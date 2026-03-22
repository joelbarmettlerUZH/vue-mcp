"""Vue.js-specific entity extractor.

Scans H2/H3 headings in the /api/ folder of the Vue documentation to build
the entity dictionary. Uses file-stem → EntityType mapping for classification.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# File-stem → EntityType mapping
_FILE_TYPE_MAP: dict[str, EntityType] = {
    "application": EntityType.GLOBAL_API,
    "general": EntityType.GLOBAL_API,
    "composition-api-setup": EntityType.COMPOSABLE,
    "composition-api-lifecycle": EntityType.LIFECYCLE_HOOK,
    "composition-api-dependency-injection": EntityType.COMPOSABLE,
    "composition-api-helpers": EntityType.COMPOSABLE,
    "reactivity-core": EntityType.COMPOSABLE,
    "reactivity-advanced": EntityType.COMPOSABLE,
    "reactivity-utilities": EntityType.COMPOSABLE,
    "options-state": EntityType.OPTION,
    "options-rendering": EntityType.OPTION,
    "options-lifecycle": EntityType.LIFECYCLE_HOOK,
    "options-composition": EntityType.OPTION,
    "options-misc": EntityType.OPTION,
    "component-instance": EntityType.INSTANCE_PROPERTY,
    "built-in-directives": EntityType.DIRECTIVE,
    "built-in-components": EntityType.COMPONENT,
    "built-in-special-elements": EntityType.COMPONENT,
    "built-in-special-attributes": EntityType.DIRECTIVE,
    "sfc-script-setup": EntityType.COMPILER_MACRO,
    "render-function": EntityType.GLOBAL_API,
    "custom-elements": EntityType.GLOBAL_API,
    "ssr": EntityType.GLOBAL_API,
    "utility-types": EntityType.OTHER,
    "custom-renderer": EntityType.GLOBAL_API,
    "compile-time-flags": EntityType.OTHER,
    "sfc-css-features": EntityType.OTHER,
    "sfc-spec": EntityType.OTHER,
}

# Files where only explicit API-looking headings should be extracted
_STRICT_FILES = {
    "sfc-script-setup",
    "sfc-spec",
    "sfc-css-features",
    "compile-time-flags",
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_SUP_RE = re.compile(r"<sup[^>]*/>|<sup[^>]*>.*?</sup>", re.DOTALL)
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")


def _is_api_name_candidate(text: str, *, strict: bool = False) -> bool:
    """Heuristic: does this cleaned heading look like an API name?"""
    if " " in text and not text.startswith("app."):
        return False
    if strict:
        return bool(any(marker in text for marker in ("()", "`", "<", "v-", "$", "__")))
    if "\\" in text:
        return True
    if text[0].islower() or text.startswith(("$", "v-", "`", "<", "_")):
        return True
    if text[0].isupper() and not text[0:2].isupper():
        return True
    return bool(text.startswith("__"))


def _clean_api_name(heading_text: str, *, strict: bool = False) -> str | None:
    """Extract the API name from a heading."""
    text = _SLUG_RE.sub("", heading_text).strip()
    text = _SUP_RE.sub("", text).strip()
    if "&" in text:
        return None
    if not text or not _is_api_name_candidate(text, strict=strict):
        return None
    m = _BACKTICK_RE.match(text)
    if m:
        text = m.group(1)
    m = _ANGLE_BRACKETS_RE.match(text)
    if m:
        text = m.group(1)
    text = _TRAILING_PARENS_RE.sub("", text)
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


def _entity_type_for_file(file_stem: str, name: str) -> EntityType:
    """Determine the EntityType based on file and entity name."""
    base_type = _FILE_TYPE_MAP.get(file_stem, EntityType.OTHER)
    if file_stem == "component-instance":
        if (name.startswith("$") and "(" in name) or name.endswith("()"):
            return EntityType.INSTANCE_METHOD
        return EntityType.INSTANCE_PROPERTY
    if file_stem == "sfc-script-setup" and name.startswith("use"):
        return EntityType.COMPOSABLE
    return base_type


class VueEntityExtractor:
    """Entity extractor for Vue.js core documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Scan H2 headings in all API markdown files to build the entity dictionary."""
        api_dir = docs_path / "api"
        if not api_dir.exists():
            return {}

        md = MarkdownIt()
        dictionary: dict[str, ApiEntity] = {}

        for md_file in sorted(api_dir.glob("*.md")):
            if md_file.name in ("index.md", "api.data.ts"):
                continue

            file_stem = md_file.stem
            raw = md_file.read_text(encoding="utf-8")
            tokens = md.parse(raw)

            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok.type == "heading_open" and tok.tag == "h2" and i + 1 < len(tokens):
                    inline = tokens[i + 1]
                    heading_text = inline.content if inline.type == "inline" else ""

                    strict = file_stem in _STRICT_FILES
                    names = _split_compound_heading(heading_text, strict=strict)
                    for name in names:
                        entity_type = _entity_type_for_file(file_stem, name)
                        dictionary[name] = ApiEntity(
                            name=name,
                            source="vue",
                            entity_type=entity_type,
                            page_path=f"api/{md_file.name}",
                            section=heading_text.strip(),
                        )
                i += 1

        return dictionary

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for Vue packages."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vue['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vue/runtime-core['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vue/reactivity['\"]"),
        ]
