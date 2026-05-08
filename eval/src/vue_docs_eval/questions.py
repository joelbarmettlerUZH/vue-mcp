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

2. **Intent distribution — TARGET ROUGHLY EQUAL COUNTS across these six categories.**
   This is the most-violated rule. Do NOT default to 'howto' for everything. If you are
   about to write another 'How do I X' question, ask yourself which of the following
   categories it really belongs to and use that intent label:
     - api_lookup    — about a specific API's signature, parameters, return value, or option name
     - conceptual    — about why/how the framework works, its mental model, or design rationale
     - howto         — practical "how do I accomplish task X" recipes
     - debugging     — phrased as a symptom or "why isn't X working" / "X is broken because…"
     - comparison    — about differences between two APIs, patterns, or alternatives
     - migration     — about converting from an older version, an alternative library, or a
                       deprecated pattern

3. **Difficulty distribution — TARGET ~25% easy / 25% medium / 25% hard / 25% extreme.**
   Use the SPECIFIC documented APIs, concepts, file paths, and terminology of {display_name}
   in your questions. DO NOT borrow vocabulary or examples from other frameworks; only refer
   to APIs that actually appear in the documentation provided below.

   - easy:    surface-level. User knows the right keyword. Answer is on one page.
              Example shape: "What does the `<prop name>` option do on the `<component>`?"
   - medium:  combines two or three docs sections, or requires knowing a non-obvious flag.
              Example shape: "How do I configure X to behave like Y when Z changes?"
   - hard:    requires understanding the framework's internals, lifecycle, or how features
              interact. May be phrased as a real production-grade task.
              Example shape: "How do I implement <feature> while keeping <constraint> intact?"
   - extreme: THE DEVELOPER DOES NOT KNOW THE NAME OF THE API. They describe a symptom or
              an outcome in plain non-technical language using only words a beginner would
              know. They write like a frustrated junior on Stack Overflow, NOT like someone
              who has read the docs.

              Rules for extreme questions:
                a) DO NOT mention any API name, function name, component name, prop name,
                   option name, or other framework-specific identifier in the question text.
                b) DO NOT use framework jargon or domain terminology. Replace it with
                   everyday language: "screen" instead of "DOM", "thing" instead of
                   "component", "save it for later" instead of "persist", "make it sticky"
                   instead of "pin", "send to" instead of "emit", and so on.
                c) Phrase the question as the user's GOAL or SYMPTOM, not the solution.
                d) The `relevant_apis` field for these questions should still list the
                   actual APIs the docs answer the question with — that's how we measure
                   whether retrieval bridged the vocab gap.

              Generate AT LEAST 10 extreme questions following these rules. They should
              cover a range of {display_name}'s capabilities — not all about the same topic.

4. Vary phrasing across the set. Some questions should have typos or informal grammar.
   Some should be multi-sentence with extra context ("I'm trying to ... and I keep getting
   ... what's wrong?"). Some should span multiple docs sections.
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
                        "enum": ["easy", "medium", "hard", "extreme"],
                        "description": (
                            "The difficulty level. 'extreme' means the developer does not "
                            "know the API name and describes the symptom/goal in plain "
                            "non-technical language."
                        ),
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
    min_per_intent = max(count // 10, 4)
    min_extreme = max(count // 5, 10)
    min_easy = max(count // 5, 10)
    min_medium = max(count // 5, 10)
    min_hard = max(count // 5, 10)

    system_instruction = GENERATION_SYSTEM_INSTRUCTION.format(display_name=display_name)

    prompt = (
        f"Study the {display_name} documentation below, then generate exactly {count} "
        f"test questions about {display_name}'s actual documented APIs.\n\n"
        f"HARD QUOTAS — the question set must satisfy ALL of these:\n"
        f"  • At least {min_per_intent} questions for EACH intent type:\n"
        f"    api_lookup, conceptual, howto, debugging, comparison, migration\n"
        f"    (target ~{per_intent} of each)\n"
        f"  • At least {min_easy} questions with difficulty='easy'\n"
        f"  • At least {min_medium} questions with difficulty='medium'\n"
        f"  • At least {min_hard} questions with difficulty='hard'\n"
        f"  • At least {min_extreme} questions with difficulty='extreme' "
        f"(vague non-technical phrasing, NO API names mentioned in the question)\n\n"
        f"Self-check before returning: count the questions per intent and per difficulty. "
        f"If any quota is violated, replace some questions to satisfy it.\n\n"
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
    diff_counts: dict[str, int] = {}
    for q in valid:
        intent_counts[q["intent"]] = intent_counts.get(q["intent"], 0) + 1
        diff_counts[q["difficulty"]] = diff_counts.get(q["difficulty"], 0) + 1
    logger.info("Intent distribution: %s", intent_counts)
    logger.info("Difficulty distribution: %s", diff_counts)

    return valid
