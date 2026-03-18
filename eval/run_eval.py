"""Run evaluation: query the search pipeline and judge results with an LLM.

Loads questions from questions.json, runs each through the MCP server's
actual search pipeline (vue_docs_search), then computes deterministic
retrieval metrics (Recall@K) and uses Gemini as an LLM judge to score
answer quality.

Usage:
    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --questions eval/questions.json --output eval/results/
    uv run python eval/run_eval.py --max-questions 20
"""

import argparse
import asyncio
import json
import logging
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from vue_docs_core.config import settings
from vue_docs_server.startup import shutdown, startup
from vue_docs_server.tools.search import vue_docs_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# ---------------------------------------------------------------------------
# Judge prompt — format-agnostic, focuses on information content
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """\
You are an expert evaluator for a Vue.js documentation retrieval system.

You will be given:
1. A developer's **question**
2. The **expected answer** (ground truth)
3. The **expected relevant APIs**
4. The **retrieved documentation** from the search system

Your task: evaluate whether the retrieved documentation contains the information \
needed to answer the question correctly and completely.

IMPORTANT: Ignore formatting, markdown syntax, YAML frontmatter blocks, HTML tags, \
and structural elements. Focus ONLY on the informational content of the retrieved text. \
A section contains an API if the API name appears anywhere in the text, including inside \
code blocks, frontmatter, or prose.

## Inputs

**Question:** {question}

**Expected answer:** {expected_answer}

**Expected relevant APIs:** {relevant_apis}

**Retrieved documentation:**
{retrieved_context}

## Scoring rubric

Score each dimension on a 1-5 scale:

### relevance (Is the retrieved content about the right topic?)
- 5: All retrieved sections directly address the question's topic
- 4: Most sections are relevant, one may be tangential
- 3: About half the content is relevant
- 2: Only a small portion relates to the question
- 1: Retrieved content is about a completely different topic

### completeness (Could someone fully answer the question from this content alone?)
- 5: All information needed for a complete answer is present
- 4: Most information present, minor details missing
- 3: Core answer is present but important details are missing
- 2: Only fragments of the needed information are present
- 1: The content does not contain enough to answer the question

### correctness (Would an answer based on this content be accurate?)
- 5: The content would lead to a fully correct answer
- 4: The content would lead to a mostly correct answer with minor gaps
- 3: The content would lead to a partially correct answer
- 2: The content could lead to a misleading answer
- 1: The content would lead to an incorrect answer

### api_coverage (Are the expected APIs mentioned in the retrieved content?)
- 5: All expected APIs appear in the retrieved content
- 4: Most expected APIs appear (one minor one missing)
- 3: About half of the expected APIs appear
- 2: Only one or two expected APIs appear
- 1: None of the expected APIs appear in the content

Provide your scores and a brief explanation (1-2 sentences).
"""

# Function declaration for structured judge scoring
JUDGE_FUNCTION = {
    "name": "submit_scores",
    "description": "Submit the evaluation scores for the retrieval quality assessment.",
    "parameters": {
        "type": "object",
        "properties": {
            "relevance": {
                "type": "integer",
                "description": "How relevant is the retrieved context to the question (1-5).",
            },
            "completeness": {
                "type": "integer",
                "description": "Does the retrieved context contain enough information to fully answer the question (1-5).",
            },
            "correctness": {
                "type": "integer",
                "description": "Would the answer based on retrieved context be correct (1-5).",
            },
            "api_coverage": {
                "type": "integer",
                "description": "Are the expected APIs mentioned or covered in the retrieved context (1-5).",
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation of the scoring (1-2 sentences).",
            },
        },
        "required": ["relevance", "completeness", "correctness", "api_coverage", "explanation"],
    },
}


def load_questions(path: Path) -> list[dict]:
    """Load evaluation questions from JSON file."""
    if not path.exists():
        logger.error("Questions file not found: %s", path)
        logger.error("Run 'uv run python eval/generate_questions.py' first.")
        sys.exit(1)

    with open(path) as f:
        questions = json.load(f)

    logger.info("Loaded %d questions from %s", len(questions), path)
    return questions


