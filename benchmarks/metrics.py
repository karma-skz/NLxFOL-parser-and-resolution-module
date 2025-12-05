"""Utility helpers for scoring NL→FOL translation experiments."""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu


def _normalize_formula(formula: str) -> str:
    text = formula.strip()
    replacements = {
        "∀": "forall ",
        "∃": "exists ",
        "¬": "not ",
        "→": "->",
        "⇒": "->",
        "↔": "<->",
        "⇔": "<->",
        "∧": "&",
        "∨": "|",
        "⊕": " xor ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokenize_formula(formula: str) -> List[str]:
    cleaned = _normalize_formula(formula)
    return cleaned.split()


def _extract_predicates(formula: str) -> List[str]:
    matches = re.findall(r"([A-Z][A-Za-z0-9_]*)\s*\(", formula)
    return matches


def compute_parsing_metrics(
    gold: str | None, translation: str | None
) -> Dict[str, float] | None:
    if not gold or not translation:
        return None
    gold_norm = _normalize_formula(gold)
    trans_norm = _normalize_formula(translation)
    exact_match = 1.0 if gold_norm == trans_norm else 0.0

    gold_predicates = _extract_predicates(gold_norm)
    trans_predicates = _extract_predicates(trans_norm)
    gold_set = set(gold_predicates)
    trans_set = set(trans_predicates)
    intersection = gold_set & trans_set
    precision = len(intersection) / len(trans_set) if trans_set else 0.0
    recall = len(intersection) / len(gold_set) if gold_set else 0.0
    if precision + recall > 0:
        predicate_f1 = 2 * precision * recall / (precision + recall)
    else:
        predicate_f1 = 0.0

    smooth = SmoothingFunction().method1
    gold_tokens = _tokenize_formula(gold_norm)
    trans_tokens = _tokenize_formula(trans_norm)
    if gold_tokens and trans_tokens:
        bleu = sentence_bleu([gold_tokens], trans_tokens, smoothing_function=smooth)
    else:
        bleu = 0.0

    tree_similarity = difflib.SequenceMatcher(None, trans_norm, gold_norm).ratio()

    return {
        "exact_match": exact_match,
        "predicate_precision": precision,
        "predicate_recall": recall,
        "predicate_f1": predicate_f1,
        "bleu": bleu,
        "tree_similarity": tree_similarity,
    }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate_parsing_metrics(
    metrics: Iterable[Mapping[str, float]],
) -> Dict[str, float]:
    buckets: Dict[str, List[float]] = defaultdict(list)
    for metric in metrics:
        for key, value in metric.items():
            if value is not None:
                buckets[key].append(float(value))
    return {key: _mean(vals) for key, vals in buckets.items()}


def aggregate_translation_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    success = 0
    validators: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"passed": 0, "failed": 0}
    )
    parsing_bucket: List[Dict[str, float]] = []

    for row in rows:
        translation = row.get("translation")
        error = row.get("error")
        if translation and not error:
            success += 1
        row_validators = row.get("validators") or {}
        for name, passed in row_validators.items():
            key = "passed" if passed else "failed"
            validators[name][key] += 1
        metrics = row.get("parsing_metrics")
        if not metrics:
            metrics = compute_parsing_metrics(row.get("gold_fol"), translation)
        if metrics:
            parsing_bucket.append(metrics)

    summary: Dict[str, Any] = {
        "total_sentences": total,
        "translations": success,
        "translation_rate": (success / total) if total else 0.0,
    }
    if validators:
        summary["validators"] = validators
    if parsing_bucket:
        summary["parsing_metrics"] = _aggregate_parsing_metrics(parsing_bucket)
    return summary


def aggregate_entailment_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(rows)
    entailed = sum(1 for row in rows if row.get("entailed"))
    return {
        "total_examples": total,
        "entailed": entailed,
        "entailed_rate": (entailed / total) if total else 0.0,
    }
