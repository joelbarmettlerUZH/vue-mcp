"""Run evaluation: query the search pipeline and judge results with an LLM.

Loads questions from questions.json, runs each through the MCP server's
actual search pipeline (vue_docs_search), then uses Gemini as an LLM judge
to score retrieval quality and answer correctness.

Usage:
    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --questions eval/questions.json --output eval/results/
    uv run python eval/run_eval.py --max-questions 20
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from vue_docs_core.config import settings
from vue_docs_server.startup import startup, shutdown
from vue_docs_server.tools.search import vue_docs_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

JUDGE_PROMPT = """\
You are evaluating a documentation retrieval system for Vue.js. Given a developer \
question, the expected answer, and the retrieved documentation context, score the \
retrieval quality.

**Question:** {question}

**Expected Answer:** {expected_answer}

**Expected Relevant APIs:** {relevant_apis}

**Retrieved Context:**
{retrieved_context}

Score the following dimensions on a scale of 1-5:

1. **relevance**: How relevant is the retrieved context to the question? (1=completely irrelevant, 5=perfectly relevant)
2. **completeness**: Does the retrieved context contain enough information to fully answer the question? (1=missing everything, 5=complete answer possible)
3. **correctness**: If you were to answer the question using only the retrieved context, would the answer be correct? (1=would produce wrong answer, 5=would produce fully correct answer)
4. **api_coverage**: Are the expected APIs mentioned or covered in the retrieved context? (1=none found, 5=all found)

Also provide a brief explanation of your scoring.
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
                "description": "Brief explanation of the scoring.",
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


async def run_search(
    query: str,
    max_results: int = 10,
) -> tuple[str, float]:
    """Run a single search query through the actual server pipeline."""
    start = time.monotonic()
    result_text = await vue_docs_search(query, max_results=max_results)
    latency = time.monotonic() - start
    return result_text, latency


def judge_result(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    model: str | None = None,
) -> dict:
    """Use Gemini as LLM judge to score retrieval quality via function calling."""
    model = model or settings.gemini_flash_lite_model
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    prompt = JUDGE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        relevant_apis=", ".join(relevant_apis) if relevant_apis else "(none specified)",
        retrieved_context=retrieved_context[:8000],  # Truncate to stay within limits
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

    with httpx.Client(timeout=60.0) as client:
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
            # Ensure all keys exist with defaults
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
    import re

    scores: dict = {"explanation": text[:200]}
    for dim in ("relevance", "completeness", "correctness", "api_coverage"):
        # Match patterns like "relevance=4", "relevance: 4", "**relevance**: 3/5"
        match = re.search(rf"{dim}\s*[=:]\s*(\d)", text.lower())
        scores[dim] = int(match.group(1)) if match else 0

    if all(scores.get(d, 0) == 0 for d in ("relevance", "completeness", "correctness", "api_coverage")):
        raise RuntimeError(f"Could not parse scores from text response: {text[:100]}")

    return scores


