"""Orchestration: load questions, run providers, judge, aggregate."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_eval.cost import CONTEXT7_COST_PER_QUERY, jina_cost
from vue_docs_eval.judge import judge_stable
from vue_docs_eval.metrics import aggregate_results, compute_recall
from vue_docs_eval.models import (
    EvalQuestion,
    EvalReport,
    ProviderMetrics,
    QuestionResult,
)
from vue_docs_eval.providers.base import Provider
from vue_docs_eval.tokens import count_tokens

logger = logging.getLogger(__name__)


def load_questions(paths: list[Path]) -> list[EvalQuestion]:
    """Load questions from one or more JSON files."""
    questions: list[EvalQuestion] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Questions file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        for item in data:
            questions.append(EvalQuestion(**item))
        logger.info("Loaded %d questions from %s", len(data), path)
    return questions


async def run_evaluation(
    providers: list[Provider],
    questions: list[EvalQuestion],
    judge_model: str | None = None,
    judge_runs: int = 3,
    max_results: int = 10,
) -> EvalReport:
    """Run evaluation for all providers against all questions."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    gemini = GeminiClient(
        model=judge_model or "gemini-3.1-flash-lite-preview",
        timeout=120.0,
    )

    all_provider_metrics: list[ProviderMetrics] = []

    for provider in providers:
        logger.info("Starting provider: %s", provider.name)
        await provider.startup()

        try:
            results = await _eval_provider(
                provider=provider,
                questions=questions,
                gemini=gemini,
                judge_runs=judge_runs,
                max_results=max_results,
            )
        finally:
            await provider.shutdown()

        metrics = aggregate_results(provider.name, results)
        all_provider_metrics.append(metrics)

    await gemini.close()

    return EvalReport(
        timestamp=timestamp,
        config={
            "max_results": max_results,
            "judge_model": gemini.model,
            "judge_runs": judge_runs,
            "providers": [p.name for p in providers],
            "total_questions": len(questions),
        },
        providers=all_provider_metrics,
    )


async def _eval_provider(
    provider: Provider,
    questions: list[EvalQuestion],
    gemini: GeminiClient,
    judge_runs: int,
    max_results: int,
) -> list[QuestionResult]:
    """Evaluate a single provider against all questions."""
    results: list[QuestionResult] = []

    for i, q in enumerate(questions):
        logger.info(
            "[%s] [%d/%d] %s (framework=%s, intent=%s)",
            provider.name,
            i + 1,
            len(questions),
            q.question[:80],
            q.framework,
            q.intent,
        )

        search_result = await provider.search(q.question, q.framework, max_results)

        # Deterministic recall
        recall = compute_recall(search_result.text, q.relevant_paths, q.relevant_apis)

        # LLM judge
        scores = await judge_stable(
            question=q.question,
            expected_answer=q.expected_answer,
            relevant_apis=q.relevant_apis,
            retrieved_context=search_result.text,
            gemini=gemini,
            runs=judge_runs,
        )

        # Token count and cost
        context_tokens = count_tokens(search_result.text)
        internal_cost = jina_cost(search_result.embed_tokens, search_result.rerank_tokens)
        external_cost = CONTEXT7_COST_PER_QUERY if provider.name == "context7" else 0.0

        result = QuestionResult(
            question=q.question,
            framework=q.framework,
            intent=q.intent,
            difficulty=q.difficulty,
            provider=provider.name,
            search_result=search_result,
            recall=recall,
            scores=scores,
            context_tokens=context_tokens,
            internal_cost_usd=internal_cost,
            external_cost_usd=external_cost,
        )
        results.append(result)

        runs_str = " ".join(
            f"[{r.get('relevance', 0)}/{r.get('completeness', 0)}"
            f"/{r.get('correctness', 0)}/{r.get('api_coverage', 0)}"
            f"/{r.get('verboseness', 0)}]"
            for r in scores.runs
        )
        logger.info(
            "  -> rel=%d comp=%d corr=%d api=%d verb=%d | "
            "pR=%.0f%% aR=%.0f%% | %dtok %.3fs | runs: %s",
            scores.relevance,
            scores.completeness,
            scores.correctness,
            scores.api_coverage,
            scores.verboseness,
            recall.path_recall * 100,
            recall.api_recall * 100,
            context_tokens,
            search_result.latency_s,
            runs_str,
        )

    return results