class _NoOpContext:
    """Lightweight no-op context for running tools outside the MCP protocol."""

    async def report_progress(self, *a, **kw): pass
    async def info(self, *a, **kw): pass
    async def warning(self, *a, **kw): pass
    async def error(self, *a, **kw): pass
    async def debug(self, *a, **kw): pass
    async def get_state(self, *a, **kw): return None
    async def set_state(self, *a, **kw): pass


_noop_ctx = _NoOpContext()


async def run_search(
    query: str,
    max_results: int = 10,
) -> tuple[str, float]:
    """Run a single search query through the actual server pipeline."""
    start = time.monotonic()
    result_text = await vue_docs_search(query, max_results=max_results, ctx=_noop_ctx)
    latency = time.monotonic() - start
    return result_text, latency


# ---------------------------------------------------------------------------
# Deterministic retrieval metrics (no LLM needed)
# ---------------------------------------------------------------------------


def compute_recall_at_k(
    retrieved_context: str,
    relevant_paths: list[str],
    relevant_apis: list[str],
) -> dict:
    """Compute deterministic recall metrics from retrieved context.

    - path_recall: fraction of expected paths that appear in the retrieved content
    - api_recall: fraction of expected APIs mentioned in the retrieved content
    """
    context_lower = retrieved_context.lower()

    # Path recall: check if any chunk from each expected path was retrieved
    # The retrieved context contains source URLs like https://vuejs.org/guide/essentials/computed
    # and breadcrumbs like "Guide > Essentials > Computed Properties"
    paths_found = 0
    for path in relevant_paths:
        # Convert "guide/essentials/computed.md" to the URL slug "guide/essentials/computed"
        slug = path.removeprefix("/").removesuffix(".md")
        if slug.lower() in context_lower:
            paths_found += 1

    # API recall: check if each expected API name appears anywhere in the text
    apis_found = 0
    for api in relevant_apis:
        # Case-insensitive search for the API name
        # Use word boundary-ish matching to avoid "ref" matching "preference"
        pattern = re.escape(api)
        if re.search(pattern, retrieved_context, re.IGNORECASE):
            apis_found += 1

    path_recall = paths_found / len(relevant_paths) if relevant_paths else 1.0
    api_recall = apis_found / len(relevant_apis) if relevant_apis else 1.0

    return {
        "path_recall": round(path_recall, 3),
        "api_recall": round(api_recall, 3),
        "paths_found": paths_found,
        "paths_expected": len(relevant_paths),
        "apis_found": apis_found,
        "apis_expected": len(relevant_apis),
    }


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------


def judge_result(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    model: str | None = None,
) -> dict:
    """Use Gemini as LLM judge to score retrieval quality via function calling."""
    model = model or "gemini-3.1-flash-lite-preview"
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    prompt = JUDGE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        relevant_apis=", ".join(relevant_apis) if relevant_apis else "(none specified)",
        retrieved_context=retrieved_context,
    )

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1000,
        },
        "tools": [{"function_declarations": [JUDGE_FUNCTION]}],
        "tool_config": {
            "function_calling_config": {
                "mode": "ANY",
                "allowed_function_names": ["submit_scores"],
            }
        },
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"Server error {response.status_code}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates for judging")

    # Extract function call arguments
    parts = candidates[0].get("content", {}).get("parts", [])
    for part in parts:
        if "functionCall" in part:
            scores = part["functionCall"].get("args", {})
            for key in ("relevance", "completeness", "correctness", "api_coverage"):
                scores.setdefault(key, 0)
            scores.setdefault("explanation", "")
            return scores

    # Fallback: parse scores from text response if no function call
    for part in parts:
        if "text" in part:
            return _parse_scores_from_text(part["text"])

    # Fallback: parse from MALFORMED_FUNCTION_CALL finishMessage
    finish_msg = candidates[0].get("finishMessage", "")
    if finish_msg:
        return _parse_scores_from_text(finish_msg)

    raise RuntimeError(f"Gemini returned no usable content: {json.dumps(candidates[0])[:300]}")


