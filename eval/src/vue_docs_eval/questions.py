"""Framework-parameterized question generation using GeminiClient."""

import asyncio
import logging
from pathlib import Path

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_core.data.sources import SOURCE_REGISTRY

logger = logging.getLogger(__name__)

GENERATION_SYSTEM_INSTRUCTION = """\
You are an expert {display_name} developer and documentation specialist. Your task is to \
generate challenging, realistic developer questions that the {display_name} documentation \
should be able to answer.

Requirements for the questions:
1. Each question must be answerable from the documentation content provided.
2. Questions MUST cover ALL of these intent types with roughly equal distribution:
   - api_lookup: Questions about specific API signatures, parameters, return values
   - conceptual: Questions about {display_name} principles, architecture, core concepts
   - howto: Questions about how to accomplish specific tasks
   - debugging: Questions describing a symptom or unexpected behavior
   - comparison: Questions asking about differences between approaches
   - migration: Questions about converting between patterns
3. Include varying difficulty levels (easy, medium, hard) - aim for ~30% each.
4. Include some questions with typos or informal phrasing.
5. Include some multi-faceted questions that span multiple documentation sections.
6. Include some questions using synonyms or informal language.
"""

QUESTION_FUNCTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "List of generated evaluation questions.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The developer's question in natural language.",
                    },
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
                        "description": "The intent category of the question.",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "The difficulty level of the question.",
                    },
                    "expected_answer": {
                        "type": "string",
                        "description": "A concise answer (2-5 sentences) from the documentation.",
                    },
                    "relevant_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Documentation file paths that contain the answer.",
                    },
                    "relevant_apis": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "API names relevant to the answer.",
                    },
                },
                "required": [
                    "question",
                    "intent",
                    "difficulty",
                    "expected_answer",
                    "relevant_paths",
                    "relevant_apis",
                ],
            },
        }
    },
    "required": ["questions"],
}


def collect_doc_files(docs_path: Path) -> list[tuple[str, str]]:
    """Collect markdown files, returning (relative_path, content) pairs."""
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs path does not exist: {docs_path}")

    files: list[tuple[str, str]] = []
    for md_file in sorted(docs_path.rglob("*.md")):
        relative = str(md_file.relative_to(docs_path))
        content = md_file.read_text(encoding="utf-8", errors="replace")
        if len(content) < 100:
            continue
        files.append((relative, content))

    logger.info("Found %d documentation files in %s", len(files), docs_path)
    return files


def build_docs_content(files: list[tuple[str, str]], max_chars: int = 800_000) -> str:
    """Build a combined documentation string within token limits."""
    priority_prefixes = ["guide/essentials/", "guide/components/", "api/", "guide/", "tutorial/"]

    def priority_key(path: str) -> int:
        for i, prefix in enumerate(priority_prefixes):
            if path.startswith(prefix):
                return i
        return len(priority_prefixes)

    sorted_files = sorted(files, key=lambda f: (priority_key(f[0]), f[0]))

    parts: list[str] = []
    total = 0
    included = 0

    for rel_path, content in sorted_files:
        entry = f"\n\n--- FILE: {rel_path} ---\n\n{content}"
        if total + len(entry) > max_chars:
            logger.info("Truncating at %d files (%.0fK chars)", included, total / 1000)
            break
        parts.append(entry)
        total += len(entry)
        included += 1

    logger.info("Including %d files (%.0fK chars) for question generation", included, total / 1000)
    return "".join(parts)


def generate_questions(
    framework: str,
    docs_path: Path,
    count: int = 50,
    model: str | None = None,
) -> list[dict]:
    """Generate test questions for a specific framework."""
    source = SOURCE_REGISTRY.get(framework)
    if not source:
        raise ValueError(f"Unknown framework: {framework}")

    display_name = source.display_name

    files = collect_doc_files(docs_path)
    docs_content = build_docs_content(files)

    per_intent = max(count // 6, 5)
    min_per_intent = max(count // 10, 3)

    system_instruction = GENERATION_SYSTEM_INSTRUCTION.format(display_name=display_name)

    prompt = (
        f"Study the documentation below, then generate exactly {count} test questions.\n"
        f"Aim for ~{per_intent} questions per intent type. "
        f"You MUST generate at least {min_per_intent} questions for EACH intent type.\n\n"
        f"DOCUMENTATION CONTENT:\n{docs_content}"
    )

    gemini = GeminiClient(model=model or "gemini-3.1-flash-lite-preview", timeout=300.0)

    async def _call():
        result = await gemini.generate_with_tool(
            prompt,
            function_name="save_questions",
            function_description="Save the generated evaluation questions with their metadata.",
            parameters_schema=QUESTION_FUNCTION_SCHEMA,
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=32000,
        )
        await gemini.close()
        return result

    logger.info("Generating %d questions for %s...", count, display_name)
    result = asyncio.run(_call())
    questions = result.arguments.get("questions", [])

    # Validate, add framework field
    valid = []
    for q in questions:
        if not isinstance(q, dict) or "question" not in q:
            continue
        q["framework"] = framework
        q.setdefault("intent", "conceptual")
        q.setdefault("difficulty", "medium")
        q.setdefault("expected_answer", "")
        q.setdefault("relevant_paths", [])
        q.setdefault("relevant_apis", [])
        valid.append(q)

    logger.info("Generated %d valid questions (requested %d)", len(valid), count)

    intent_counts: dict[str, int] = {}
    for q in valid:
        intent_counts[q["intent"]] = intent_counts.get(q["intent"], 0) + 1
    logger.info("Intent distribution: %s", intent_counts)

    return valid
