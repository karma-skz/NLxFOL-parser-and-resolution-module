from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tqdm import tqdm

from benchmarks.metrics import compute_parsing_metrics, aggregate_translation_rows
from nl_methods.nl_to_fol import translate as translate_sentence, validate_with_methods

DATA_ROOT = Path("benchmarks/datasets/FOLIO/data/v0.0")


def load_records(split: str, limit: Optional[int]) -> List[Dict[str, object]]:
    path = DATA_ROOT / f"folio-{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"FOLIO split '{split}' not found at {path}")
    records: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
            if limit is not None and len(records) >= limit:
                break
    return records


def iter_sentences(record: Dict[str, object]) -> Iterable[Dict[str, object]]:
    premises: List[str] = record.get("premises", [])
    premises_fol: List[str] = record.get("premises-FOL", []) or []
    for idx, text in enumerate(premises):
        gold = premises_fol[idx] if idx < len(premises_fol) else None
        yield {
            "type": "premise",
            "index": idx,
            "text": text,
            "gold_fol": gold,
        }
    yield {
        "type": "conclusion",
        "index": 0,
        "text": record.get("conclusion", ""),
        "gold_fol": record.get("conclusion-FOL"),
    }


def write_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, summary: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def translate_with_validators(text: str) -> Dict[str, object]:
    try:
        translation = translate_sentence(text, strict=False)
    except Exception as exc:  # noqa: BLE001
        return {"translation": None, "error": str(exc), "validators": {}}
    error = translation if translation.startswith("[ERROR]") else None
    translation_value = None if error else translation
    validators = {}
    if translation_value:
        try:
            validators = validate_with_methods(translation_value, run_all=True)
        except Exception as exc:  # noqa: BLE001
            error = f"Validator failure: {exc}"
            translation_value = None
            validators = {}
    return {
        "translation": translation_value,
        "error": error,
        "validators": validators,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Translate FOLIO sentences with the rule-based NL→FOL system and run all"
            " validators."
        )
    )
    parser.add_argument(
        "--split",
        choices=["train", "validation"],
        default="validation",
        help="Dataset split to process (default: validation)",
    )
    parser.add_argument(
        "--limit-examples",
        type=int,
        default=None,
        help="Optional cap on number of FOLIO examples",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("outputs/folio/parser_rows.jsonl"),
        help="Path to write per-sentence rows",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("outputs/folio/parser_summary.json"),
        help="Path to write summary metrics",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the tqdm progress bar",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(message)s",
    )

    records = load_records(args.split, args.limit_examples)
    logging.info("Loaded %d FOLIO examples (split=%s)", len(records), args.split)

    progress: Optional[tqdm] = None
    if not args.no_progress and sys.stderr.isatty():
        progress = tqdm(total=len(records), desc="Parser", unit="example", leave=False)

    rows: List[Dict[str, object]] = []
    try:
        for record in records:
            for sentence in iter_sentences(record):
                result = translate_with_validators(sentence["text"])
                parsing_metrics = compute_parsing_metrics(
                    sentence.get("gold_fol"), result["translation"]
                )
                rows.append(
                    {
                        "story_id": str(record.get("story_id")),
                        "example_id": str(record.get("example_id")),
                        "label": record.get("label"),
                        "model": "rule-based",
                        "sentence_type": sentence.get("type"),
                        "sentence_index": sentence.get("index"),
                        "sentence": sentence.get("text"),
                        "gold_fol": sentence.get("gold_fol"),
                        **result,
                        "parsing_metrics": parsing_metrics,
                    }
                )
            if progress is not None:
                progress.update(1)
    finally:
        if progress is not None:
            progress.close()

    summary = aggregate_translation_rows(rows)
    write_jsonl(args.output_jsonl, rows)
    write_summary(args.summary_json, summary)

    logging.info(
        "Completed split=%s examples=%d sentences=%d translation_rate=%.2f",
        args.split,
        len(records),
        summary["total_sentences"],
        summary["translation_rate"],
    )
    print(f"Rows written to {args.output_jsonl}")
    print(f"Summary written to {args.summary_json}")


if __name__ == "__main__":
    main()
