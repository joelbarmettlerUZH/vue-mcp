"""Vue Router-specific entity extractor.

Scans Vue Router documentation to extract router APIs: composables (useRouter,
useRoute), factory functions (createRouter, createWebHistory), navigation guards,
components (RouterLink, RouterView), and configuration options.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Vue Router APIs with their types (for bootstrapping when docs structure varies)
_KNOWN_APIS: dict[str, EntityType] = {
    # Composables
    "useRouter": EntityType.COMPOSABLE,
    "useRoute": EntityType.COMPOSABLE,
    "useLink": EntityType.COMPOSABLE,
    # Factory functions
    "createRouter": EntityType.GLOBAL_API,
    "createWebHistory": EntityType.GLOBAL_API,
    "createWebHashHistory": EntityType.GLOBAL_API,
    "createMemoryHistory": EntityType.GLOBAL_API,
    "createRouterMatcher": EntityType.GLOBAL_API,
    # Navigation guards
    "beforeEach": EntityType.NAVIGATION_GUARD,
    "beforeResolve": EntityType.NAVIGATION_GUARD,
    "afterEach": EntityType.NAVIGATION_GUARD,
    "beforeEnter": EntityType.NAVIGATION_GUARD,
    "beforeRouteEnter": EntityType.NAVIGATION_GUARD,
    "beforeRouteUpdate": EntityType.NAVIGATION_GUARD,
    "beforeRouteLeave": EntityType.NAVIGATION_GUARD,
    "onBeforeRouteLeave": EntityType.NAVIGATION_GUARD,
    "onBeforeRouteUpdate": EntityType.NAVIGATION_GUARD,
    # Components
    "RouterLink": EntityType.COMPONENT,
    "RouterView": EntityType.COMPONENT,
    "router-link": EntityType.COMPONENT,
    "router-view": EntityType.COMPONENT,
    # Router instance methods
    "router.push": EntityType.INSTANCE_METHOD,
    "router.replace": EntityType.INSTANCE_METHOD,
    "router.go": EntityType.INSTANCE_METHOD,
    "router.back": EntityType.INSTANCE_METHOD,
    "router.forward": EntityType.INSTANCE_METHOD,
    "router.addRoute": EntityType.INSTANCE_METHOD,
    "router.removeRoute": EntityType.INSTANCE_METHOD,
    "router.hasRoute": EntityType.INSTANCE_METHOD,
    "router.getRoutes": EntityType.INSTANCE_METHOD,
    "router.resolve": EntityType.INSTANCE_METHOD,
    "router.isReady": EntityType.INSTANCE_METHOD,
    # Router instance properties
    "router.currentRoute": EntityType.INSTANCE_PROPERTY,
    "router.options": EntityType.INSTANCE_PROPERTY,
    # Route properties
    "route.params": EntityType.INSTANCE_PROPERTY,
    "route.query": EntityType.INSTANCE_PROPERTY,
    "route.hash": EntityType.INSTANCE_PROPERTY,
    "route.path": EntityType.INSTANCE_PROPERTY,
    "route.name": EntityType.INSTANCE_PROPERTY,
    "route.meta": EntityType.INSTANCE_PROPERTY,
    "route.matched": EntityType.INSTANCE_PROPERTY,
    "route.redirectedFrom": EntityType.INSTANCE_PROPERTY,
    "route.fullPath": EntityType.INSTANCE_PROPERTY,
    # Route config options
    "redirect": EntityType.OPTION,
    "alias": EntityType.OPTION,
    "children": EntityType.OPTION,
    "meta": EntityType.OPTION,
    "scrollBehavior": EntityType.OPTION,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class VueRouterEntityExtractor:
    """Entity extractor for Vue Router documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Vue Router docs.

        Combines known API list with heading-based extraction from /api/ folder.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vue-router",
                entity_type=entity_type,
            )

        # Scan API docs if they exist
        api_dir = docs_path / "api"
        if api_dir.exists():
            self._scan_api_headings(api_dir, dictionary)

        return dictionary

    def _scan_api_headings(self, api_dir: Path, dictionary: dict[str, ApiEntity]):
        """Extract additional entities from API reference headings."""
        md = MarkdownIt()

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
                        entity_type = self._classify(name)
                        dictionary[name] = ApiEntity(
                            name=name,
                            source="vue-router",
                            entity_type=entity_type,
                            page_path=rel_path,
                            section=heading_text.strip(),
                        )
                i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        """Clean an API heading into an entity name."""
        text = _SLUG_RE.sub("", heading_text).strip()
        if not text:
            return None
        # Strip backticks
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        # Strip angle brackets
        m = _ANGLE_BRACKETS_RE.match(text)
        if m:
            text = m.group(1)
        # Strip trailing ()
        text = _TRAILING_PARENS_RE.sub("", text)
        # Skip prose headings (multiple words without dots)
        if " " in text and "." not in text:
            return None
        if not text:
            return None
        return text

    def _classify(self, name: str) -> EntityType:
        """Classify an entity by name pattern."""
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("use"):
            return EntityType.COMPOSABLE
        if name.startswith("create"):
            return EntityType.GLOBAL_API
        if name.startswith(("before", "after", "onBefore")):
            return EntityType.NAVIGATION_GUARD
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        if "." in name:
            return EntityType.INSTANCE_METHOD
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for vue-router."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vue-router['\"]"),
        ]
