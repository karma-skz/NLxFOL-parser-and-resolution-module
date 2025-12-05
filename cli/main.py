#!/usr/bin/env python
"""Unified command-line interface for translation, Gemini, and KB flows."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_local_env() -> None:
    """Populate os.environ from an adjacent .env.local file if present."""
    env_path = Path(__file__).with_name(".env.local")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        val = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = val


_load_local_env()

from knowledge_base import kb
from nl_methods.nl_to_fol import (
    translate,
    validate_with_methods,
    available_methods,
)
from nl_methods.resolution import (
    run_resolution,
    run_resolution_from_file,
    write_results as write_resolution_results,
)

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_MAX_RETRIES = 5


class GeminiSession:
    """Thin wrapper that lazily loads the Gemini helpers."""

    def __init__(self, model: str, api_key: Optional[str], max_retries: int) -> None:
        self.model = model
        self.api_key = api_key
        self.max_retries = max_retries
        self._client = None
        self._create_client, self._call_gemini = _load_gemini_helpers()

    def translate(self, sentence: str) -> Dict[str, object]:
        if self._client is None:
            self._client = self._create_client(self.model, self.api_key)
        return self._call_gemini(
            self._client,
            sentence,
            max_retries=self.max_retries,
        )


def _load_gemini_helpers():
    try:
        from benchmarks.run_gemini import call_gemini, create_client
    except ModuleNotFoundError as exc:  # google.generativeai missing
        raise RuntimeError(
            "Gemini support requires the google-generativeai dependency. "
            "Install requirements before using --gemini."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unable to initialize Gemini helpers: {exc}") from exc
    return create_client, call_gemini


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translate sentences, compare validators, call Gemini, and manage the KB.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="Translate NL to FOL, run validators, optionally call Gemini, and interact with the KB.",
    )
    _attach_sentence_arguments(analyze)
    analyze.add_argument(
        "--method",
        choices=available_methods(),
        help="Validate with a single method (default: run all).",
    )
    analyze.add_argument(
        "--methods",
        nargs="+",
        choices=available_methods(),
        help="Validate with a custom subset. Overrides --method.",
    )
    analyze.add_argument(
        "--skip-gemini",
        action="store_true",
        help="Disable Gemini calls even if an API key is configured.",
    )
    analyze.add_argument(
        "--gemini-model",
        default=DEFAULT_GEMINI_MODEL,
        help=f"Gemini model name (default: {DEFAULT_GEMINI_MODEL}).",
    )
    analyze.add_argument(
        "--api-key",
        default=None,
        help="Optional Gemini API key (defaults to GOOGLE_API_KEY).",
    )
    analyze.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Retry attempts for Gemini requests (default: 5).",
    )
    analyze.add_argument(
        "--add-to-kb",
        action="store_true",
        help="Add the translator-produced FOL to the knowledge base when valid.",
    )
    analyze.add_argument(
        "--query-kb",
        action="store_true",
        help="Query the knowledge base with the translator-produced FOL.",
    )

    kb_parser = subparsers.add_parser("kb", help="Knowledge base management commands.")
    kb_sub = kb_parser.add_subparsers(dest="kb_command", required=True)

    kb_add = kb_sub.add_parser(
        "add", help="Translate NL and add the formula to the KB."
    )
    _attach_sentence_arguments(kb_add)

    kb_query = kb_sub.add_parser("query", help="Translate NL and query the KB.")
    _attach_sentence_arguments(kb_query)

    kb_sub.add_parser(
        "list", help="List KB statistics, facts, rules, and stored formulas."
    )
    kb_sub.add_parser("clear", help="Clear the KB state from memory and disk.")

    resolution = subparsers.add_parser(
        "resolution",
        help="Run the legacy FOL resolution prover against inline data or a formatted file.",
    )
    resolution.add_argument(
        "--input",
        type=Path,
        help="Optional path to a FOL-Resolution formatted input file.",
    )
    resolution.add_argument(
        "--output",
        type=Path,
        help="Where to write TRUE/FALSE results (defaults to input folder/output.txt in file mode).",
    )
    resolution.add_argument(
        "--queries",
        nargs="+",
        help="Inline queries when not using --input (same syntax as the legacy solver).",
    )
    resolution.add_argument(
        "--kb-sentences",
        nargs="+",
        help="Inline KB sentences (required with --queries when no --input is provided).",
    )
    resolution.add_argument(
        "--print-results",
        action="store_true",
        help="Echo TRUE/FALSE verdicts to stdout.",
    )

    return parser


def _attach_sentence_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "sentence",
        nargs="+",
        help="One or more quoted sentences (each argument represents a full sentence).",
    )


def handle_analyze(args: argparse.Namespace) -> int:
    sentences = [s.strip() for s in args.sentence if s.strip()]
    if not sentences:
        print("No sentences provided.", file=sys.stderr)
        return 1

    methods = _resolve_method_selection(args)
    gemini_session: Optional[GeminiSession] = None
    if not args.skip_gemini:
        try:
            gemini_session = GeminiSession(
                args.gemini_model, args.api_key, args.max_retries
            )
        except RuntimeError as exc:
            print(f"Gemini disabled: {exc}", file=sys.stderr)
            return 1

    overall_success = True
    for idx, sentence in enumerate(sentences, start=1):
        print(f"\n=== Sentence {idx} ===")
        ok = _analyze_sentence(sentence, methods, args, gemini_session)
        overall_success = overall_success and ok
    return 0 if overall_success else 1


def _analyze_sentence(
    sentence: str,
    methods: Optional[Iterable[str]],
    args: argparse.Namespace,
    gemini_session: Optional[GeminiSession],
) -> bool:
    print(f"NL: {sentence}")
    fol = translate(sentence, strict=False)
    translator_ok = not fol.startswith("[ERROR]")

    if translator_ok:
        print(f"Translator FOL: {fol}")
        validation = validate_with_methods(
            fol,
            methods=methods,
            run_all=methods is None,
        )
        print("Validators:")
        for name, passed in validation.items():
            status = "OK" if passed else "FAIL"
            print(f"  - {name}: {status}")
    else:
        print(f"Translator Error: {fol}")

    gemini_ok = True
    if gemini_session is not None:
        try:
            response = gemini_session.translate(sentence)
        except RuntimeError as exc:
            print(f"Gemini error: {exc}", file=sys.stderr)
            return False
        translation = response.get("translation")
        error_msg = response.get("error")
        if translation:
            print(f"Gemini ({gemini_session.model}): {translation}")
            if translator_ok:
                matches = translation.strip() == fol.strip()
                print(f"  Matches translator: {'YES' if matches else 'NO'}")
        else:
            gemini_ok = False
            print("Gemini failed to produce FOL.")
            if error_msg:
                print(f"  Error: {error_msg}")

    if args.add_to_kb:
        if translator_ok:
            added = kb().add(fol)
            print("KB add:" + (" success" if added else " failed"))
        else:
            print("KB add skipped (translator error).")

    if args.query_kb:
        if translator_ok:
            entailed, trace = kb().query(fol)
            print(f"KB query: {'ENTAILED' if entailed else 'NOT ENTAILED'}")
            if trace:
                print("Trace:")
                for line in trace:
                    print(f"  {line}")
        else:
            print("KB query skipped (translator error).")

    return translator_ok and gemini_ok


def handle_kb(args: argparse.Namespace) -> int:
    command = args.kb_command
    if command in {"add", "query"}:
        sentence = _consume_sentence(args)
        if not sentence:
            print("Sentence required.", file=sys.stderr)
            return 1
        if command == "add":
            return _kb_add(sentence)
        return _kb_query(sentence)
    if command == "list":
        _kb_list()
        return 0
    if command == "clear":
        kb().clear()
        print("Knowledge base cleared.")
        return 0
    print(f"Unknown KB command: {command}", file=sys.stderr)
    return 1


def handle_resolution(args: argparse.Namespace) -> int:
    if args.input:
        input_path = args.input
        output_path = args.output or input_path.with_name("output.txt")
        results = run_resolution_from_file(input_path, output_path)
        print(f"Resolution complete. Results written to {output_path}.")
    else:
        if not args.queries or not args.kb_sentences:
            print(
                "Inline mode requires both --queries and --kb-sentences.",
                file=sys.stderr,
            )
            return 1
        results = run_resolution(args.queries, args.kb_sentences)
        if args.output:
            write_resolution_results(args.output, results)
            print(f"Results written to {args.output}.")
    if args.print_results or not args.output:
        labels = (
            args.queries
            if args.queries
            else [f"query_{i+1}" for i in range(len(results))]
        )
        for label, verdict in zip(labels, results):
            print(f"{label}: {'TRUE' if verdict else 'FALSE'}")
    return 0


def _kb_add(sentence: str) -> int:
    print(f"Adding: {sentence}")
    fol = translate(sentence, strict=False)
    if fol.startswith("[ERROR]"):
        print(f"Translation failed: {fol}")
        return 1
    print(f"  FOL: {fol}")
    if kb().add(fol):
        print("  OK: Added to knowledge base.")
        return 0
    print("  WARN: Stored but not processed (see logs).")
    return 1


def _kb_query(sentence: str) -> int:
    print(f"Querying: {sentence}")
    fol = translate(sentence, strict=False)
    if fol.startswith("[ERROR]"):
        print(f"Translation failed: {fol}")
        return 1
    print(f"  FOL: {fol}")
    entailed, trace = kb().query(fol)
    if entailed:
        print("  Result: ENTAILED")
    else:
        print("  Result: NOT ENTAILED")
    if trace:
        print("  Trace:")
        for line in trace:
            print(f"    {line}")
    return 0 if entailed else 1


def _kb_list() -> None:
    state = kb().get_state()
    print("Knowledge Base Stats:")
    stats = state["stats"]
    print(f"  Facts: {stats['fact_count']}")
    print(f"  Rules: {stats['rule_count']}")
    active = ", ".join(stats.get("active_predicates", [])) or "(none)"
    print(f"  Active predicates: {active}")

    print("\nFacts:")
    _print_collection(state["facts"])

    print("\nRules:")
    _print_collection(state["rules"])

    print("\nStored formulas:")
    _print_collection(state["other"])


def _print_collection(items: Iterable[str]) -> None:
    has_items = False
    for item in items:
        has_items = True
        print(f"  - {item}")
    if not has_items:
        print("  (none)")


def _resolve_method_selection(args: argparse.Namespace) -> Optional[List[str]]:
    if getattr(args, "methods", None):
        return list(dict.fromkeys(args.methods))
    if getattr(args, "method", None):
        return [args.method]
    return None


def _consume_sentence(args: argparse.Namespace) -> Optional[str]:
    sentences = [s.strip() for s in getattr(args, "sentence", []) if s.strip()]
    if not sentences:
        return None
    if len(sentences) > 1:
        print("Multiple sentences detected; using the first.")
    return sentences[0]


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        return handle_analyze(args)
    if args.command == "kb":
        return handle_kb(args)
    if args.command == "resolution":
        return handle_resolution(args)
    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
