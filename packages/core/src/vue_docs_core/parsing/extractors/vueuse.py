"""VueUse-specific entity extractor.

Extracts composable function entities from VueUse documentation. Unlike Vue.js
and Vue Router where entities are extracted from API reference headings, VueUse
entities map 1:1 to directory names under each package (e.g. ``core/useMouse/``).
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity, EntityType

_PACKAGE_DIRS = {
    "core",
    "shared",
    "router",
    "integrations",
    "math",
    "firebase",
    "rxjs",
    "electron",
    "nuxt",
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_CATEGORY_RE = re.compile(r"^category:\s*(.+)$", re.MULTILINE)
_DEPRECATED_RE = re.compile(r"^deprecated:\s*true\b", re.MULTILINE)
_RELATED_RE = re.compile(r"^related:\s*(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple frontmatter fields from markdown text."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = m.group(1)
    result: dict[str, str] = {}
    cm = _CATEGORY_RE.search(fm)
    if cm:
        result["category"] = cm.group(1).strip()
    if _DEPRECATED_RE.search(fm):
        result["deprecated"] = "true"
    rm = _RELATED_RE.search(fm)
    if rm:
        result["related"] = rm.group(1).strip()
    return result


def _classify(name: str) -> EntityType:
    """Classify a VueUse entity by its name pattern."""
    if name.startswith("use"):
        return EntityType.COMPOSABLE
    if name.startswith("create"):
        return EntityType.GLOBAL_API
    if name.startswith("on"):
        return EntityType.LIFECYCLE_HOOK
    # PascalCase without "use" prefix (e.g. OnClickOutside, UseImage) -> component
    if name[0].isupper() and not name.startswith("use"):
        return EntityType.COMPONENT
    return EntityType.UTILITY


class VueUseEntityExtractor:
    """Entity extractor for VueUse documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from VueUse docs.

        Each subdirectory with an ``index.md`` under a package directory
        represents one composable/utility entity.
        """
        dictionary: dict[str, ApiEntity] = {}

        for pkg_name in sorted(_PACKAGE_DIRS):
            pkg_dir = docs_path / pkg_name
            if not pkg_dir.is_dir():
                continue

            for fn_dir in sorted(pkg_dir.iterdir()):
                if not fn_dir.is_dir():
                    continue
                index_md = fn_dir / "index.md"
                if not index_md.exists():
                    continue

                entity_name = fn_dir.name
                if entity_name in dictionary:
                    continue

                # Parse frontmatter for metadata
                raw = index_md.read_text(encoding="utf-8")
                fm = _parse_frontmatter(raw)

                # Parse related entities
                related: list[str] = []
                if "related" in fm:
                    related = [r.strip() for r in fm["related"].split(",") if r.strip()]

                page_path = f"{pkg_name}/{entity_name}/index.md"
                category = fm.get("category", "")

                dictionary[entity_name] = ApiEntity(
                    name=entity_name,
                    source="vueuse",
                    entity_type=_classify(entity_name),
                    page_path=page_path,
                    section=category,
                    related=related,
                )

        return dictionary

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for all VueUse packages."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/core['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/shared['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/math['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/router['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/integrations/\w+['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/firebase['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/rxjs['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/electron['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vueuse/nuxt['\"]"),
        ]
