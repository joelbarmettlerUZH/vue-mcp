"""LLM judge using GeminiClient with structured function calling."""

import asyncio
import logging
import statistics

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_eval.models import JudgeScores

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_INSTRUCTION = """\
You are an expert evaluator for a documentation retrieval system. \
Evaluate whether the retrieved documentation contains the information \
needed to answer the question correctly and completely.

IMPORTANT: Ignore formatting, markdown syntax, YAML frontmatter blocks, HTML tags, \
and structural elements. Focus ONLY on the informational content of the retrieved text. \
A section contains an API if the API name appears anywhere in the text, including inside \
code blocks, frontmatter, or prose.

Score each dimension on a 1-5 scale:

relevance (Is the retrieved content about the right topic?)
- 5: All retrieved sections directly address the question's topic
- 4: Most sections are relevant, one may be tangential
- 3: About half the content is relevant
- 2: Only a small portion relates to the question
- 1: Retrieved content is about a completely different topic

completeness (Could someone fully answer the question from this content alone?)
- 5: All information needed for a complete answer is present
- 4: Most information present, minor details missing
- 3: Core answer is present but important details are missing
- 2: Only fragments of the needed information are present
- 1: The content does not contain enough to answer the question

correctness (Would an answer based on this content be accurate?)
- 5: The content would lead to a fully correct answer
- 4: The content would lead to a mostly correct answer with minor gaps
- 3: The content would lead to a partially correct answer
- 2: The content could lead to a misleading answer
- 1: The content would lead to an incorrect answer

api_coverage (Are the expected APIs mentioned in the retrieved content?)
- 5: All expected APIs appear in the retrieved content
- 4: Most expected APIs appear (one minor one missing)
- 3: About half of the expected APIs appear
- 2: Only one or two expected APIs appear
- 1: None of the expected APIs appear in the content

verboseness (Is the retrieved content appropriately concise?)
- 5: Content is focused and concise, minimal irrelevant padding
- 4: Mostly concise, a small amount of tangential content
- 3: Moderate amount of unnecessary content mixed with relevant parts
- 2: Significant padding or boilerplate diluting the useful information
- 1: Mostly irrelevant content, the answer is buried in noise
"""

JUDGE_FUNCTION_SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {
            "type": "integer",
            "description": "How relevant is the retrieved context to the question (1-5).",
        },
        "completeness": {
            "type": "integer",
            "description": "Does the context contain enough to fully answer the question (1-5).",
        },
        "correctness": {
            "type": "integer",
            "description": "Would the answer based on retrieved context be correct (1-5).",
        },
        "api_coverage": {
            "type": "integer",
            "description": "Are expected APIs covered in the retrieved context (1-5).",
        },
        "verboseness": {
            "type": "integer",
            "description": "Is the content appropriately concise (5=best, 1=too verbose).",
        },
        "explanation": {
            "type": "string",
            "description": "Brief explanation of the scoring (1-2 sentences).",
        },
    },
    "required": [
        "relevance",
        "completeness",
        "correctness",
        "api_coverage",
        "verboseness",
        "explanation",
    ],
}

SCORE_DIMS = ("relevance", "completeness", "correctness", "api_coverage", "verboseness")


async def _judge_once(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    gemini: GeminiClient,
) -> dict:
    """Run a single judge call via GeminiClient function calling."""
    apis_str = ", ".join(relevant_apis) if relevant_apis else "(none specified)"

    prompt = (
        f"**Question:** {question}\n\n"
        f"**Expected answer:** {expected_answer}\n\n"
        f"**Expected relevant APIs:** {apis_str}\n\n"
        f"**Retrieved documentation:**\n{retrieved_context}"
    )

    result = await gemini.generate_with_tool(
        prompt,
        function_name="submit_scores",
        function_description="Submit the evaluation scores for the retrieval quality assessment.",
        parameters_schema=JUDGE_FUNCTION_SCHEMA,
        system_instruction=JUDGE_SYSTEM_INSTRUCTION,
        temperature=0.0,
        max_output_tokens=1000,
    )

    scores = dict(result.arguments)
    for key in SCORE_DIMS:
        scores.setdefault(key, 0)
    scores.setdefault("explanation", "")
    return scores


async def judge_stable(
    question: str,
    expected_answer: str,
    relevant_apis: list[str],
    retrieved_context: str,
    gemini: GeminiClient,
    runs: int = 3,
) -> JudgeScores:
    """Run the judge multiple times and take the median score per dimension."""
    all_scores: list[dict] = []
    explanations: list[str] = []

    for run_idx in range(runs):
        for attempt in range(5):
            try:
                scores = await _judge_once(
                    question=question,
                    expected_answer=expected_answer,
                    relevant_apis=relevant_apis,
                    retrieved_context=retrieved_context,
                    gemini=gemini,
                )
                all_scores.append(scores)
                explanations.append(scores.get("explanation", ""))
                break
            except Exception as e:
                logger.warning("Judge run %d attempt %d failed: %s", run_idx + 1, attempt + 1, e)
                if attempt < 4:
                    await asyncio.sleep(2**attempt)
                else:
                    raise RuntimeError(f"Judge failed after 5 attempts for: {question[:60]}") from e

    median_scores: dict[str, int] = {}
    for dim in SCORE_DIMS:
        values = [s.get(dim, 0) for s in all_scores if s.get(dim, 0) > 0]
        median_scores[dim] = int(statistics.median(values)) if values else 0

    run_dicts = [{d: s.get(d, 0) for d in SCORE_DIMS} for s in all_scores]

    return JudgeScores(
        **median_scores,
        explanation=explanations[0] if explanations else "",
        runs=run_dicts,
    )
