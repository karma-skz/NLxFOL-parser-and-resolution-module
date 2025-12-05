"""FO-Master style validator updated to accept common FOL notation.
This performs a lightweight tokenization and structural checks (balanced
parentheses, basic token validity). It is intentionally permissive.
"""
from __future__ import annotations
import re
from . import fol_syntax_semantics as folm

token_re = re.compile(
    r"\s*(" \
    r"forall|exists|" \
    r"<->|<=>|↔|" \
    r"->|=>|→|" \
    r"\||∨|" \
    r"&|∧|" \
    r"not|~|!|¬|" \
    r"\(|\)|,|\.|" \
    r"!=|≠|=|" \
    r"[A-Z][A-Za-z0-9_]*|" \
    r"[a-z][a-z0-9_]*" \
    r")"
)


def _tokenize_common(expr: str) -> list[str] | None:
    tokens: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        m = token_re.match(expr, i)
        if not m:
            # Unknown/mismatched character
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            return None
        tok = m.group(1)
        if tok.strip():
            tokens.append(tok)
        i = m.end()
    return tokens


def _balanced_parens(tokens: list[str]) -> bool:
    stack = 0
    for t in tokens:
        if t == '(':
            stack += 1
        elif t == ')':
            stack -= 1
            if stack < 0:
                return False
    return stack == 0


def validate(fol: str) -> bool:
    # Tokenize to common notation using local regex (no adapter)
    tokens = _tokenize_common(fol)
    if not tokens:
        return False
    if not _balanced_parens(tokens):
        return False
    # Fallback to previous lightweight parser to ensure non-empty structure
    parsed = folm.parse(tokens)
    return parsed is not None
