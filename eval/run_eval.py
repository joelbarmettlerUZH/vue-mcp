"""Run evaluation: query the search pipeline and judge results with an LLM.

Loads questions from questions.json, runs each through the MCP server's search
pipeline, then uses Gemini as an LLM judge to score retrieval quality and
answer correctness.

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
from vue_docs_core.clients.jina import JinaClient, TASK_RETRIEVAL_QUERY
from vue_docs_core.clients.bm25 import BM25Model
from vue_docs_core.clients.qdrant import QdrantDocClient
from vue_docs_core.models.entity import EntityIndex, ApiEntity
from vue_docs_core.retrieval.entity_matcher import EntityMatcher
from vue_docs_core.retrieval.reconstruction import reconstruct_results

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

Return a JSON object with: "relevance", "completeness", "correctness", "api_coverage" (integers 1-5), and "explanation" (string).
Output ONLY valid JSON, no markdown fences.
"""


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


def load_server_state() -> tuple[QdrantDocClient, BM25Model, EntityMatcher]:
    """Load server state for running searches."""
    data_path = Path(settings.data_path)

    # Entity index
    dict_path = data_path / "entity_dictionary.json"
    entity_index = EntityIndex()
    if dict_path.exists():
        with open(dict_path) as f:
            raw = json.load(f)
        entities = {}
        for name, info in raw.items():
            entities[name] = ApiEntity(
                name=name,
                entity_type=info.get("entity_type", "other"),
                page_path=info.get("page_path", ""),
                section=info.get("section", ""),
                related=info.get("related", []),
            )
        entity_index = EntityIndex(entities=entities)
        logger.info("Loaded %d API entities", len(entities))

    # Synonym table
    syn_path = data_path / "synonym_table.json"
    synonym_table: dict[str, list[str]] = {}
    if syn_path.exists():
        with open(syn_path) as f:
            synonym_table = json.load(f)

    # BM25
    bm25 = BM25Model()
    bm25_path = data_path / "bm25_model"
    if bm25_path.exists():
        bm25.load(bm25_path)
        logger.info("BM25 model loaded")

    # Entity matcher
    matcher = EntityMatcher(entity_index=entity_index, synonym_table=synonym_table)

    # Qdrant
    qdrant = QdrantDocClient()
    info = qdrant.collection_info()
    logger.info("Qdrant connected: %d points", info["points_count"])

    return qdrant, bm25, matcher


async def run_search(
    query: str,
    qdrant: QdrantDocClient,
    bm25: BM25Model,
    matcher: EntityMatcher,
    max_results: int = 10,
) -> tuple[str, float]:
    """Run a single search query and return (results_text, latency_seconds)."""
    start = time.monotonic()

    # Embed query
    jina = JinaClient()
    try:
        embed_result = await jina.embed([query], task=TASK_RETRIEVAL_QUERY)
        if not embed_result.embeddings:
            return "Error: embedding failed", time.monotonic() - start
        dense_vector = embed_result.embeddings[0]
    finally:
        await jina.close()

    # BM25 sparse vector
    sparse_vector = bm25.get_query_sparse_vector(query)

    # Entity detection for boosting
    match_result = matcher.match(query)
    entity_boost = match_result.entities if match_result.entities else None

    # Hybrid search
    hits = qdrant.hybrid_search(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        limit=max_results * 3,
        entity_boost=entity_boost,
    )

    if not hits:
        return "No results found.", time.monotonic() - start

    result_text = reconstruct_results(hits, max_results=max_results)
    latency = time.monotonic() - start
    return result_text, latency


def judge_result(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    model: str | None = None,
) -> dict:
    """Use Gemini as LLM judge to score retrieval quality."""
    model = model or settings.gemini_flash_lite_model
    api_key = settings.gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return {"relevance": 0, "completeness": 0, "correctness": 0, "api_coverage": 0, "explanation": "No API key"}

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
            "temperature": 0.1,
            "maxOutputTokens": 1000,
            "responseMimeType": "application/json",
        },
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        return {"relevance": 0, "completeness": 0, "correctness": 0, "api_coverage": 0, "explanation": "No response"}

    text = candidates[0]["content"]["parts"][0]["text"].strip()

    # Parse JSON
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]

    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse judge response: %s", text[:200])
        return {"relevance": 0, "completeness": 0, "correctness": 0, "api_coverage": 0, "explanation": "Parse error"}

    # Ensure all keys exist with defaults
    for key in ("relevance", "completeness", "correctness", "api_coverage"):
        scores.setdefault(key, 0)
    scores.setdefault("explanation", "")

    return scores


async def run_evaluation(
    questions: list[dict],
    qdrant: QdrantDocClient,
    bm25: BM25Model,
    matcher: EntityMatcher,
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
                question, qdrant, bm25, matcher, max_results=max_results
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

        # Judge with LLM
        try:
            scores = judge_result(
                question=question,
                expected_answer=expected_answer,
                relevant_apis=relevant_apis,
                retrieved_context=retrieved_context,
                model=judge_model,
            )
        except Exception as e:
            logger.error("Judging failed for '%s': %s", question[:50], e)
            scores = {"relevance": 0, "completeness": 0, "correctness": 0, "api_coverage": 0, "explanation": str(e)}

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

    qdrant, bm25, matcher = load_server_state()

    try:
        results = await run_evaluation(
            questions=questions,
            qdrant=qdrant,
            bm25=bm25,
            matcher=matcher,
            judge_model=args.judge_model,
            max_results=args.max_results,
        )
    finally:
        qdrant.close()

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
