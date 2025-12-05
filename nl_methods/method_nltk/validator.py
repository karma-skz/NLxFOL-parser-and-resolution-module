"""NLTK-based FOL validator method."""
from __future__ import annotations
from nltk.sem.logic import LogicParser

_parser = LogicParser()

def _normalize(expr: str) -> str:
    s = expr
    s = s.replace('forall ', 'all ')
    s = s.replace(' not ', ' - ')
    s = s.replace('(not ', '(- ')
    if s.startswith('not '):
        s = '-' + s[4:]
    return s

def validate(fol: str) -> bool:
    try:
        _parser.parse(_normalize(fol))
        return True
    except Exception:
        return False
