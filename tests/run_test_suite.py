from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge_base import kb
from nl_methods.nl_to_fol import translate as translate_sentence

DEFAULT_INPUT = Path("tests/test.json")
DEFAULT_OUTPUT = Path("tests/test_results.json")
DEFAULT_LOG = Path("tests/test_results.log")
DEFAULT_GRAPH = Path("tests/test_results.png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the NL→FOL translator + knowledge base against a JSON test suite."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the test definition JSON (default: tests/test.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the aggregated JSON results (default: tests/test_results.json)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG,
        help="Where to write a human-readable log (default: tests/test_results.log)",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Abort the suite immediately on the first failed test",
    )
    parser.add_argument(
        "--max-tests",
        type=int,
        default=343,
        help=(
            "Limit how many tests to execute from the JSON file (default: 343; "
            "set to 0 or a negative value to run all tests)."
        ),
    )
    parser.add_argument(
        "--graph-output",
        type=Path,
        default=DEFAULT_GRAPH,
        help=(
            "Path to save a PNG summary of the run (default: tests/test_results.png)."
        ),
    )
    parser.add_argument(
        "--progress-graph",
        type=Path,
        default=None,
        help=(
            "Optional override for the timeline graph path. "
            "Defaults to <graph-output> with '_progress' suffix."
        ),
    )
    parser.add_argument(
        "--skip-graphs",
        action="store_true",
        help="Skip rendering PNG graphs even if matplotlib is installed.",
    )
    return parser.parse_args()


def _load_tests(path: Path) -> Sequence[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    tests = payload.get("tests")
    if not isinstance(tests, list):
        raise ValueError("tests/test.json must contain a 'tests' array")
    return tests


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _init_logging(log_path: Path) -> None:
    _ensure_parent(log_path)
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def _translate(sentence: str) -> str:
    return translate_sentence(sentence, strict=False)


def _run_test(test: Dict[str, Any]) -> Dict[str, Any]:
    case_name = test.get("name", "<unnamed>")
    steps = test.get("steps", [])
    expected = test.get("expected", [])

    kb().clear()
    logging.info("=== Running %s ===", case_name)

    query_results: List[bool] = []
    step_logs: List[Dict[str, Any]] = []
    error_detected = False
    translation_errors = 0
    kb_errors = 0
    unknown_actions = 0

    for index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            logging.error("%s step %d malformed: %s", case_name, index, step)
            error_detected = True
            break
        action, sentence = step
        sentence = sentence.strip()
        entry: Dict[str, Any] = {
            "index": index,
            "action": action,
            "sentence": sentence,
        }

        fol = _translate(sentence)
        entry["fol"] = fol
        if fol.startswith("[ERROR]"):
            entry["status"] = "translation_error"
            logging.error("%s step %d translation failed: %s", case_name, index, fol)
            error_detected = True
            translation_errors += 1
            step_logs.append(entry)
            break

        if action == "add":
            added = kb().add(fol)
            entry["status"] = "added" if added else "kb_error"
            entry["success"] = added
            if not added:
                logging.error("%s step %d failed to add FOL: %s", case_name, index, fol)
                error_detected = True
                kb_errors += 1
                step_logs.append(entry)
                break
        elif action == "query":
            entailed, trace = kb().query(fol)
            entry["status"] = "queried"
            entry["entailed"] = entailed
            entry["trace"] = trace
            query_results.append(bool(entailed))
            logging.info(
                "%s step %d query result: %s -> %s",
                case_name,
                index,
                fol,
                "TRUE" if entailed else "FALSE",
            )
        else:
            entry["status"] = "unknown_action"
            logging.error("%s step %d unknown action '%s'", case_name, index, action)
            error_detected = True
            unknown_actions += 1
            step_logs.append(entry)
            break

        step_logs.append(entry)

    expected_bools = [bool(x) for x in expected]
    query_matches = sum(1 for a, b in zip(query_results, expected_bools) if a == b)
    passed = not error_detected and query_results == expected_bools

    if not error_detected and query_results != expected_bools:
        logging.warning(
            "%s expected %s but observed %s",
            case_name,
            expected_bools,
            query_results,
        )

    logging.info(
        "%s result: %s (%d/%d tests matched)",
        case_name,
        "PASS" if passed else "FAIL",
        sum(1 for a, b in zip(query_results, expected_bools) if a == b),
        max(len(expected_bools), len(query_results)),
    )

    return {
        "name": case_name,
        "passed": passed,
        "expected": expected_bools,
        "observed": query_results,
        "steps": step_logs,
        "query_count": len(query_results),
        "query_matches": query_matches,
        "translation_errors": translation_errors,
        "kb_errors": kb_errors,
        "unknown_actions": unknown_actions,
    }


def main() -> None:
    args = parse_args()
    tests = _load_tests(args.input)
    _init_logging(args.log_file)

    run_started = datetime.utcnow().isoformat() + "Z"
    wall_start = time.perf_counter()
    results: List[Dict[str, Any]] = []
    passed = 0
    total_queries = 0
    matched_queries = 0
    translation_errors = 0
    kb_errors = 0
    unknown_actions = 0
    progress_rows: List[Dict[str, Any]] = []

    max_tests = args.max_tests if args.max_tests and args.max_tests > 0 else None
    selected_tests = tests if max_tests is None else tests[:max_tests]

    for test in selected_tests:
        case_start = time.perf_counter()
        result = _run_test(test)
        case_duration = time.perf_counter() - case_start
        results.append(result)
        if result["passed"]:
            passed += 1
        elif args.stop_on_failure:
            logging.error("Stopping early due to failure in %s", result["name"])
            break

        total_queries += result.get("query_count", 0)
        matched_queries += result.get("query_matches", 0)
        translation_errors += result.get("translation_errors", 0)
        kb_errors += result.get("kb_errors", 0)
        unknown_actions += result.get("unknown_actions", 0)

        total_cases = len(results)
        progress_rows.append(
            {
                "index": total_cases,
                "name": result["name"],
                "passed": bool(result["passed"]),
                "duration_seconds": case_duration,
                "cumulative_pass_rate": (passed / total_cases) if total_cases else 0.0,
                "cumulative_query_accuracy": (
                    (matched_queries / total_queries) if total_queries else 0.0
                ),
                "query_count": result.get("query_count", 0),
                "query_matches": result.get("query_matches", 0),
                "case_translation_errors": result.get("translation_errors", 0),
            }
        )

    total_duration = time.perf_counter() - wall_start

    summary = {
        "started": run_started,
        "finished": datetime.utcnow().isoformat() + "Z",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "duration_seconds": total_duration,
        "average_case_seconds": (total_duration / len(results)) if results else 0.0,
        "max_tests": max_tests if max_tests is not None else len(tests),
        "pass_rate": (passed / len(results)) if results else 0.0,
        "query_metrics": {
            "executed": total_queries,
            "matched": matched_queries,
            "accuracy": (matched_queries / total_queries) if total_queries else 0.0,
        },
        "error_breakdown": {
            "translation_errors": translation_errors,
            "kb_errors": kb_errors,
            "unknown_actions": unknown_actions,
        },
        "results": results,
        "progress": progress_rows,
    }

    if not args.skip_graphs and args.graph_output:
        progress_path = (
            args.progress_graph
            if args.progress_graph
            else args.graph_output.with_name(
                f"{args.graph_output.stem}_progress{args.graph_output.suffix}"
            )
        )
        _render_summary_graphs(summary, args.graph_output)
        _render_progress_graph(progress_rows, progress_path)

    _ensure_parent(args.output)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    logging.info("Wrote results to %s", args.output)


def _render_summary_graphs(summary: Dict[str, Any], graph_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        logging.error("matplotlib is required for graph generation: %s", exc)
        return

    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    query_metrics = summary.get("query_metrics", {})
    error_breakdown = summary.get("error_breakdown", {})

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    ax1, ax2, ax3, ax4 = axes.flatten()

    if passed or failed:
        ax1.pie(
            [passed, failed],
            labels=["Passed", "Failed"],
            autopct="%1.1f%%",
            startangle=90,
            colors=["#2ca02c", "#d62728"],
        )
    else:
        ax1.text(0.5, 0.5, "No tests run", ha="center", va="center")
    ax1.set_title("Test Outcomes")

    err_labels = list(error_breakdown.keys()) or [
        "translation_errors",
        "kb_errors",
        "unknown_actions",
    ]
    err_values = [error_breakdown.get(lbl, 0) for lbl in err_labels]
    ax2.bar(err_labels, err_values, color="#ff7f0e")
    ax2.set_title("Error Breakdown")
    ax2.set_ylabel("Count")
    ax2.tick_params(axis="x", rotation=20)

    executed = query_metrics.get("executed", 0)
    matched = query_metrics.get("matched", 0)
    unmatched = max(executed - matched, 0)
    ax3.bar(
        ["Matched", "Unmatched"], [matched, unmatched], color=["#1f77b4", "#9467bd"]
    )
    ax3.set_title("Query Outcomes")
    ax3.set_ylabel("Count")

    duration = summary.get("duration_seconds", 0.0)
    avg_case = summary.get("average_case_seconds", 0.0)
    ax4.axis("off")
    ax4.text(
        0,
        0.9,
        "Timing",
        fontsize=12,
        fontweight="bold",
    )
    ax4.text(0, 0.7, f"Total wall-clock: {duration:.2f}s")
    ax4.text(0, 0.55, f"Avg per test: {avg_case:.3f}s")
    ax4.text(0, 0.4, f"Pass rate: {summary.get('pass_rate', 0.0):.2%}")
    ax4.text(0, 0.25, f"Query accuracy: {query_metrics.get('accuracy', 0.0):.2%}")

    plt.tight_layout()
    _ensure_parent(graph_path)
    fig.savefig(graph_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logging.info("Wrote summary graph to %s", graph_path)


def _render_progress_graph(
    progress_rows: List[Dict[str, Any]], graph_path: Path
) -> None:
    if not progress_rows:
        logging.warning("Skipping progress graph because no test data was recorded.")
        return

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        logging.error("matplotlib is required for graph generation: %s", exc)
        return

    indices = [row["index"] for row in progress_rows]
    pass_rates = [row["cumulative_pass_rate"] for row in progress_rows]
    query_accuracy = [row["cumulative_query_accuracy"] for row in progress_rows]
    durations = [row["duration_seconds"] for row in progress_rows]

    fig, (ax_top, ax_bottom) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax_top.plot(indices, pass_rates, label="Cumulative Pass Rate", color="#1f77b4")
    ax_top.plot(
        indices,
        query_accuracy,
        label="Cumulative Query Accuracy",
        color="#2ca02c",
        linestyle="--",
    )
    ax_top.set_ylabel("Rate")
    ax_top.set_ylim(0, 1.05)
    ax_top.legend(loc="lower right")
    ax_top.set_title("Run Progress")

    ax_bottom.bar(indices, durations, width=0.8, color="#ff9896")
    ax_bottom.set_ylabel("Duration (s)")
    ax_bottom.set_xlabel("Test Index")
    ax_bottom.set_title("Per-test Wall-clock Time")

    plt.tight_layout()
    _ensure_parent(graph_path)
    fig.savefig(graph_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logging.info("Wrote progress graph to %s", graph_path)


if __name__ == "__main__":
    main()
