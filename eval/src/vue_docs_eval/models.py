"""Pydantic models for evaluation data structures."""

from typing import Annotated, Any

from pydantic import BaseModel, Field


class EvalQuestion(BaseModel):
    """A single evaluation question with ground truth."""

    question: Annotated[str, Field(description="The developer question in natural language")]
    framework: Annotated[str, Field(description="Framework identifier (e.g. 'vue', 'vue-router')")]
    intent: Annotated[str, Field(description="Question intent category")]
    difficulty: Annotated[str, Field(description="Difficulty level: easy, medium, hard")]
    expected_answer: Annotated[str, Field(description="Ground truth answer (2-5 sentences)")]
    relevant_paths: Annotated[
        list[str], Field(description="Documentation file paths containing the answer")
    ]
    relevant_apis: Annotated[list[str], Field(description="API names relevant to the answer")]


class SearchResult(BaseModel):
    """Result from a single search query against a provider."""

    text: Annotated[str, Field(description="Retrieved documentation text")]
    latency_s: Annotated[float, Field(description="Wall-clock latency in seconds")]
    embed_tokens: Annotated[
        int | None, Field(description="Jina embedding tokens consumed (ours only)")
    ] = None
    rerank_tokens: Annotated[
        int | None, Field(description="Jina reranking tokens consumed (ours only)")
    ] = None


class JudgeScores(BaseModel):
    """LLM judge scores for a single evaluation."""

    relevance: Annotated[int, Field(ge=1, le=5, description="Topic relevance (1-5)")]
    completeness: Annotated[int, Field(ge=1, le=5, description="Answer completeness (1-5)")]
    correctness: Annotated[int, Field(ge=1, le=5, description="Answer correctness (1-5)")]
    api_coverage: Annotated[int, Field(ge=1, le=5, description="Expected API coverage (1-5)")]
    verboseness: Annotated[
        int, Field(ge=1, le=5, description="Conciseness (5=best, 1=too verbose)")
    ]
    explanation: Annotated[str, Field(description="Brief judge explanation")]
    runs: Annotated[
        list[dict[str, int]], Field(description="Individual run scores for transparency")
    ] = []


class RecallMetrics(BaseModel):
    """Deterministic retrieval metrics."""

    path_recall: Annotated[float, Field(description="Fraction of expected paths found")]
    api_recall: Annotated[float, Field(description="Fraction of expected APIs found")]
    path_precision: Annotated[
        float | None, Field(description="Fraction of retrieved paths in expected set")
    ] = None
    f1: Annotated[float | None, Field(description="Harmonic mean of precision and recall")] = None
    paths_found: int = 0
    paths_expected: int = 0
    apis_found: int = 0
    apis_expected: int = 0


class QuestionResult(BaseModel):
    """Complete evaluation result for a single question against a single provider."""

    question: str
    framework: str
    intent: str
    difficulty: str
    provider: str
    search_result: SearchResult
    recall: RecallMetrics
    scores: JudgeScores
    context_tokens: Annotated[int, Field(description="Accurate token count via tiktoken")]
    internal_cost_usd: Annotated[float | None, Field(description="Our API cost per query")] = None
    external_cost_usd: Annotated[float, Field(description="User-facing cost per query")] = 0.0


class ProviderMetrics(BaseModel):
    """Aggregate metrics for a single provider."""

    provider: str
    total_questions: int = 0
    results: list[QuestionResult] = []
    overall: dict[str, Any] = {}
    by_framework: dict[str, dict[str, Any]] = {}
    by_intent: dict[str, dict[str, Any]] = {}
    by_difficulty: dict[str, dict[str, Any]] = {}
    pass_rates: dict[str, dict[str, float]] = {}


class EvalReport(BaseModel):
    """Complete evaluation report, potentially comparing multiple providers."""

    timestamp: str
    config: dict[str, Any] = {}
    providers: list[ProviderMetrics] = []
