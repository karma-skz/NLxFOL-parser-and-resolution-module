from typing import List

def atomic_parser(formula: str):
    if '(' not in formula or ')' not in formula:
        return None
    pred, rest = formula.split('(',1)
    args = rest[:-1]
    return [pred, [a.strip() for a in args.split(',') if a.strip()]]

def atomic_evaluator(formula: str, MOD):
    parsed = atomic_parser(formula)
    if not parsed:
        return None
    pred, args = parsed
    if pred == '=':
        if len(args) != 2:
            return None
        return (args[0], args[1]) in MOD.interp.get('=', set())
    rel = MOD.interp.get(pred)
    if rel is None:
        return False
    if isinstance(rel, set):
        if all(a in MOD.interp for a in args):
            tup = tuple(MOD.interp[a] for a in args)
            return tup in rel
    return False
