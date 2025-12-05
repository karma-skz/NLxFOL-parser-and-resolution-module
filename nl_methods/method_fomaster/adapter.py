"""Adapter to convert common FOL into FOL master syntax and validate parse."""
import re
from . import fol_syntax_semantics as folm

_PATTERN = re.compile(r"([A-Z][A-Za-z0-9_]*)\(([^()]*)\)")


def adapt(fol: str) -> str:
    s = fol.strip()
    s = re.sub(r"forall\s+([a-z][A-Za-z0-9_]*)\.\s*", lambda m: f"U{m.group(1)}", s)
    s = re.sub(r"exists\s+([a-z][A-Za-z0-9_]*)\.\s*", lambda m: f"X{m.group(1)}", s)
    s = s.replace('<->', ' - ').replace('->', ' > ').replace('&', ' ^ ').replace('|', ' v ')
    s = re.sub(r"\bnot\b", "~", s)
    s = re.sub(r"([a-z][A-Za-z0-9_]*)\s*=\s*([a-z][A-Za-z0-9_]*)", r"=(\1,\2)", s)
    def fix_pred(m):
        name = m.group(1)
        args = m.group(2)
        clean = re.sub(r"_+", "", name)
        clean = re.sub(r"[TFUXv]", "", clean) or 'P'
        clean = clean[0].upper() + clean[1:]
        arg_list = [a.strip() for a in args.split(',') if a.strip()]
        fixed_args = []
        for a in arg_list:
            fixed_args.append(re.sub(r"_+", "", a.lower() if a and a[0].isupper() else a))
        return f"{clean}({','.join(fixed_args)})"
    s = _PATTERN.sub(fix_pred, s)
    return re.sub(r"\s+", " ", s).strip()


def can_parse(fol: str) -> bool:
    adapted = adapt(fol)
    toks = folm.tokenize(adapted)
    if not toks:
        return False
    tree = folm.parse(toks)
    return tree is not None
