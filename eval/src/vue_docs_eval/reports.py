"""Report formatting: ASCII tables and JSON output."""

import json
import statistics
from pathlib import Path
from typing import Any

from vue_docs_eval.models import EvalReport, ProviderMetrics

JUDGE_DIMS = ("relevance", "completeness", "correctness", "api_coverage", "verboseness")


def format_single_report(pm: ProviderMetrics) -> str:
    """Format metrics for a single provider as an ASCII table report."""
    lines: list[str] = []
    overall = pm.overall

    lines.append("=" * 70)
    lines.append(f"EVALUATION REPORT: {pm.provider.upper()}")
    lines.append("=" * 70)

    lines.append(f"\nTotal questions: {overall.get('total_questions', pm.total_questions)}")

    lines.append("\nDETERMINISTIC RETRIEVAL METRICS:")
    _append_pct(lines, "Path Recall", overall.get("avg_path_recall"))
    _append_pct(lines, "API Recall", overall.get("avg_api_recall"))
    _append_pct(lines, "F1", overall.get("avg_f1"))

    lines.append(f"\nLLM JUDGE (avg composite): {overall.get('avg_composite', 'N/A')}")

    if pm.pass_rates:
        lines.append("")
        header = f"  {'threshold':>10s}"
        for dim in JUDGE_DIMS:
            header += f"  {dim[:4]:>5s}"
        header += f"  {'ALL':>5s}"
        lines.append(header)
        lines.append("  " + "-" * (15 + 6 * (len(JUDGE_DIMS) + 1)))
        for threshold in (5, 4, 3, 2):
            key = f"gte_{threshold}"
            rates = pm.pass_rates.get(key, {})
            row = f"  {'>= ' + str(threshold):>10s}"
            for dim in JUDGE_DIMS:
                row += f"  {rates.get(dim, 0):>5.0%}"
            row += f"  {rates.get('all', 0):>5.0%}"
            lines.append(row)

    lines.append("\nLATENCY & CONTEXT:")
    lines.append(f"  Avg latency:  {overall.get('avg_latency', 'N/A')}s")
    lines.append(f"  P95 latency:  {overall.get('p95_latency', 'N/A')}s")
    lines.append(f"  Avg tokens:   {overall.get('avg_context_tokens', 'N/A')}")
    lines.append(f"  Max tokens:   {overall.get('max_context_tokens', 'N/A')}")

    lines.append("\nCOST:")
    if "avg_internal_cost" in overall:
        lines.append(f"  Avg internal: ${overall['avg_internal_cost']:.6f}/query")
        lines.append(f"  Total internal: ${overall.get('total_internal_cost', 0):.4f}")
    lines.append(f"  Avg external: ${overall.get('avg_external_cost', 0):.6f}/query")

    # By intent
    if pm.by_intent:
        lines.append("\nBY INTENT:")
        lines.append(
            f"  {'intent':15s} {'n':>3s}  {'pR%':>4s}  {'aR%':>4s}  {'avg':>4s}  {'lat':>5s}"
        )
        lines.append("  " + "-" * 40)
        for intent, m in sorted(pm.by_intent.items()):
            composite_vals = [m.get(f"avg_{d}", 0) for d in JUDGE_DIMS if m.get(f"avg_{d}", 0) > 0]
            avg = statistics.mean(composite_vals) if composite_vals else 0
            lines.append(
                f"  {intent:15s} {m.get('count', 0):3d}  "
                f"{m.get('avg_path_recall', 0):>4.0%}  "
                f"{m.get('avg_api_recall', 0):>4.0%}  "
                f"{avg:>4.1f}  "
                f"{m.get('avg_latency', 0):>5.2f}s"
            )

    # By difficulty
    if pm.by_difficulty:
        lines.append("\nBY DIFFICULTY:")
        lines.append(
            f"  {'diff':10s} {'n':>3s}  {'pR%':>4s}  {'aR%':>4s}  {'avg':>4s}  {'lat':>5s}"
        )
        lines.append("  " + "-" * 37)
        for diff, m in sorted(pm.by_difficulty.items()):
            composite_vals = [m.get(f"avg_{d}", 0) for d in JUDGE_DIMS if m.get(f"avg_{d}", 0) > 0]
            avg = statistics.mean(composite_vals) if composite_vals else 0
            lines.append(
                f"  {diff:10s} {m.get('count', 0):3d}  "
                f"{m.get('avg_path_recall', 0):>4.0%}  "
                f"{m.get('avg_api_recall', 0):>4.0%}  "
                f"{avg:>4.1f}  "
                f"{m.get('avg_latency', 0):>5.2f}s"
            )

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def format_comparison_report(report: EvalReport) -> str:
    """Format a side-by-side comparison of multiple providers."""
    if len(report.providers) < 2:
        return format_single_report(report.providers[0]) if report.providers else ""

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("COMPARISON REPORT")
    lines.append("=" * 70)

    providers = report.providers
    names = [p.provider for p in providers]
    header = f"  {'metric':25s}" + "".join(f"  {n:>15s}" for n in names)
    lines.append(f"\n{header}")
    lines.append("  " + "-" * (25 + 17 * len(names)))

    # Metrics to compare
    metric_rows = [
        ("Questions", "total_questions", "d"),
        ("Avg Path Recall", "avg_path_recall", "%"),
        ("Avg API Recall", "avg_api_recall", "%"),
        ("Avg F1", "avg_f1", "%"),
        ("Avg Composite", "avg_composite", ".2f"),
        ("Avg Latency (s)", "avg_latency", ".3f"),
        ("P95 Latency (s)", "p95_latency", ".3f"),
        ("Avg Tokens", "avg_context_tokens", "d"),
        ("Avg Internal Cost", "avg_internal_cost", "$.6f"),
        ("Avg External Cost", "avg_external_cost", "$.6f"),
    ]

    for label, key, fmt in metric_rows:
        row = f"  {label:25s}"
        for p in providers:
            val = p.overall.get(key)
            if val is None:
                row += f"  {'N/A':>15s}"
            elif fmt == "%":
                row += f"  {val:>14.1%} "
            elif fmt.startswith("$"):
                row += f"  ${val:>13.6f} "
            elif fmt == "d":
                row += f"  {val:>15d}"
            else:
                row += f"  {val:>15{fmt}}"
        lines.append(row)

    # Per-dimension judge scores
    lines.append(f"\n  {'JUDGE DIMENSIONS':25s}" + "".join(f"  {n:>15s}" for n in names))
    lines.append("  " + "-" * (25 + 17 * len(names)))
    for dim in JUDGE_DIMS:
        row = f"  {dim:25s}"
        for p in providers:
            val = p.overall.get(f"avg_{dim}")
            row += f"  {val:>15.2f}" if val is not None else f"  {'N/A':>15s}"
        lines.append(row)

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def save_report(report: EvalReport, output_dir: Path, timestamp: str) -> tuple[Path, Path]:
    """Save JSON results and ASCII report to files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / f"eval_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    # ASCII
    if len(report.providers) > 1:
        text = format_comparison_report(report)
    else:
        text = format_single_report(report.providers[0]) if report.providers else ""

    report_path = output_dir / f"report_{timestamp}.txt"
    with open(report_path, "w") as f:
        f.write(text)

    return json_path, report_path


def _append_pct(lines: list[str], label: str, value: Any) -> None:
    if isinstance(value, float):
        lines.append(f"  {label:15s} {value:.1%}")
    else:
        lines.append(f"  {label:15s} {value or 'N/A'}")
