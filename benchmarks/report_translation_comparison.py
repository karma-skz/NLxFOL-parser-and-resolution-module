from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.metrics import aggregate_translation_rows


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _flatten(metrics: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for key, value in metrics.items():
        dotted = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, dotted))
        else:
            flat[dotted] = value
    return flat


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _format_delta(a: Any, b: Any) -> str:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        delta = b - a
        return f"{delta:+.6f}"
    return "-"


def _render_table(
    label_a: str, summary_a: Dict[str, Any], label_b: str, summary_b: Dict[str, Any]
) -> str:
    flat_a = _flatten(summary_a)
    flat_b = _flatten(summary_b)
    keys = sorted(set(flat_a) | set(flat_b))
    header = f"{'Metric':40} {label_a:>20} {label_b:>20} " "{'Delta (b-a)':>15}"
    lines = [header, "-" * len(header)]
    for key in keys:
        a = flat_a.get(key)
        b = flat_b.get(key)
        lines.append(
            f"{key:40} {_format_value(a):>20} {_format_value(b):>20} {_format_delta(a, b):>15}"
        )
    return "\n".join(lines)


def evaluate_rows(path: Path) -> Dict[str, Any]:
    rows = _read_jsonl(path)
    return aggregate_translation_rows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate parser + Gemini JSONL outputs and emit a comparison report "
            "similar to outputs/folio/comparison.txt."
        )
    )
    parser.add_argument(
        "--parser-rows",
        type=Path,
        required=True,
        help="Path to the rule-based parser rows JSONL file",
    )
    parser.add_argument(
        "--gemini-rows",
        type=Path,
        required=True,
        help="Path to the Gemini rows JSONL file",
    )
    parser.add_argument(
        "--parser-summary",
        type=Path,
        default=None,
        help="Optional path to save the parser summary JSON",
    )
    parser.add_argument(
        "--gemini-summary",
        type=Path,
        default=None,
        help="Optional path to save the Gemini summary JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the formatted comparison table",
    )
    parser.add_argument(
        "--parser-label",
        default="Parser",
        help="Label for the parser column (default: Parser)",
    )
    parser.add_argument(
        "--gemini-label",
        default="Gemini",
        help="Label for the Gemini column (default: Gemini)",
    )
    parser.add_argument(
        "--graph-output",
        type=Path,
        default=None,
        help="Optional path to save a PNG figure comparing the summaries.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parser_summary = evaluate_rows(args.parser_rows)
    gemini_summary = evaluate_rows(args.gemini_rows)

    if args.parser_summary:
        _write_json(args.parser_summary, parser_summary)
    if args.gemini_summary:
        _write_json(args.gemini_summary, gemini_summary)

    table = _render_table(
        args.parser_label, parser_summary, args.gemini_label, gemini_summary
    )
    print(table)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(table + "\n", encoding="utf-8")

    if args.graph_output:
        _render_graphs(
            args.parser_label,
            parser_summary,
            args.gemini_label,
            gemini_summary,
            args.graph_output,
        )


def _validator_rates(summary: Dict[str, Any]) -> Dict[str, float]:
    validators = summary.get("validators") or {}
    rates: Dict[str, float] = {}
    for name, counts in validators.items():
        total = counts.get("passed", 0) + counts.get("failed", 0)
        if total:
            rates[name] = counts.get("passed", 0) / total
    return rates


def _render_graphs(
    label_a: str,
    summary_a: Dict[str, Any],
    label_b: str,
    summary_b: Dict[str, Any],
    graph_path: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(f"[graph] matplotlib is required to render plots: {exc}", file=sys.stderr)
        return

    totals = [summary_a.get("total_sentences", 0), summary_b.get("total_sentences", 0)]
    translated = [summary_a.get("translations", 0), summary_b.get("translations", 0)]
    untranslated = [max(total - trans, 0) for total, trans in zip(totals, translated)]

    flat_a = _flatten(summary_a)
    flat_b = _flatten(summary_b)
    metric_keys = [
        ("translation_rate", "Translation Rate"),
        ("parsing_metrics.exact_match", "Exact Match"),
        ("parsing_metrics.predicate_f1", "Predicate F1"),
        ("parsing_metrics.bleu", "BLEU"),
        ("parsing_metrics.tree_similarity", "Tree Similarity"),
    ]

    rates_a = _validator_rates(summary_a)
    rates_b = _validator_rates(summary_b)
    validator_names = sorted(set(rates_a) | set(rates_b))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax1, ax2, ax3, ax4 = axes.flatten()

    x = range(2)
    width = 0.35
    ax1.bar(
        [i - width / 2 for i in x],
        translated,
        width,
        label="Translated",
        color="#2ca02c",
    )
    ax1.bar(
        [i + width / 2 for i in x],
        untranslated,
        width,
        label="Untranslated",
        color="#d62728",
    )
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([label_a, label_b])
    ax1.set_ylabel("Sentences")
    ax1.set_title("Translation Coverage")
    ax1.legend()

    indices = range(len(metric_keys))
    bars_a = [flat_a.get(key, 0.0) for key, _ in metric_keys]
    bars_b = [flat_b.get(key, 0.0) for key, _ in metric_keys]
    width_metric = 0.35
    ax2.bar(
        [i - width_metric / 2 for i in indices],
        bars_a,
        width_metric,
        label=label_a,
        color="#1f77b4",
    )
    ax2.bar(
        [i + width_metric / 2 for i in indices],
        bars_b,
        width_metric,
        label=label_b,
        color="#ff7f0e",
    )
    ax2.set_xticks(list(indices))
    ax2.set_xticklabels([label for _, label in metric_keys], rotation=20)
    ax2.set_ylim(0, 1)
    ax2.set_title("Quality Metrics")
    ax2.legend()

    if validator_names:
        idx = range(len(validator_names))
        vals_a = [rates_a.get(name, 0.0) for name in validator_names]
        vals_b = [rates_b.get(name, 0.0) for name in validator_names]
        ax3.bar(
            [i - width_metric / 2 for i in idx],
            vals_a,
            width_metric,
            label=label_a,
            color="#17becf",
        )
        ax3.bar(
            [i + width_metric / 2 for i in idx],
            vals_b,
            width_metric,
            label=label_b,
            color="#bcbd22",
        )
        ax3.set_xticks(list(idx))
        ax3.set_xticklabels(validator_names, rotation=20)
        ax3.set_ylim(0, 1)
        ax3.set_ylabel("Pass Rate")
        ax3.set_title("Validator Agreement")
        ax3.legend()
    else:
        ax3.axis("off")
        ax3.text(0.5, 0.5, "No validator stats", ha="center", va="center")

    ax4.axis("off")
    ax4.set_title("Highlights", loc="left")
    lines = [
        f"{label_a} translation rate: {flat_a.get('translation_rate', 0.0):.2%}",
        f"{label_b} translation rate: {flat_b.get('translation_rate', 0.0):.2%}",
        f"Δ translation rate: {flat_b.get('translation_rate', 0.0) - flat_a.get('translation_rate', 0.0):+.2%}",
        f"{label_a} exact match: {flat_a.get('parsing_metrics.exact_match', 0.0):.2%}",
        f"{label_b} exact match: {flat_b.get('parsing_metrics.exact_match', 0.0):.2%}",
    ]
    y = 0.9
    for text in lines:
        ax4.text(0.02, y, text)
        y -= 0.12

    plt.tight_layout()
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(graph_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
