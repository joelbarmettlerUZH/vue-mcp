"""Pinia Colada-specific entity extractor.

Scans Pinia Colada documentation to extract its data-fetching surface:
query composables (``useQuery``, ``useInfiniteQuery``), mutation composables
(``useMutation``), cache stores (``useQueryCache``, ``useMutationCache``),
the ``defineQuery`` / ``defineMutation`` factory helpers, the ``PiniaColada``
plugin, and the official plugin authoring API.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Pinia Colada APIs with their types. Sourced directly from src/index.ts
# exports, plus the official plugin packages and documented hook names.
_KNOWN_APIS: dict[str, EntityType] = {
    # Plugin & install
    "PiniaColada": EntityType.GLOBAL_API,
    "PiniaColadaOptions": EntityType.OTHER,
    # Query composables
    "useQuery": EntityType.COMPOSABLE,
    "useQueryState": EntityType.COMPOSABLE,
    "useInfiniteQuery": EntityType.COMPOSABLE,
    "useQueryCache": EntityType.COMPOSABLE,
    # Mutation composables
    "useMutation": EntityType.COMPOSABLE,
    "useMutationCache": EntityType.COMPOSABLE,
    # Definition helpers
    "defineQuery": EntityType.GLOBAL_API,
    "defineQueryOptions": EntityType.GLOBAL_API,
    "defineMutation": EntityType.GLOBAL_API,
    "defineMutationOptions": EntityType.GLOBAL_API,
    "defineInfiniteQueryOptions": EntityType.GLOBAL_API,
    # Cache helpers
    "hydrateQueryCache": EntityType.GLOBAL_API,
    "serializeQueryCache": EntityType.GLOBAL_API,
    "isQueryCache": EntityType.GLOBAL_API,
    "isMutationCache": EntityType.GLOBAL_API,
    "setInfiniteQueryData": EntityType.GLOBAL_API,
    "toCacheKey": EntityType.GLOBAL_API,
    # Return / option types worth surfacing in api_lookup
    "UseQueryReturn": EntityType.OTHER,
    "UseQueryOptions": EntityType.OTHER,
    "UseQueryStateReturn": EntityType.OTHER,
    "UseInfiniteQueryReturn": EntityType.OTHER,
    "UseInfiniteQueryOptions": EntityType.OTHER,
    "UseInfiniteQueryLoadMoreOptions": EntityType.OTHER,
    "UseMutationReturn": EntityType.OTHER,
    "UseMutationOptions": EntityType.OTHER,
    "DefineQueryOptions": EntityType.OTHER,
    "DefineInfiniteQueryOptions": EntityType.OTHER,
    "DefineMutationOptions": EntityType.OTHER,
    "QueryCache": EntityType.OTHER,
    "MutationCache": EntityType.OTHER,
    "QueryMeta": EntityType.OTHER,
    "MutationMeta": EntityType.OTHER,
    "EntryKey": EntityType.OTHER,
    "TypesConfig": EntityType.OTHER,
    # Plugin authoring (typed under ./plugins)
    "PiniaColadaPlugin": EntityType.OTHER,
    "PiniaColadaPluginContext": EntityType.OTHER,
    # Official plugins (usable as values in `plugins: [...]`)
    "PiniaColadaQueryHooksPlugin": EntityType.GLOBAL_API,
    "PiniaColadaAutoRefetchPlugin": EntityType.GLOBAL_API,
    "PiniaColadaRetry": EntityType.GLOBAL_API,
    "PiniaColadaDelay": EntityType.GLOBAL_API,
    "PiniaColadaCachePersister": EntityType.GLOBAL_API,
    # TanStack Query compatibility
    "PiniaColadaTanstackCompatPlugin": EntityType.GLOBAL_API,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")


class PiniaColadaEntityExtractor:
    """Entity extractor for Pinia Colada documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Pinia Colada docs.

        Combines the curated seed list (every public export from
        ``src/index.ts`` plus the official plugins) with H2/H3 heading scans
        across the ``guide/``, ``advanced/``, ``cookbook/``, and ``plugins/``
        folders to pick up additions.
        """
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="pinia-colada",
                entity_type=entity_type,
            )

        for md_file in sorted(docs_path.rglob("*.md")):
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(
        self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]
    ) -> None:
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
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="pinia-colada",
                        entity_type=self._classify(name),
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
        text = _TRAILING_PARENS_RE.sub("", text)
        if " " in text and "." not in text:
            return None
        return text or None

    def _classify(self, name: str) -> EntityType:
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("use") and name[3:4].isupper():
            return EntityType.COMPOSABLE
        if name.startswith(("define", "create", "hydrate", "serialize")):
            return EntityType.GLOBAL_API
        if name.startswith("PiniaColada"):
            return EntityType.OTHER
        if name[0].isupper():
            return EntityType.OTHER
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for Pinia Colada and its official plugins."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@pinia/colada['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@pinia/colada-nuxt['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@pinia/colada-plugin-[\w-]+['\"]"),
        ]
