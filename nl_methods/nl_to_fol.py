"""Utility helpers to translate NL sentences to FOL and validate the output.

This module acts as the high-level façade for everything under ``nl_methods``.
It wires the shared NL→FOL translator together with all available validators so
other packages can import a single module instead of juggling three folders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping

from translator import translate_sentence
from .method_lark.validator import validate as _validate_lark
from .method_nltk.validator import validate as _validate_nltk
from .method_fomaster.validator import validate as _validate_fomaster


ValidatorFn = Callable[[str], bool]


class TranslationError(RuntimeError):
    """Raised when the rule-based translator fails to produce valid FOL."""


class UnknownMethodError(ValueError):
    """Raised when a consumer requests an unsupported validator."""


VALIDATORS: Dict[str, ValidatorFn] = {
    "lark": _validate_lark,
    "nltk": _validate_nltk,
    "fomaster": _validate_fomaster,
}


@dataclass(frozen=True)
class TranslationRecord:
    """Container returned by ``translate_and_validate`` / ``batch_translate``."""

    sentence: str
    fol: str
    validation: Mapping[str, bool]

    @property
    def ok(self) -> bool:
        """True when the translator produced a non-error formula."""

        return not self.fol.startswith("[ERROR]")


def available_methods() -> List[str]:
    """Return a copy of the validator names in registration order."""

    return list(VALIDATORS.keys())


def translate(sentence: str, *, strict: bool = True) -> str:
    """Translate a single sentence to FOL.

    Args:
            sentence: Natural language input.
            strict: When True (default) raise ``TranslationError`` on failures. When
                    False, return the translator's raw error string so callers can log it.
    """

    fol = translate_sentence(sentence)
    if strict and fol.startswith("[ERROR]"):
        raise TranslationError(fol)
    return fol


def validate(fol: str, method: str) -> bool:
    """Validate a FOL string with a single method name."""

    method_key = method.lower()
    validator = VALIDATORS.get(method_key)
    if validator is None:
        raise UnknownMethodError(f"Unknown validation method: {method}")
    return bool(validator(fol))


def _select_methods(methods: Iterable[str] | None, run_all: bool) -> List[str]:
    if run_all or methods is None:
        return available_methods()
    ordered: List[str] = []
    for name in methods:
        key = name.lower()
        if key not in VALIDATORS:
            raise UnknownMethodError(f"Unknown validation method: {name}")
        if key not in ordered:
            ordered.append(key)
    return ordered


def validate_with_methods(
    fol: str, *, methods: Iterable[str] | None = None, run_all: bool = False
) -> Dict[str, bool]:
    """Validate ``fol`` with the requested subset (or all) validators."""

    selected = _select_methods(methods, run_all)
    return {name: bool(VALIDATORS[name](fol)) for name in selected}


def translate_and_validate(
    sentence: str,
    *,
    methods: Iterable[str] | None = None,
    run_all: bool = False,
    strict: bool = True,
) -> TranslationRecord:
    """Translate ``sentence`` and optionally validate the resulting FOL string."""

    fol = translate(sentence, strict=strict)
    validation = validate_with_methods(fol, methods=methods, run_all=run_all)
    return TranslationRecord(sentence=sentence, fol=fol, validation=validation)


def batch_translate(
    sentences: Iterable[str],
    *,
    methods: Iterable[str] | None = None,
    run_all: bool = False,
    strict: bool = True,
) -> List[TranslationRecord]:
    """Translate+validate a collection of sentences, preserving the order."""

    return [
        translate_and_validate(s, methods=methods, run_all=run_all, strict=strict)
        for s in sentences
    ]


__all__ = [
    "TranslationError",
    "UnknownMethodError",
    "TranslationRecord",
    "available_methods",
    "translate",
    "validate",
    "validate_with_methods",
    "translate_and_validate",
    "batch_translate",
]
