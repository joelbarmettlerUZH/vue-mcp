"""Pinia-specific entity extractor.

Scans Pinia documentation to extract state management APIs: store definition
(defineStore, createPinia), store instance methods ($patch, $subscribe),
composition helpers (storeToRefs), Options API helpers (mapState, mapActions),
and plugin interfaces.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Pinia APIs with their types
_KNOWN_APIS: dict[str, EntityType] = {
    # Store definition & creation
    "defineStore": EntityType.GLOBAL_API,
    "createPinia": EntityType.GLOBAL_API,
    "setActivePinia": EntityType.GLOBAL_API,
    "getActivePinia": EntityType.GLOBAL_API,
    "setMapStoreSuffix": EntityType.GLOBAL_API,
    "acceptHMRUpdate": EntityType.GLOBAL_API,
    "skipHydrate": EntityType.GLOBAL_API,
    # Composition helpers
    "storeToRefs": EntityType.COMPOSABLE,
    # Options API helpers
    "mapStores": EntityType.GLOBAL_API,
    "mapState": EntityType.GLOBAL_API,
    "mapGetters": EntityType.GLOBAL_API,
    "mapWritableState": EntityType.GLOBAL_API,
    "mapActions": EntityType.GLOBAL_API,
    # Store instance methods
    "$patch": EntityType.INSTANCE_METHOD,
    "$reset": EntityType.INSTANCE_METHOD,
    "$subscribe": EntityType.INSTANCE_METHOD,
    "$onAction": EntityType.INSTANCE_METHOD,
    "$dispose": EntityType.INSTANCE_METHOD,
    "$state": EntityType.INSTANCE_PROPERTY,
    "$id": EntityType.INSTANCE_PROPERTY,
    # Plugin system
    "PiniaPlugin": EntityType.OTHER,
    "PiniaPluginContext": EntityType.OTHER,
    "pinia.use": EntityType.INSTANCE_METHOD,
    # Testing
    "createTestingPinia": EntityType.GLOBAL_API,
    # Types
    "Store": EntityType.OTHER,
    "StoreGeneric": EntityType.OTHER,
    "StateTree": EntityType.OTHER,
    "StoreDefinition": EntityType.OTHER,
    "MutationType": EntityType.OTHER,
    "DefineStoreOptions": EntityType.OTHER,
    "DefineSetupStoreOptions": EntityType.OTHER,
    "PiniaCustomProperties": EntityType.OTHER,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class PiniaEntityExtractor:
    """Entity extractor for Pinia documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Pinia docs.

        Combines known API list with heading-based extraction from API docs.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="pinia",
                entity_type=entity_type,
            )

        # Scan API docs if they exist (TypeDoc-generated)
        api_dir = docs_path / "api"
        if api_dir.exists():
            for md_file in sorted(api_dir.rglob("*.md")):
                if md_file.name == "index.md":
                    continue
                self._scan_headings(md_file, docs_path, dictionary)

        # Also scan core-concepts for additional entities
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            if str(rel).startswith("zh"):
                continue
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]):
        """Extract entities from H2/H3 headings in a markdown file."""
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
                        source="pinia",
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
        """Classify an entity by name pattern."""
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("$"):
            return EntityType.INSTANCE_METHOD
        if name.startswith(("create", "define", "map", "set", "get")):
            return EntityType.GLOBAL_API
        if name.startswith("use"):
            return EntityType.COMPOSABLE
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for pinia."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]pinia['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@pinia/testing['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@pinia/nuxt['\"]"),
        ]
