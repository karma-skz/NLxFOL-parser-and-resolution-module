"""Predicate utilities adapted from the legacy FOL-Resolution project."""

from __future__ import annotations

from typing import Dict, List, Union


class Predicate:
    """Simple predicate wrapper supporting unification."""

    def __init__(self, predicate: str) -> None:
        split_predicate = predicate.split("(")
        self.negative = False
        self.name = split_predicate[0]
        self.predicate_string = predicate
        if "~" in split_predicate[0]:
            self.name = split_predicate[0][1:]
            self.negative = True
        parameters = split_predicate[1][:-1]
        self.arguments = parameters.split(",") if parameters else []

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            ("~" if self.negative else "")
            + self.name
            + "("
            + ",".join(self.arguments)
            + ")"
        )

    def negate(self) -> None:
        self.negative = not self.negative
        self.update_predicate_string()

    def __eq__(self, predicate: object) -> bool:
        return isinstance(predicate, Predicate) and self.__dict__ == predicate.__dict__

    def __hash__(self) -> int:
        return hash(self.predicate_string)

    def unify_with_predicate(
        self, predicate: "Predicate"
    ) -> Union[Dict[str, str], bool]:
        if self.name == predicate.name and len(self.arguments) == len(
            predicate.arguments
        ):
            substitution: Dict[str, str] = {}
            return unify(self.arguments, predicate.arguments, substitution)
        return False

    def update_predicate_string(self) -> None:
        self.predicate_string = (
            ("~" if self.negative else "")
            + self.name
            + "("
            + ",".join(self.arguments)
            + ")"
        )

    def substitute(self, substitution: Dict[str, str]) -> "Predicate":
        if substitution:
            for index, arg in enumerate(self.arguments):
                if arg in substitution:
                    self.arguments[index] = substitution[arg]
            self.update_predicate_string()
        return self


def unify(
    predicate1_arg: Union[str, List[str]],
    predicate2_arg: Union[str, List[str]],
    substitution: Dict[str, str] | bool,
) -> Dict[str, str] | bool:
    if substitution is False:
        return False
    if predicate1_arg == predicate2_arg:
        return substitution  # type: ignore[return-value]
    if isinstance(predicate1_arg, str) and predicate1_arg.islower():
        return unify_var(predicate1_arg, predicate2_arg, substitution)
    if isinstance(predicate2_arg, str) and predicate2_arg.islower():
        return unify_var(predicate2_arg, predicate1_arg, substitution)
    if isinstance(predicate1_arg, list) and isinstance(predicate2_arg, list):
        if predicate1_arg and predicate2_arg:
            head = unify(predicate1_arg[0], predicate2_arg[0], substitution)
            return unify(predicate1_arg[1:], predicate2_arg[1:], head)
        return substitution  # type: ignore[return-value]
    return False


def unify_var(var: str, x: Union[str, List[str]], substitution: Dict[str, str] | bool):
    if substitution is False:
        return False
    if var in substitution:
        return unify(substitution[var], x, substitution)
    if isinstance(x, str) and x in substitution:
        return unify(var, substitution[x], substitution)
    assert isinstance(substitution, dict)
    substitution[var] = x  # type: ignore[index]
    return substitution
