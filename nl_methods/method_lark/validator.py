"""Lark-based FOL validator method."""
from lark import Lark

grammar = r"""
?start: expr
?expr: iff
?iff: implies (("<->" | "<=>" | "↔") implies)?
?implies: or_expr (("->" | "=>" | "→") implies)?
?or_expr: and_expr (("|" | "∨") and_expr)*
?and_expr: unary (("&" | "∧") unary)*
?unary: quant | ("not" | "!" | "~" | "¬") unary | equality | predicate | "(" expr ")"
quant: (("forall" | "exists") | ("∀" | "∃")) varlist "." expr
varlist: VAR ( ("," VAR) | VAR )*
equality: term ("=" | "!=" | "≠") term
predicate: NAME "(" [terms] ")"
terms: term ("," term)*
?term: VAR | NAME | NAME "(" [terms] ")"
VAR: /[a-z][a-z0-9_]*/
NAME: /[A-Z][A-Za-z0-9_]*/
%import common.WS
%ignore WS
"""
_parser = Lark(grammar, start="start", parser="lalr")

def validate(fol: str) -> bool:
    try:
        _parser.parse(fol)
        return True
    except Exception:
        return False
