"""Generate test questions from Vue documentation using Gemini.

Reads the Vue.js documentation markdown files and uses Gemini to generate
diverse, challenging questions across all intent types. Each question includes
a ground-truth answer with references to the source documentation sections.

Usage:
    uv run python eval/generate_questions.py --docs-path data/vue-docs/src --output eval/questions.json
    uv run python eval/generate_questions.py --docs-path data/vue-docs/src --count 100
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import httpx

from vue_docs_core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Intent types from the spec
INTENT_TYPES = [
    "api_lookup",
    "conceptual",
    "howto",
    "debugging",
    "comparison",
    "migration",
]

GENERATION_PROMPT = """\
You are an expert Vue.js developer and documentation specialist. Your task is to \
generate challenging, realistic developer questions that the Vue.js documentation \
should be able to answer.

Below is the full content of several Vue.js documentation pages. Study them carefully, \
then generate exactly {count} test questions.

Requirements for the questions:
1. Each question must be answerable from the documentation content provided.
2. Questions should cover ALL of these intent types (distribute roughly evenly):
   - api_lookup: Questions about specific Vue API signatures, parameters, return values
   - conceptual: Questions about Vue principles, reactivity system, rendering, etc.
   - howto: Questions about how to accomplish specific tasks
   - debugging: Questions describing a symptom or unexpected behavior
   - comparison: Questions asking about differences between approaches
   - migration: Questions about converting between patterns (Options API vs Composition API)
3. Include varying difficulty levels (easy, medium, hard).
4. Include some questions with typos or informal phrasing (e.g., "definProps", "onmounted").
5. Include some multi-faceted questions that span multiple documentation sections.
6. Include some questions using synonyms or informal language (e.g., "two-way binding" for v-model).

For each question, provide:
- "question": The developer's question (natural language)
- "intent": One of {intents}
- "difficulty": One of "easy", "medium", "hard"
- "expected_answer": A concise answer (2-5 sentences) derived from the documentation
- "relevant_paths": List of documentation file paths that contain the answer
- "relevant_apis": List of Vue API names relevant to the answer (empty list if none)

Return a JSON array of objects. Output ONLY valid JSON, no markdown fences or explanation.

---
DOCUMENTATION CONTENT:
{docs_content}
"""


def collect_doc_files(docs_path: Path) -> list[tuple[str, str]]:
    """Collect markdown files from the Vue docs, returning (relative_path, content) pairs."""
    if not docs_path.exists():
        logger.error("Docs path does not exist: %s", docs_path)
        sys.exit(1)

    files: list[tuple[str, str]] = []
    for md_file in sorted(docs_path.rglob("*.md")):
        relative = str(md_file.relative_to(docs_path))
        content = md_file.read_text(encoding="utf-8", errors="replace")
        # Skip very short files (likely index pages)
        if len(content) < 100:
            continue
        files.append((relative, content))

    logger.info("Found %d documentation files in %s", len(files), docs_path)
    return files


def build_docs_content(files: list[tuple[str, str]], max_chars: int = 800_000) -> str:
    """Build a combined documentation string within token limits.

    Prioritizes guide/, api/, and tutorial/ files. Truncates if needed.
    """
    # Priority order for documentation sections
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
            logger.info(
                "Truncating at %d files (%.0fK chars)", included, total / 1000
            )
            break
        parts.append(entry)
        total += len(entry)
        included += 1

    logger.info("Including %d files (%.0fK chars) for question generation", included, total / 1000)
    return "".join(parts)


def call_gemini(prompt: str, model: str | None = None) -> str:
    """Call Gemini API synchronously and return the text response."""
    model = model or settings.gemini_flash_model
    api_key = settings.gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        sys.exit(1)

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 32000,
            "responseMimeType": "application/json",
        },
    }

    logger.info("Calling Gemini model %s (prompt ~%.0fK chars)...", model, len(prompt) / 1000)
    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, json=payload)
        if response.status_code != 200:
            logger.error("Gemini API error %d: %s", response.status_code, response.text[:1000])
        response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        logger.error("Gemini returned no candidates: %s", data)
        sys.exit(1)

    text = candidates[0]["content"]["parts"][0]["text"]
    return text


def generate_questions(
    docs_path: Path,
    count: int = 50,
    model: str | None = None,
) -> list[dict]:
    """Generate test questions from the Vue documentation.

    Args:
        docs_path: Path to the Vue documentation source files.
        count: Number of questions to generate.
        model: Gemini model to use (defaults to settings.gemini_flash_model).

    Returns:
        List of question dicts with question, intent, answer, paths, and apis.
    """
    files = collect_doc_files(docs_path)
    docs_content = build_docs_content(files)

    prompt = GENERATION_PROMPT.format(
        count=count,
        intents=json.dumps(INTENT_TYPES),
        docs_content=docs_content,
    )

    logger.info("Generating %d questions...", count)
    raw = call_gemini(prompt, model=model)

    # Parse JSON response (strip markdown fences if present)
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]

    try:
        questions = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini response as JSON: %s", e)
        logger.error("Raw response (first 2000 chars): %s", text[:2000])
        sys.exit(1)

    if not isinstance(questions, list):
        logger.error("Expected JSON array, got %s", type(questions).__name__)
        sys.exit(1)

    # Validate and clean each question
    valid = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if "question" not in q:
            continue
        # Ensure required fields have defaults
        q.setdefault("intent", "conceptual")
        q.setdefault("difficulty", "medium")
        q.setdefault("expected_answer", "")
        q.setdefault("relevant_paths", [])
        q.setdefault("relevant_apis", [])
        valid.append(q)

    logger.info(
        "Generated %d valid questions (requested %d)", len(valid), count
    )

    # Report intent distribution
    intent_counts: dict[str, int] = {}
    for q in valid:
        intent = q["intent"]
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    logger.info("Intent distribution: %s", intent_counts)

    return valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evaluation questions from Vue docs")
    parser.add_argument(
        "--docs-path",
        type=Path,
        default=Path("data/vue-docs/src"),
        help="Path to Vue documentation source (default: data/vue-docs/src)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/questions.json"),
        help="Output file path (default: eval/questions.json)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of questions to generate (default: 50)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (default: from settings)",
    )

    args = parser.parse_args()
    questions = generate_questions(args.docs_path, count=args.count, model=args.model)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(questions, f, indent=2)

    logger.info("Wrote %d questions to %s", len(questions), args.output)


if __name__ == "__main__":
    main()
