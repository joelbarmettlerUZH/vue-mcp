"""Query transformation via Gemini parallel function calling.

A single LLM call with three tool declarations. Gemini decides which
transformations are useful for the query and calls them in parallel:

- decompose_query: Break multi-faceted questions into sub-questions
- rewrite_query: Generate alternative phrasings for better recall
- step_back_query: Generalize the question for broader context

The model may call all three, two, one, or even just one depending on
the query's complexity.
"""

import logging

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_core.config import settings
from vue_docs_core.models.query import QueryIntent, QueryTransformResult

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """\
You are a query transformation expert for a Vue.js documentation search system.

Given a developer's question about Vue.js, analyze it and call the appropriate \
transformation tools to help the search system find the most relevant documentation.

Rules:
- ALWAYS call classify_intent to classify the query intent.
- Call decompose_query ONLY for multi-part questions that ask about 2+ distinct concepts.
- Call rewrite_query to generate alternative phrasings that might match documentation better.
- Call step_back_query for debugging or conceptual questions that would benefit from \
broader context.
- You may call multiple tools — the system supports parallel function calling.
- Keep all outputs concise. Sub-questions and rewrites should be short search queries, \
not full sentences.
"""

TOOL_DECLARATIONS = [
    {
        "name": "classify_intent",
        "description": (
            "Classify the developer query into one of the intent categories. "
            "This determines the retrieval strategy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "api_lookup",
                        "conceptual",
                        "howto",
                        "debugging",
                        "comparison",
                        "migration",
                    ],
                    "description": (
                        "api_lookup: asking about a specific API signature/behavior. "
                        "conceptual: asking for explanation of a principle or system. "
                        "howto: asking how to accomplish a task. "
                        "debugging: describing a symptom or unexpected behavior. "
                        "comparison: asking about differences between approaches. "
                        "migration: asking about converting between patterns."
                    ),
                },
            },
            "required": ["intent"],
        },
    },
    {
        "name": "decompose_query",
        "description": (
            "Break a multi-faceted question into 2-4 independent sub-questions. "
            "Each sub-question targets a single concept and will be searched separately. "
            "Only call this for questions that genuinely ask about multiple distinct things."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sub_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-4 independent sub-questions.",
                },
            },
            "required": ["sub_questions"],
        },
    },
    {
        "name": "rewrite_query",
        "description": (
            "Generate 2-4 alternative phrasings of the query to improve search recall. "
            "Include different terminology, Vue-specific jargon, and varying specificity levels. "
            "Always call this tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rewrites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-4 alternative query phrasings.",
                },
            },
            "required": ["rewrites"],
        },
    },
    {
        "name": "step_back_query",
        "description": (
            "Generate a more general, conceptual version of the question. "
            "Useful for debugging queries (generalize the symptom to the concept) "
            "and conceptual queries (broaden to the parent topic). "
            "Call this for debugging, conceptual, and comparison queries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "general_query": {
                    "type": "string",
                    "description": "A broader, more general version of the original question.",
                },
            },
            "required": ["general_query"],
        },
    },
]


async def transform_query(
    query: str,
    detected_entities: list[str] | None = None,
) -> QueryTransformResult:
    """Transform a query using Gemini parallel function calling.

    Makes a single LLM call that can return multiple function calls
    (classify_intent, decompose_query, rewrite_query, step_back_query)
    in one response.

    Falls back gracefully if the LLM call fails — returns the original
    query with no transformations applied.
    """
    entities = detected_entities or []

    entity_hint = ""
    if entities:
        entity_hint = f"\n\nDetected Vue APIs in the query: {', '.join(entities)}"

    prompt = f"Developer query: {query}{entity_hint}"

    try:
        gemini = GeminiClient(model=settings.gemini_flash_lite_model)
        responses = await gemini.generate_with_parallel_tools(
            prompt,
            function_declarations=TOOL_DECLARATIONS,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.0,
            max_output_tokens=512,
            model=settings.gemini_flash_lite_model,
        )

        # Parse all function call responses
        result = QueryTransformResult(
            original_query=query,
            detected_entities=entities,
        )

        total_input = 0
        total_output = 0

        for resp in responses:
            total_input = max(total_input, resp.input_tokens)
            total_output += resp.output_tokens

            if resp.function_name == "classify_intent":
                intent_str = resp.arguments.get("intent", "auto")
                try:
                    result.intent = QueryIntent(intent_str)
                except ValueError:
                    result.intent = QueryIntent.AUTO

            elif resp.function_name == "decompose_query":
                subs = resp.arguments.get("sub_questions", [])
                result.sub_questions = [s for s in subs if isinstance(s, str) and s.strip()]

            elif resp.function_name == "rewrite_query":
                rewrites = resp.arguments.get("rewrites", [])
                result.rewritten_queries = [r for r in rewrites if isinstance(r, str) and r.strip()]

            elif resp.function_name == "step_back_query":
                result.step_back_query = resp.arguments.get("general_query", "")

        logger.info(
            "Query transformed: intent=%s, %d sub-questions, %d rewrites, "
            "step_back=%s (tokens: %d in, %d out)",
            result.intent.value,
            len(result.sub_questions),
            len(result.rewritten_queries),
            bool(result.step_back_query),
            total_input,
            total_output,
        )

        return result

    except Exception:
        logger.warning("Query transformation failed, using original query", exc_info=True)
        return QueryTransformResult(
            original_query=query,
            detected_entities=entities,
        )
