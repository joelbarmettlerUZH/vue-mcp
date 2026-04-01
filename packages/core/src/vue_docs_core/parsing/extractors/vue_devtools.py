"""Vue DevTools-specific entity extractor.

Scans Vue DevTools documentation to extract plugin APIs (addCustomTab,
addCustomCommand), DevTools features, and configuration options.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

_KNOWN_APIS: dict[str, EntityType] = {
    # Plugin API
    "addCustomTab": EntityType.GLOBAL_API,
    "addCustomCommand": EntityType.GLOBAL_API,
    "removeCustomCommand": EntityType.GLOBAL_API,
    "onDevToolsClientConnected": EntityType.LIFECYCLE_HOOK,
    # Vite plugin
    "vueDevTools": EntityType.GLOBAL_API,
    # Standalone
    "devtools": EntityType.GLOBAL_API,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class VueDevToolsEntityExtractor:
    """Entity extractor for Vue DevTools documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vue-devtools",
                entity_type=entity_type,
            )

        # Scan all docs for additional entities
        for md_file in sorted(docs_path.rglob("*.md")):
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]):
        md = MarkdownIt()
        raw = md_file.read_text(encoding="utf-8")
        tokens = md.parse(raw)
        rel_path = str(md_file.relative_to(docs_path))

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open" and tok.tag in ("h2", "h3") and i + 1 < len(tokens):
                inline = tokens[i + 1]
                heading_text = inline.content if inline.type == "inline" else ""
                name = self._clean_heading(heading_text)
                if name and name not in dictionary:
                    entity_type = self._classify(name)
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="vue-devtools",
                        entity_type=entity_type,
                        page_path=rel_path,
                        section=heading_text.strip(),
                    )
            i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        text = _SLUG_RE.sub("", heading_text).strip()
        if not text:
            return None
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        m = _ANGLE_BRACKETS_RE.match(text)
        if m:
            text = m.group(1)
        text = _TRAILING_PARENS_RE.sub("", text)
        if " " in text and "." not in text:
            return None
        if not text:
            return None
        return text

    def _classify(self, name: str) -> EntityType:
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith(("add", "remove", "create", "define")):
            return EntityType.GLOBAL_API
        if name.startswith("on"):
            return EntityType.LIFECYCLE_HOOK
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vue/devtools-api['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vue/devtools['\"]"),
            re.compile(r"import\s+(\w+)\s+from\s*['\"]vite-plugin-vue-devtools['\"]"),
        ]
