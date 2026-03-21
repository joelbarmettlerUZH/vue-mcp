"""Metric computation: recall, precision, F1, and aggregation."""

import re
import statistics
from typing import Any

from vue_docs_eval.models import (
    ProviderMetrics,
    QuestionResult,
    RecallMetrics,
)

JUDGE_DIMS = ("relevance", "completeness", "correctness", "api_coverage", "verboseness")


def compute_recall(
    retrieved_context: str,
    relevant_paths: list[str],
    relevant_apis: list[str],
) -> RecallMetrics:
    """Compute deterministic retrieval metrics from retrieved context."""
    context_lower = retrieved_context.lower()

    # Path recall
    paths_found = 0
    for path in relevant_paths:
        slug = path.removeprefix("/").removesuffix(".md")
        if slug.lower() in context_lower:
            paths_found += 1

    # API recall
    apis_found = 0
    for api in relevant_apis:
        pattern = re.escape(api)
        if re.search(pattern, retrieved_context, re.IGNORECASE):
            apis_found += 1

    path_recall = paths_found / len(relevant_paths) if relevant_paths else 1.0
    api_recall = apis_found / len(relevant_apis) if relevant_apis else 1.0

    # Path precision: extract paths from the response and check against expected
    retrieved_paths = _extract_paths_from_context(retrieved_context)
    path_precision = None
    f1 = None
    if retrieved_paths and relevant_paths:
        expected_slugs = {p.removeprefix("/").removesuffix(".md").lower() for p in relevant_paths}
        matching = sum(1 for rp in retrieved_paths if rp.lower() in expected_slugs)
        path_precision = round(matching / len(retrieved_paths), 3)
        if path_recall + path_precision > 0:
            f1 = round(2 * path_precision * path_recall / (path_precision + path_recall), 3)

    return RecallMetrics(
        path_recall=round(path_recall, 3),
        api_recall=round(api_recall, 3),
        path_precision=path_precision,
        f1=f1,
        paths_found=paths_found,
        paths_expected=len(relevant_paths),
        apis_found=apis_found,
        apis_expected=len(relevant_apis),
    )


def _extract_paths_from_context(context: str) -> list[str]:
    """Extract documentation paths from retrieved context (URLs and source references)."""
    paths: set[str] = set()
    # Match patterns like vuejs.org/guide/essentials/computed or router.vuejs.org/guide/...
    for match in re.finditer(r"(?:vuejs\.org|router\.vuejs\.org)/([a-z0-9/_-]+)", context.lower()):
        paths.add(match.group(1).rstrip("/"))
    # Match source: lines in YAML frontmatter
    for match in re.finditer(r"source:\s*https?://[^/]+/([a-z0-9/_-]+)", context.lower()):
        paths.add(match.group(1).rstrip("/"))
    return list(paths)


def aggregate_results(provider_name: str, results: list[QuestionResult]) -> ProviderMetrics:
    """Compute aggregate metrics from per-question results."""
    if not results:
        return ProviderMetrics(provider=provider_name)

    overall = _aggregate_group(results)
    overall["total_questions"] = len(results)

    # By framework
    by_framework: dict[str, dict[str, Any]] = {}
    framework_groups: dict[str, list[QuestionResult]] = {}
    for r in results:
        framework_groups.setdefault(r.framework, []).append(r)
    for fw, group in framework_groups.items():
        by_framework[fw] = _aggregate_group(group)

    # By intent
    by_intent: dict[str, dict[str, Any]] = {}
    intent_groups: dict[str, list[QuestionResult]] = {}
    for r in results:
        intent_groups.setdefault(r.intent, []).append(r)
    for intent, group in intent_groups.items():
        by_intent[intent] = _aggregate_group(group)

    # By difficulty
    by_difficulty: dict[str, dict[str, Any]] = {}
    diff_groups: dict[str, list[QuestionResult]] = {}
    for r in results:
        diff_groups.setdefault(r.difficulty, []).append(r)
    for diff, group in diff_groups.items():
        by_difficulty[diff] = _aggregate_group(group)

    # Pass rates
    pass_rates: dict[str, dict[str, float]] = {}
    for threshold in (5, 4, 3, 2):
        key = f"gte_{threshold}"
        rates: dict[str, float] = {}
        for dim in JUDGE_DIMS:
            passing = sum(1 for r in results if getattr(r.scores, dim) >= threshold)
            rates[dim] = round(passing / len(results), 3)
        all_pass = sum(
            1 for r in results if all(getattr(r.scores, d) >= threshold for d in JUDGE_DIMS)
        )
        rates["all"] = round(all_pass / len(results), 3)
        pass_rates[key] = rates

    return ProviderMetrics(
        provider=provider_name,
        total_questions=len(results),
        results=results,
        overall=overall,
        by_framework=by_framework,
        by_intent=by_intent,
        by_difficulty=by_difficulty,
        pass_rates=pass_rates,
    )


def _aggregate_group(results: list[QuestionResult]) -> dict[str, Any]:
    """Compute aggregate stats for a group of results."""
    m: dict[str, Any] = {"count": len(results)}

    # Judge dimensions
    for dim in JUDGE_DIMS:
        values = [getattr(r.scores, dim) for r in results if getattr(r.scores, dim) > 0]
        if values:
            m[f"avg_{dim}"] = round(statistics.mean(values), 2)
            m[f"median_{dim}"] = round(statistics.median(values), 2)

    # Composite score
    composite_values = []
    for r in results:
        vals = [getattr(r.scores, d) for d in JUDGE_DIMS]
        if any(v > 0 for v in vals):
            composite_values.append(statistics.mean(vals))
    if composite_values:
        m["avg_composite"] = round(statistics.mean(composite_values), 2)

    # Recall
    path_recalls = [r.recall.path_recall for r in results]
    api_recalls = [r.recall.api_recall for r in results]
    m["avg_path_recall"] = round(statistics.mean(path_recalls), 3)
    m["avg_api_recall"] = round(statistics.mean(api_recalls), 3)

    # Precision and F1 (may be None for some providers)
    f1_values = [r.recall.f1 for r in results if r.recall.f1 is not None]
    if f1_values:
        m["avg_f1"] = round(statistics.mean(f1_values), 3)

    # Latency
    latencies = [r.search_result.latency_s for r in results if r.search_result.latency_s > 0]
    if latencies:
        m["avg_latency"] = round(statistics.mean(latencies), 3)
        m["p95_latency"] = round(sorted(latencies)[int(len(latencies) * 0.95)], 3)
        m["max_latency"] = round(max(latencies), 3)

    # Context size
    token_values = [r.context_tokens for r in results if r.context_tokens > 0]
    if token_values:
        m["avg_context_tokens"] = round(statistics.mean(token_values))
        m["max_context_tokens"] = max(token_values)

    # Cost
    internal_costs = [r.internal_cost_usd for r in results if r.internal_cost_usd is not None]
    if internal_costs:
        m["avg_internal_cost"] = round(statistics.mean(internal_costs), 6)
        m["total_internal_cost"] = round(sum(internal_costs), 4)

    external_costs = [r.external_cost_usd for r in results]
    m["avg_external_cost"] = round(statistics.mean(external_costs), 6)
    m["total_external_cost"] = round(sum(external_costs), 4)

    return m
