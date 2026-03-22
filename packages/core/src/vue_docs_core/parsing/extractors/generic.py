"""Generic entity extractor for documentation sources without custom extractors.

Uses heading-based extraction and use* composable detection as fallback.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class GenericEntityExtractor:
    """Fallback entity extractor using heading-based extraction."""

    def __init__(self, source: str = "unknown"):
        self._source = source

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Scan API docs headings to build an entity dictionary."""
        dictionary: dict[str, ApiEntity] = {}
        md = MarkdownIt()

        # Try common API directory locations
        api_dirs = [
            docs_path / "api",
            docs_path / "reference",
            docs_path / "API",
        ]

        for api_dir in api_dirs:
            if api_dir.exists():
                self._scan_headings(api_dir, md, dictionary)

        return dictionary

    def _scan_headings(
        self,
        api_dir: Path,
        md: MarkdownIt,
        dictionary: dict[str, ApiEntity],
    ):
        """Extract entities from H2/H3 headings in markdown files."""
        for md_file in sorted(api_dir.rglob("*.md")):
            if md_file.name == "index.md":
                continue

            raw = md_file.read_text(encoding="utf-8")
            tokens = md.parse(raw)
            rel_path = str(md_file.relative_to(api_dir.parent))

            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok.type == "heading_open" and tok.tag in ("h2", "h3") and i + 1 < len(tokens):
                    inline = tokens[i + 1]
                    heading_text = inline.content if inline.type == "inline" else ""
                    name = self._clean_heading(heading_text)
                    if name and name not in dictionary:
                        dictionary[name] = ApiEntity(
                            name=name,
                            source=self._source,
                            entity_type=self._classify(name),
                            page_path=rel_path,
                            section=heading_text.strip(),
                        )
                i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        """Clean a heading into an entity name."""
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
        # Skip prose headings (multiple words without dots/special chars)
        if " " in text and "." not in text and not text.startswith(("v-", "$")):
            return None
        if not text:
            return None
        return text

    def _classify(self, name: str) -> EntityType:
        """Classify an entity by name pattern."""
        if name.startswith("use"):
            return EntityType.COMPOSABLE
        if name.startswith("create"):
            return EntityType.GLOBAL_API
        if name.startswith("define"):
            return EntityType.COMPILER_MACRO
        if name.startswith("v-"):
            return EntityType.DIRECTIVE
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        if "." in name:
            return EntityType.INSTANCE_METHOD
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return empty import patterns (no default matching)."""
        return []