async def run_evaluation(
    questions: list[dict],
    judge_model: str | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Run evaluation on all questions.

    Returns list of result dicts with question, scores, and latency.
    """
    results = []

    for i, q in enumerate(questions):
        question = q["question"]
        intent = q.get("intent", "unknown")
        difficulty = q.get("difficulty", "unknown")
        expected_answer = q.get("expected_answer", "")
        relevant_apis = q.get("relevant_apis", [])

        logger.info("[%d/%d] %s (intent=%s)", i + 1, len(questions), question[:80], intent)

        # Run search
        try:
            retrieved_context, latency = await run_search(
                question, max_results=max_results
            )
        except Exception as e:
            logger.error("Search failed for '%s': %s", question[:50], e)
            results.append({
                "question": question,
                "intent": intent,
                "difficulty": difficulty,
                "latency": 0,
                "scores": {"relevance": 0, "completeness": 0, "correctness": 0, "api_coverage": 0},
                "error": str(e),
            })
            continue

        # Judge with LLM (retry up to 5 times on transient errors)
        scores = None
        for attempt in range(5):
            try:
                scores = judge_result(
                    question=question,
                    expected_answer=expected_answer,
                    relevant_apis=relevant_apis,
                    retrieved_context=retrieved_context,
                    model=judge_model,
                )
                break
            except Exception as e:
                logger.warning("Judging attempt %d failed for '%s': %s", attempt + 1, question[:50], e)
                if attempt < 4:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        results.append({
            "question": question,
            "intent": intent,
            "difficulty": difficulty,
            "latency": round(latency, 3),
            "scores": scores,
            "retrieved_preview": retrieved_context[:500],
        })

        logger.info(
            "  -> relevance=%d completeness=%d correctness=%d api=%d latency=%.2fs",
            scores.get("relevance", 0),
            scores.get("completeness", 0),
            scores.get("correctness", 0),
            scores.get("api_coverage", 0),
            latency,
        )

    return results


def compute_metrics(results: list[dict]) -> dict:
    """Compute aggregate metrics from evaluation results."""
    if not results:
        return {}

    dimensions = ["relevance", "completeness", "correctness", "api_coverage"]

    # Overall metrics
    overall: dict[str, float] = {}
    for dim in dimensions:
        values = [r["scores"].get(dim, 0) for r in results if r["scores"].get(dim, 0) > 0]
        if values:
            overall[f"avg_{dim}"] = round(statistics.mean(values), 2)
            overall[f"median_{dim}"] = round(statistics.median(values), 2)

    # Composite score (average of all dimensions)
    composite_values = []
    for r in results:
        s = r["scores"]
        vals = [s.get(d, 0) for d in dimensions]
        if any(v > 0 for v in vals):
            composite_values.append(statistics.mean(vals))
    if composite_values:
        overall["avg_composite"] = round(statistics.mean(composite_values), 2)

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
        intent = r["intent"]
        intent_groups.setdefault(intent, []).append(r)

    for intent, group in intent_groups.items():
        intent_metrics: dict[str, float] = {"count": len(group)}
        for dim in dimensions:
            values = [r["scores"].get(dim, 0) for r in group if r["scores"].get(dim, 0) > 0]
            if values:
                intent_metrics[f"avg_{dim}"] = round(statistics.mean(values), 2)
        by_intent[intent] = intent_metrics

    # Per-difficulty metrics
    by_difficulty: dict[str, dict] = {}
    diff_groups: dict[str, list[dict]] = {}
    for r in results:
        diff = r["difficulty"]
        diff_groups.setdefault(diff, []).append(r)

    for diff, group in diff_groups.items():
        diff_metrics: dict[str, float] = {"count": len(group)}
        for dim in dimensions:
            values = [r["scores"].get(dim, 0) for r in group if r["scores"].get(dim, 0) > 0]
            if values:
                diff_metrics[f"avg_{dim}"] = round(statistics.mean(values), 2)
        by_difficulty[diff] = diff_metrics

    return {
        "overall": overall,
        "by_intent": by_intent,
        "by_difficulty": by_difficulty,
    }


def format_report(metrics: dict) -> str:
    """Format metrics as a human-readable report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("VUE DOCS MCP EVALUATION REPORT")
    lines.append("=" * 60)

    overall = metrics.get("overall", {})
    lines.append(f"\nTotal questions: {overall.get('total_questions', 0)}")
    lines.append(f"Errors: {overall.get('errors', 0)}")
    lines.append("")

    lines.append("OVERALL SCORES (1-5 scale):")
    lines.append(f"  Composite:    {overall.get('avg_composite', 'N/A')}")
    lines.append(f"  Relevance:    {overall.get('avg_relevance', 'N/A')} (median {overall.get('median_relevance', 'N/A')})")
    lines.append(f"  Completeness: {overall.get('avg_completeness', 'N/A')} (median {overall.get('median_completeness', 'N/A')})")
    lines.append(f"  Correctness:  {overall.get('avg_correctness', 'N/A')} (median {overall.get('median_correctness', 'N/A')})")
    lines.append(f"  API Coverage: {overall.get('avg_api_coverage', 'N/A')} (median {overall.get('median_api_coverage', 'N/A')})")

    lines.append(f"\nLATENCY:")
    lines.append(f"  Average: {overall.get('avg_latency', 'N/A')}s")
    lines.append(f"  P95:     {overall.get('p95_latency', 'N/A')}s")
    lines.append(f"  Max:     {overall.get('max_latency', 'N/A')}s")

    by_intent = metrics.get("by_intent", {})
    if by_intent:
        lines.append(f"\nBY INTENT:")
        for intent, m in sorted(by_intent.items()):
            lines.append(
                f"  {intent:15s} (n={m.get('count', 0):2d})  "
                f"rel={m.get('avg_relevance', 'N/A'):>4}  "
                f"comp={m.get('avg_completeness', 'N/A'):>4}  "
                f"corr={m.get('avg_correctness', 'N/A'):>4}  "
                f"api={m.get('avg_api_coverage', 'N/A'):>4}"
            )

    by_difficulty = metrics.get("by_difficulty", {})
    if by_difficulty:
        lines.append(f"\nBY DIFFICULTY:")
        for diff, m in sorted(by_difficulty.items()):
            lines.append(
                f"  {diff:10s} (n={m.get('count', 0):2d})  "
                f"rel={m.get('avg_relevance', 'N/A'):>4}  "
                f"comp={m.get('avg_completeness', 'N/A'):>4}  "
                f"corr={m.get('avg_correctness', 'N/A'):>4}  "
                f"api={m.get('avg_api_coverage', 'N/A'):>4}"
            )

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


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

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    results_path = output_dir / f"eval_{timestamp}.json"
    with open(results_path, "w") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "config": {
                    "max_results": args.max_results,
                    "judge_model": args.judge_model or settings.gemini_flash_lite_model,
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
        help="Gemini model for judging (default: gemini-2.5-flash-lite)",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