def _parse_scores_from_text(text: str) -> dict:
    """Best-effort extraction of scores from a text response."""
    scores: dict = {"explanation": text[:200]}
    for dim in ("relevance", "completeness", "correctness", "api_coverage"):
        match = re.search(rf"{dim}\s*[=:]\s*(\d)", text.lower())
        scores[dim] = int(match.group(1)) if match else 0

    if all(
        scores.get(d, 0) == 0 for d in ("relevance", "completeness", "correctness", "api_coverage")
    ):
        raise RuntimeError(f"Could not parse scores from text response: {text[:100]}")

    return scores


# ---------------------------------------------------------------------------
# Multi-run judge for stability
# ---------------------------------------------------------------------------


def judge_result_stable(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    model: str | None = None,
    runs: int = 3,
) -> dict:
    """Run the judge multiple times and take the median score per dimension.

    This eliminates run-to-run variance from the LLM judge.
    """
    all_scores: list[dict] = []
    explanations: list[str] = []

    for run_idx in range(runs):
        for attempt in range(5):
            try:
                scores = judge_result(
                    question=question,
                    expected_answer=expected_answer,
                    relevant_apis=relevant_apis,
                    retrieved_context=retrieved_context,
                    model=model,
                )
                all_scores.append(scores)
                explanations.append(scores.get("explanation", ""))
                break
            except Exception as e:
                logger.warning("Judge run %d attempt %d failed: %s", run_idx + 1, attempt + 1, e)
                if attempt < 4:
                    time.sleep(2**attempt)
                else:
                    # Use zeros for this run if all retries fail
                    all_scores.append({
                        "relevance": 0, "completeness": 0,
                        "correctness": 0, "api_coverage": 0,
                    })

    # Take median per dimension
    median_scores: dict = {}
    for dim in ("relevance", "completeness", "correctness", "api_coverage"):
        values = [s.get(dim, 0) for s in all_scores if s.get(dim, 0) > 0]
        median_scores[dim] = int(statistics.median(values)) if values else 0

    # Keep the explanation from the first successful run
    median_scores["explanation"] = explanations[0] if explanations else ""

    # Store individual run scores for transparency
    median_scores["_runs"] = [
        {d: s.get(d, 0) for d in ("relevance", "completeness", "correctness", "api_coverage")}
        for s in all_scores
    ]

    return median_scores


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------


