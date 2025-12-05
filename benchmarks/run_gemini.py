from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from tqdm import tqdm

DATA_ROOT = Path("benchmarks/datasets/FOLIO/data/v0.0")
DEFAULT_MODEL = "gemini-2.0-flash"


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


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        newline = stripped.find("\n")
        if newline != -1:
            stripped = stripped[newline + 1 :]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def build_prompt(sentence: str) -> str:
    return (
        "Convert the following sentence into first-order logic (FOL). USE the predicates from the sentence itself. and use proper boolean logic symbols lik for all - ∀, or- ∨ etc.\n"
        f"Sentence: {sentence.strip()}\n"
        'Return only JSON data like {"fol": "..."} with no extra commentary. or markdown formatting.'
    )


def create_client(model: str, api_key: Optional[str]) -> genai.GenerativeModel:
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "Google Gemini API key missing. Set GOOGLE_API_KEY or pass --api-key."
        )
    genai.configure(api_key=key)
    return genai.GenerativeModel(model)


def call_gemini(
    client: genai.GenerativeModel,
    sentence: str,
    max_retries: int = 5,
    backoff: float = 1.0,
) -> Dict[str, object]:
    prompt = build_prompt(sentence)
    last_error: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.generate_content(
                prompt,
                generation_config={"temperature": 0.0},
            )
            text = (response.text or "").strip()
            clean = strip_code_fences(text)
            translation = None
            error = None
            try:
                parsed = json.loads(clean)
                translation = parsed.get("fol")
                if not translation:
                    error = "Missing 'fol' field in response JSON"
            except json.JSONDecodeError:
                error = f"Failed to parse JSON response: {clean[:120]}..."
            return {
                "translation": translation,
                "error": error,
                "raw_text": clean,
                "raw_text_original": text,
                "raw_response": response.to_dict(),
            }
        except google_exceptions.GoogleAPICallError as exc:  # type: ignore[attr-defined]
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        if attempt < max_retries:
            sleep_for = backoff * (2 ** (attempt - 1))
            logging.warning(
                "Gemini call failed (attempt %d/%d): %s; retrying in %.1fs",
                attempt,
                max_retries,
                last_error,
                sleep_for,
            )
            time.sleep(sleep_for)
    return {
        "translation": None,
        "error": last_error or "Gemini call failed",
        "raw_text": "",
        "raw_text_original": "",
        "raw_response": {},
    }


def summarize(rows: List[Dict[str, object]]) -> Dict[str, object]:
    total = len(rows)
    success = sum(1 for row in rows if row.get("translation") and not row.get("error"))
    return {
        "total_sentences": total,
        "translations": success,
        "translation_rate": (success / total) if total else 0.0,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate FOLIO sentences with Gemini (sequential, single file)."
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
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override GOOGLE_API_KEY environment variable",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=Path("outputs/folio/gemini_rows.jsonl"),
        help="Path to write per-sentence rows",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("outputs/folio/gemini_summary.json"),
        help="Path to write summary metrics",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="How many times to retry a failed Gemini call (default: 5)",
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

    client = create_client(args.model, args.api_key)

    progress: Optional[tqdm] = None
    if not args.no_progress and sys.stderr.isatty():
        progress = tqdm(total=len(records), desc="Gemini", unit="example", leave=False)

    rows: List[Dict[str, object]] = []
    try:
        for record in records:
            for sentence in iter_sentences(record):
                llm_result = call_gemini(
                    client,
                    sentence["text"],
                    max_retries=args.max_retries,
                )
                rows.append(
                    {
                        "story_id": str(record.get("story_id")),
                        "example_id": str(record.get("example_id")),
                        "label": record.get("label"),
                        "sentence_type": sentence.get("type"),
                        "sentence_index": sentence.get("index"),
                        "sentence": sentence.get("text"),
                        "gold_fol": sentence.get("gold_fol"),
                        "model": args.model,
                        **llm_result,
                    }
                )
            if progress is not None:
                progress.update(1)
    finally:
        if progress is not None:
            progress.close()

    summary = summarize(rows)
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
