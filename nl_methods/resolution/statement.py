"""Statement utilities adapted from the legacy FOL-Resolution project."""

from __future__ import annotations

import copy
from typing import Dict, Iterable, List, Optional, Set

from .predicate import Predicate


class Statement:
    """Represents a disjunction of predicates."""

    def __init__(self, statement_string: Optional[str] = None) -> None:
        self.statement_string: Optional[str] = None
        self.predicate_set: Optional[Set[Predicate]] = None
        if statement_string:
            self.init_from_string(statement_string)

    def init_from_string(self, statement_string: str) -> None:
        predicate_list = [
            Predicate(token) for token in statement_string.split("|") if token
        ]
        self.predicate_set = set(predicate_list)
        self.statement_string = "|".join(
            pred.predicate_string for pred in self.predicate_set
        )

    def init_from_predicate_set(self, predicate_set: Set[Predicate]) -> None:
        self.predicate_set = predicate_set
        self.statement_string = "|".join(
            pred.predicate_string for pred in predicate_set
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.statement_string or ""

    def __eq__(self, statement: object) -> bool:
        return (
            isinstance(statement, Statement)
            and self.predicate_set == statement.predicate_set
        )

    def __hash__(self) -> int:
        return hash("".join(sorted(self.statement_string or "")))

    def exists_in_kb(self, kb: Set["Statement"]) -> bool:
        return self in kb

    def add_statement_to_kb(
        self, kb: Set["Statement"], kb_hash: Dict[str, Set["Statement"]]
    ) -> None:
        kb.add(self)
        assert self.predicate_set is not None
        for predicate in self.predicate_set:
            kb_hash.setdefault(predicate.name, set()).add(self)

    def resolve(self, statement: "Statement") -> Set["Statement"] | bool:
        assert self.predicate_set is not None
        assert statement.predicate_set is not None
        inferred: Set[Statement] = set()
        for predicate_1 in self.predicate_set:
            for predicate_2 in statement.predicate_set:
                unification = False
                if (
                    predicate_1.negative ^ predicate_2.negative
                ) and predicate_1.name == predicate_2.name:
                    unification = predicate_1.unify_with_predicate(predicate_2)
                if unification is False:
                    continue
                remainder_1 = [
                    copy.deepcopy(pred)
                    for pred in self.predicate_set
                    if pred != predicate_1
                ]
                remainder_2 = [
                    copy.deepcopy(pred)
                    for pred in statement.predicate_set
                    if pred != predicate_2
                ]
                if not remainder_1 and not remainder_2:
                    return False
                substituted_1 = [pred.substitute(unification) for pred in remainder_1]
                substituted_2 = [pred.substitute(unification) for pred in remainder_2]
                new_statement = Statement()
                new_statement.init_from_predicate_set(
                    set(substituted_1 + substituted_2)
                )
                inferred.add(new_statement)
        return inferred

    def get_resolving_clauses(
        self, kb_hash: Dict[str, Set["Statement"]]
    ) -> Set["Statement"]:
        assert self.predicate_set is not None
        clauses: Set[Statement] = set()
        for predicate in self.predicate_set:
            clauses.update(kb_hash.get(predicate.name, set()))
        return clauses