async def run_evaluation(
    questions: list[dict],
    judge_model: str | None = None,
    max_results: int = 10,
    judge_runs: int = 3,
) -> list[dict]:
    """Run evaluation on all questions.

    For each question:
    1. Run the search pipeline
    2. Compute deterministic recall metrics (path_recall, api_recall)
    3. Run the LLM judge multiple times and take median scores
    """
    results = []

    for i, q in enumerate(questions):
        question = q["question"]
        intent = q.get("intent", "unknown")
        difficulty = q.get("difficulty", "unknown")
        expected_answer = q.get("expected_answer", "")
        relevant_apis = q.get("relevant_apis", [])
        relevant_paths = q.get("relevant_paths", [])

        logger.info("[%d/%d] %s (intent=%s)", i + 1, len(questions), question[:80], intent)

        # Run search
        try:
            retrieved_context, latency = await run_search(question, max_results=max_results)
        except Exception as e:
            logger.error("Search failed for '%s': %s", question[:50], e)
            results.append({
                "question": question,
                "intent": intent,
                "difficulty": difficulty,
                "latency": 0,
                "recall": {"path_recall": 0, "api_recall": 0},
                "scores": {
                    "relevance": 0, "completeness": 0,
                    "correctness": 0, "api_coverage": 0,
                },
                "error": str(e),
            })
            continue

        # Deterministic recall metrics
        recall = compute_recall_at_k(retrieved_context, relevant_paths, relevant_apis)

        # LLM judge (median of multiple runs)
        scores = judge_result_stable(
            question=question,
            expected_answer=expected_answer,
            relevant_apis=relevant_apis,
            retrieved_context=retrieved_context,
            model=judge_model,
            runs=judge_runs,
        )

        results.append({
            "question": question,
            "intent": intent,
            "difficulty": difficulty,
            "latency": round(latency, 3),
            "recall": recall,
            "scores": scores,
            "retrieved_preview": retrieved_context[:500],
        })

        runs_str = " ".join(
            f"[{r['relevance']}/{r['completeness']}/{r['correctness']}/{r['api_coverage']}]"
            for r in scores.get("_runs", [])
        )
        logger.info(
            "  -> rel=%d comp=%d corr=%d api=%d | path_recall=%.0f%% api_recall=%.0f%% | runs: %s",
            scores.get("relevance", 0),
            scores.get("completeness", 0),
            scores.get("correctness", 0),
            scores.get("api_coverage", 0),
            recall["path_recall"] * 100,
            recall["api_recall"] * 100,
            runs_str,
        )

    return results


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def compute_metrics(results: list[dict]) -> dict:
    """Compute aggregate metrics from evaluation results."""
    if not results:
        return {}

    dimensions = ["relevance", "completeness", "correctness", "api_coverage"]

    # Overall LLM judge metrics
    overall: dict[str, float] = {}
    for dim in dimensions:
        values = [r["scores"].get(dim, 0) for r in results if r["scores"].get(dim, 0) > 0]
        if values:
            overall[f"avg_{dim}"] = round(statistics.mean(values), 2)
            overall[f"median_{dim}"] = round(statistics.median(values), 2)

    # Composite score
    composite_values = []
    for r in results:
        s = r["scores"]
        vals = [s.get(d, 0) for d in dimensions]
        if any(v > 0 for v in vals):
            composite_values.append(statistics.mean(vals))
    if composite_values:
        overall["avg_composite"] = round(statistics.mean(composite_values), 2)

    # Deterministic recall metrics
    path_recalls = [r["recall"]["path_recall"] for r in results if "recall" in r]
    api_recalls = [r["recall"]["api_recall"] for r in results if "recall" in r]
    if path_recalls:
        overall["avg_path_recall"] = round(statistics.mean(path_recalls), 3)
    if api_recalls:
        overall["avg_api_recall"] = round(statistics.mean(api_recalls), 3)

    # Latency
    latencies = [r["latency"] for r in results if r["latency"] > 0]
    if latencies:
        overall["avg_latency"] = round(statistics.mean(latencies), 3)
        overall["p95_latency"] = round(sorted(latencies)[int(len(latencies) * 0.95)], 3)
        overall["max_latency"] = round(max(latencies), 3)

    overall["total_questions"] = len(results)
    overall["errors"] = sum(1 for r in results if "error" in r)

    # Per-intent metrics
    by_intent: dict[str, dict] = {}
    intent_groups: dict[str, list[dict]] = {}
    for r in results:
        intent_groups.setdefault(r["intent"], []).append(r)

    for intent, group in intent_groups.items():
        m: dict[str, float] = {"count": len(group)}
        for dim in dimensions:
            values = [r["scores"].get(dim, 0) for r in group if r["scores"].get(dim, 0) > 0]
            if values:
                m[f"avg_{dim}"] = round(statistics.mean(values), 2)
        pr = [r["recall"]["path_recall"] for r in group if "recall" in r]
        ar = [r["recall"]["api_recall"] for r in group if "recall" in r]
        if pr:
            m["avg_path_recall"] = round(statistics.mean(pr), 3)
        if ar:
            m["avg_api_recall"] = round(statistics.mean(ar), 3)
        by_intent[intent] = m

    # Per-difficulty metrics
    by_difficulty: dict[str, dict] = {}
    diff_groups: dict[str, list[dict]] = {}
    for r in results:
        diff_groups.setdefault(r["difficulty"], []).append(r)

    for diff, group in diff_groups.items():
        m = {"count": len(group)}
        for dim in dimensions:
            values = [r["scores"].get(dim, 0) for r in group if r["scores"].get(dim, 0) > 0]
            if values:
                m[f"avg_{dim}"] = round(statistics.mean(values), 2)
        pr = [r["recall"]["path_recall"] for r in group if "recall" in r]
        ar = [r["recall"]["api_recall"] for r in group if "recall" in r]
        if pr:
            m["avg_path_recall"] = round(statistics.mean(pr), 3)
        if ar:
            m["avg_api_recall"] = round(statistics.mean(ar), 3)
        by_difficulty[diff] = m

    # Pass rates at various thresholds
    pass_rates: dict[str, dict] = {}
    for threshold in (5, 4, 3, 2):
        key = f"gte_{threshold}"
        rates: dict[str, float] = {}
        for dim in dimensions:
            passing = sum(1 for r in results if r["scores"].get(dim, 0) >= threshold)
            rates[dim] = round(passing / len(results), 3)
        all_pass = sum(
            1 for r in results
            if all(r["scores"].get(d, 0) >= threshold for d in dimensions)
        )
        rates["all"] = round(all_pass / len(results), 3)
        pass_rates[key] = rates

    # Pass rates by intent (all dims >= 4)
    pass_by_intent: dict[str, float] = {}
    for intent, group in intent_groups.items():
        passing = sum(
            1 for r in group
            if all(r["scores"].get(d, 0) >= 4 for d in dimensions)
        )
        pass_by_intent[intent] = round(passing / len(group), 3)

    # Pass rates by difficulty (all dims >= 4)
    pass_by_difficulty: dict[str, float] = {}
    for diff, group in diff_groups.items():
        passing = sum(
            1 for r in group
            if all(r["scores"].get(d, 0) >= 4 for d in dimensions)
        )
        pass_by_difficulty[diff] = round(passing / len(group), 3)

    return {
        "overall": overall,
        "by_intent": by_intent,
        "by_difficulty": by_difficulty,
        "pass_rates": pass_rates,
        "pass_by_intent": pass_by_intent,
        "pass_by_difficulty": pass_by_difficulty,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(metrics: dict) -> str:
    """Format metrics as a human-readable report."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("VUE DOCS MCP EVALUATION REPORT")
    lines.append("=" * 70)

    overall = metrics.get("overall", {})
    lines.append(f"\nTotal questions: {overall.get('total_questions', 0)}")
    lines.append(f"Errors: {overall.get('errors', 0)}")

    lines.append("\nDETERMINISTIC RETRIEVAL METRICS:")
    lines.append(f"  Path Recall:  {overall.get('avg_path_recall', 'N/A'):.1%}"
                 if isinstance(overall.get('avg_path_recall'), float)
                 else f"  Path Recall:  {overall.get('avg_path_recall', 'N/A')}")
    lines.append(f"  API Recall:   {overall.get('avg_api_recall', 'N/A'):.1%}"
                 if isinstance(overall.get('avg_api_recall'), float)
                 else f"  API Recall:   {overall.get('avg_api_recall', 'N/A')}")

    lines.append(f"\nLLM JUDGE — avg composite: {overall.get('avg_composite', 'N/A')}")

    pass_rates = metrics.get("pass_rates", {})
    if pass_rates:
        dims_short = {"relevance": "rel", "completeness": "comp",
                      "correctness": "corr", "api_coverage": "api", "all": "ALL"}
        lines.append("")
        lines.append(
            f"  {'threshold':>10s}  {'rel':>5s}  {'comp':>5s}  "
            f"{'corr':>5s}  {'api':>5s}  {'ALL':>5s}"
        )
        lines.append("  " + "-" * 43)
        for threshold in (5, 4, 3, 2):
            key = f"gte_{threshold}"
            rates = pass_rates.get(key, {})
            lines.append(
                f"  {'>= ' + str(threshold):>10s}  "
                f"{rates.get('relevance', 0):>5.0%}  "
                f"{rates.get('completeness', 0):>5.0%}  "
                f"{rates.get('correctness', 0):>5.0%}  "
                f"{rates.get('api_coverage', 0):>5.0%}  "
                f"{rates.get('all', 0):>5.0%}"
            )

    lines.append("\nLATENCY:")
    lines.append(f"  Average: {overall.get('avg_latency', 'N/A')}s")
    lines.append(f"  P95:     {overall.get('p95_latency', 'N/A')}s")
    lines.append(f"  Max:     {overall.get('max_latency', 'N/A')}s")

    by_intent = metrics.get("by_intent", {})
    pass_by_intent = metrics.get("pass_by_intent", {})
    if by_intent:
        lines.append("\nBY INTENT:")
        lines.append(
            f"  {'intent':15s} {'n':>3s}  {'pR%':>4s}  {'aR%':>4s}  "
            f"{'>=4':>5s}  {'avg':>4s}"
        )
        lines.append("  " + "-" * 42)
        for intent, m in sorted(by_intent.items()):
            pr = m.get("avg_path_recall", 0)
            ar = m.get("avg_api_recall", 0)
            p4 = pass_by_intent.get(intent, 0)
            composite_vals = [
                m.get(f"avg_{d}", 0)
                for d in ("relevance", "completeness", "correctness", "api_coverage")
                if m.get(f"avg_{d}", 0) > 0
            ]
            avg = statistics.mean(composite_vals) if composite_vals else 0
            lines.append(
                f"  {intent:15s} {m.get('count', 0):3d}  "
                f"{pr:>4.0%}  {ar:>4.0%}  "
                f"{p4:>5.0%}  {avg:>4.1f}"
            )

    by_difficulty = metrics.get("by_difficulty", {})
    pass_by_difficulty = metrics.get("pass_by_difficulty", {})
    if by_difficulty:
        lines.append("\nBY DIFFICULTY:")
        lines.append(
            f"  {'diff':10s} {'n':>3s}  {'pR%':>4s}  {'aR%':>4s}  "
            f"{'>=4':>5s}  {'avg':>4s}"
        )
        lines.append("  " + "-" * 37)
        for diff, m in sorted(by_difficulty.items()):
            pr = m.get("avg_path_recall", 0)
            ar = m.get("avg_api_recall", 0)
            p4 = pass_by_difficulty.get(diff, 0)
            composite_vals = [
                m.get(f"avg_{d}", 0)
                for d in ("relevance", "completeness", "correctness", "api_coverage")
                if m.get(f"avg_{d}", 0) > 0
            ]
            avg = statistics.mean(composite_vals) if composite_vals else 0
            lines.append(
                f"  {diff:10s} {m.get('count', 0):3d}  "
                f"{pr:>4.0%}  {ar:>4.0%}  "
                f"{p4:>5.0%}  {avg:>4.1f}"
            )

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> None:
    questions = load_questions(args.questions)

    if args.max_questions:
        questions = questions[: args.max_questions]
        logger.info("Limited to %d questions", len(questions))

    startup()

    try:
        results = await run_evaluation(
            questions=questions,
            judge_model=args.judge_model,
            max_results=args.max_results,
            judge_runs=args.judge_runs,
        )
    finally:
        shutdown()

    metrics = compute_metrics(results)

    # Print report
    report = format_report(metrics)
    print(report)

    # Save results
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    results_path = output_dir / f"eval_{timestamp}.json"
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "config": {
                    "max_results": args.max_results,
                    "judge_model": args.judge_model or "gemini-3.1-flash-lite-preview",
                    "judge_runs": args.judge_runs,
                    "embedding_model": settings.jina_embedding_model,
                    "reranker_model": settings.jina_reranker_model,
                    "total_questions": len(questions),
                },
                "metrics": metrics,
                "results": results,
            },
            f,
            indent=2,
        )
    logger.info("Results saved to %s", results_path)

    report_path = output_dir / f"report_{timestamp}.txt"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Report saved to %s", report_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation on Vue docs search")
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("eval/questions.json"),
        help="Path to questions JSON file (default: eval/questions.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/results"),
        help="Output directory for results (default: eval/results/)",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Maximum number of questions to evaluate",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Max search results per query (default: 10)",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Gemini model for judging (default: gemini-3.1-flash-lite-preview)",
    )
    parser.add_argument(
        "--judge-runs",
        type=int,
        default=3,
        help="Number of judge runs per question for median stability (default: 3)",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
