"""Deterministic API entity extraction from chunks.

Tier 1 — backtick-wrapped inline code and heading text.
Tier 2 — import statements and directive usage in code blocks.

The API dictionary is bootstrapped by source-specific extractors in
``vue_docs_core.parsing.extractors``.
"""

import json
import re
from pathlib import Path

from vue_docs_core.models.chunk import Chunk, ChunkType
from vue_docs_core.models.entity import ApiEntity, EntityIndex

# ---------------------------------------------------------------------------
# Heading → API name cleaning (kept for backward compat)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_SUP_RE = re.compile(r"<sup[^>]*/>|<sup[^>]*>.*?</sup>", re.DOTALL)
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")


def _is_api_name_candidate(text: str, *, strict: bool = False) -> bool:
    """Heuristic: does this cleaned heading look like an API name?

    When *strict* is True (for mixed-content files), only accept headings
    that contain ``()``, start with ``v-``/``$``/``__``, or are wrapped
    in backticks/angle brackets.
    """
    # Has spaces and doesn't start with app. → likely a prose title
    if " " in text and not text.startswith("app."):
        return False

    if strict:
        # In strict mode, require strong API indicators
        return bool(any(marker in text for marker in ("()", "`", "<", "v-", "$", "__")))

    # Contains backslash (escaped generics like PropType\<T>) — valid
    if "\\" in text:
        return True
    # Starts with lowercase, $, v-, or is backtick/angle-bracket wrapped
    if text[0].islower() or text.startswith(("$", "v-", "`", "<", "_")):
        return True
    # PascalCase single word (component names like Transition, KeepAlive)
    if text[0].isupper() and not text[0:2].isupper():
        return True
    # ALL_CAPS with underscores (compile-time flags like __VUE_OPTIONS_API__)
    return bool(text.startswith("__"))


def _clean_api_name(heading_text: str, *, strict: bool = False) -> str | None:
    """Extract the API name from a heading like ``ref()``, ``<Transition>``, ``v-model``."""
    text = _SLUG_RE.sub("", heading_text).strip()
    text = _SUP_RE.sub("", text).strip()

    # Handle compound headings separately
    if "&" in text:
        return None

    if not text or not _is_api_name_candidate(text, strict=strict):
        return None

    # Strip backticks
    m = _BACKTICK_RE.match(text)
    if m:
        text = m.group(1)

    # Strip angle brackets: <Transition> → Transition
    m = _ANGLE_BRACKETS_RE.match(text)
    if m:
        text = m.group(1)

    # Strip trailing ()
    text = _TRAILING_PARENS_RE.sub("", text)

    # Strip generic type params: PropType\<T> → PropType
    text = re.sub(r"\\?<[^>]*>$", "", text)

    if not text:
        return None

    return text


def _split_compound_heading(heading_text: str, *, strict: bool = False) -> list[str]:
    """Split headings like ``defineProps() & defineEmits()`` into individual names."""
    text = _SLUG_RE.sub("", heading_text).strip()
    text = _SUP_RE.sub("", text).strip()

    if "&" not in text:
        name = _clean_api_name(heading_text, strict=strict)
        return [name] if name else []

    parts = [p.strip() for p in text.split("&")]
    names = []
    for part in parts:
        part = _BACKTICK_RE.sub(r"\1", part)
        part = _TRAILING_PARENS_RE.sub("", part)
        if part:
            names.append(part)
    return names


# ---------------------------------------------------------------------------
# Legacy dictionary bootstrap (Vue-specific, kept for backward compat)
# ---------------------------------------------------------------------------

# Import these from the extractor for backward compatibility
from vue_docs_core.parsing.extractors.vue import (  # noqa: E402
    VueEntityExtractor as _VueExtractor,
)


def build_api_dictionary(api_dir: Path) -> dict[str, ApiEntity]:
    """Scan H2 headings in all API markdown files to build the entity dictionary.

    Backward-compatible wrapper — delegates to VueEntityExtractor.
    """
    extractor = _VueExtractor()
    # The extractor expects docs_path (parent of api/), so pass api_dir's parent
    return extractor.build_dictionary(api_dir.parent)


def save_dictionary(dictionary: dict[str, ApiEntity], path: Path):
    """Persist the API dictionary as JSON."""
    data = {name: entity.model_dump() for name, entity in dictionary.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_dictionary(path: Path) -> dict[str, ApiEntity]:
    """Load the API dictionary from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: ApiEntity(**props) for name, props in data.items()}


# ---------------------------------------------------------------------------
# Entity extraction from chunks
# ---------------------------------------------------------------------------

_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_DIRECTIVE_USE_RE = re.compile(r"\bv-(\w[\w-]*)")

# Default import pattern (Vue) — used when no import_patterns provided
_IMPORT_VUE_RE = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vue['\"]")


def extract_entities_from_chunk(
    chunk: Chunk,
    dictionary: dict[str, ApiEntity],
    import_patterns: list[re.Pattern] | None = None,
) -> list[str]:
    """Extract API entity references from a chunk's content.

    Tier 1: backtick-wrapped inline code tokens matched against the dictionary.
    Tier 2: import statements and directive usage in code blocks.
    """
    found: set[str] = set()
    dict_lower = {k.lower(): k for k in dictionary}
    content = chunk.content

    # --- Tier 1: inline code ---
    for m in _INLINE_CODE_RE.finditer(content):
        token = m.group(1).strip()
        # Strip trailing () for matching
        token_clean = _TRAILING_PARENS_RE.sub("", token)
        # Strip angle brackets
        am = _ANGLE_BRACKETS_RE.match(token_clean)
        if am:
            token_clean = am.group(1)

        if token_clean.lower() in dict_lower:
            found.add(dict_lower[token_clean.lower()])

    # --- Tier 2: code block patterns ---
    if chunk.chunk_type == ChunkType.CODE_BLOCK or "```" in content:
        # Import statements — use provided patterns or default
        patterns = import_patterns if import_patterns is not None else [_IMPORT_VUE_RE]
        for pattern in patterns:
            for m in pattern.finditer(content):
                imports = [s.strip() for s in m.group(1).split(",")]
                for imp in imports:
                    imp_clean = imp.split(" as ")[0].strip()
                    if imp_clean.lower() in dict_lower:
                        found.add(dict_lower[imp_clean.lower()])

        # Directive usage (v-model, v-for, etc.)
        for m in _DIRECTIVE_USE_RE.finditer(content):
            directive = f"v-{m.group(1)}"
            if directive.lower() in dict_lower:
                found.add(dict_lower[directive.lower()])

    return sorted(found)


def build_entity_index(
    chunks: list[Chunk],
    dictionary: dict[str, ApiEntity],
    import_patterns: list[re.Pattern] | None = None,
) -> EntityIndex:
    """Build a full entity index mapping API names to chunk IDs."""
    entity_to_chunks: dict[str, list[str]] = {}

    for chunk in chunks:
        entities = extract_entities_from_chunk(chunk, dictionary, import_patterns)
        chunk.metadata.api_entities = entities

        for entity_name in entities:
            entity_to_chunks.setdefault(entity_name, []).append(chunk.chunk_id)

    return EntityIndex(entities=dictionary, entity_to_chunks=entity_to_chunks)
