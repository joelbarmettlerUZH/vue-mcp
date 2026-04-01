"""Nuxt-specific entity extractor.

Scans Nuxt documentation to extract framework APIs: composables (useFetch,
useAsyncData, useHead), components (NuxtLink, NuxtPage, NuxtLayout), utility
functions (navigateTo, definePageMeta), and CLI commands (nuxi).
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Nuxt APIs with their types
_KNOWN_APIS: dict[str, EntityType] = {
    # Composables - data fetching
    "useFetch": EntityType.COMPOSABLE,
    "useAsyncData": EntityType.COMPOSABLE,
    "useLazyFetch": EntityType.COMPOSABLE,
    "useLazyAsyncData": EntityType.COMPOSABLE,
    "createUseFetch": EntityType.COMPOSABLE,
    "createUseAsyncData": EntityType.COMPOSABLE,
    # Composables - head/SEO
    "useHead": EntityType.COMPOSABLE,
    "useHeadSafe": EntityType.COMPOSABLE,
    "useSeoMeta": EntityType.COMPOSABLE,
    "useServerSeoMeta": EntityType.COMPOSABLE,
    # Composables - state
    "useState": EntityType.COMPOSABLE,
    "useCookie": EntityType.COMPOSABLE,
    "useAppConfig": EntityType.COMPOSABLE,
    "useRuntimeConfig": EntityType.COMPOSABLE,
    # Composables - routing
    "useRoute": EntityType.COMPOSABLE,
    "useRouter": EntityType.COMPOSABLE,
    # Composables - app context
    "useNuxtApp": EntityType.COMPOSABLE,
    "useNuxtData": EntityType.COMPOSABLE,
    # Composables - server/request
    "useRequestEvent": EntityType.COMPOSABLE,
    "useRequestFetch": EntityType.COMPOSABLE,
    "useRequestHeaders": EntityType.COMPOSABLE,
    "useRequestUrl": EntityType.COMPOSABLE,
    # Composables - error
    "useError": EntityType.COMPOSABLE,
    # Composables - UI/accessibility
    "useRouteAnnouncer": EntityType.COMPOSABLE,
    "useAnnouncer": EntityType.COMPOSABLE,
    "useLoadingIndicator": EntityType.COMPOSABLE,
    # Composables - misc
    "useHydration": EntityType.COMPOSABLE,
    "usePreviewMode": EntityType.COMPOSABLE,
    # Components
    "NuxtLink": EntityType.COMPONENT,
    "NuxtPage": EntityType.COMPONENT,
    "NuxtLayout": EntityType.COMPONENT,
    "NuxtLoadingIndicator": EntityType.COMPONENT,
    "NuxtErrorBoundary": EntityType.COMPONENT,
    "NuxtIsland": EntityType.COMPONENT,
    "NuxtImg": EntityType.COMPONENT,
    "NuxtPicture": EntityType.COMPONENT,
    "NuxtClientFallback": EntityType.COMPONENT,
    "NuxtRouteAnnouncer": EntityType.COMPONENT,
    "NuxtAnnouncer": EntityType.COMPONENT,
    "NuxtWelcome": EntityType.COMPONENT,
    "NuxtTime": EntityType.COMPONENT,
    "ClientOnly": EntityType.COMPONENT,
    "DevOnly": EntityType.COMPONENT,
    "Teleports": EntityType.COMPONENT,
    # Utils / global functions
    "$fetch": EntityType.GLOBAL_API,
    "navigateTo": EntityType.GLOBAL_API,
    "abortNavigation": EntityType.GLOBAL_API,
    "defineNuxtPlugin": EntityType.GLOBAL_API,
    "defineNuxtRouteMiddleware": EntityType.GLOBAL_API,
    "definePageMeta": EntityType.GLOBAL_API,
    "defineNuxtComponent": EntityType.GLOBAL_API,
    "defineLazyHydrationComponent": EntityType.GLOBAL_API,
    "clearError": EntityType.GLOBAL_API,
    "showError": EntityType.GLOBAL_API,
    "createError": EntityType.GLOBAL_API,
    "addRouteMiddleware": EntityType.GLOBAL_API,
    "refreshCookie": EntityType.GLOBAL_API,
    "refreshNuxtData": EntityType.GLOBAL_API,
    "reloadNuxtApp": EntityType.GLOBAL_API,
    "callOnce": EntityType.GLOBAL_API,
    "prefetchComponents": EntityType.GLOBAL_API,
    "preloadComponents": EntityType.GLOBAL_API,
    "preloadRouteComponents": EntityType.GLOBAL_API,
    "clearNuxtData": EntityType.GLOBAL_API,
    "clearNuxtState": EntityType.GLOBAL_API,
    "setPageLayout": EntityType.GLOBAL_API,
    "updateAppConfig": EntityType.GLOBAL_API,
    "setResponseStatus": EntityType.GLOBAL_API,
    "prerenderRoutes": EntityType.GLOBAL_API,
    "defineRouteRules": EntityType.GLOBAL_API,
    "onNuxtReady": EntityType.GLOBAL_API,
    "onPrehydrate": EntityType.GLOBAL_API,
    # Config functions
    "defineNuxtConfig": EntityType.GLOBAL_API,
    "defineAppConfig": EntityType.GLOBAL_API,
    # Lifecycle hooks
    "onBeforeRouteLeave": EntityType.LIFECYCLE_HOOK,
    "onBeforeRouteUpdate": EntityType.LIFECYCLE_HOOK,
    # CLI commands
    "nuxi dev": EntityType.OTHER,
    "nuxi build": EntityType.OTHER,
    "nuxi generate": EntityType.OTHER,
    "nuxi preview": EntityType.OTHER,
    "nuxi add": EntityType.OTHER,
    "nuxi init": EntityType.OTHER,
    "nuxi analyze": EntityType.OTHER,
    "nuxi info": EntityType.OTHER,
    "nuxi prepare": EntityType.OTHER,
    "nuxi typecheck": EntityType.OTHER,
    "nuxi test": EntityType.OTHER,
    "nuxi cleanup": EntityType.OTHER,
    "nuxi upgrade": EntityType.OTHER,
    "nuxi module": EntityType.OTHER,
    "nuxi devtools": EntityType.OTHER,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class NuxtEntityExtractor:
    """Entity extractor for Nuxt documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Nuxt docs.

        Combines known API list with heading-based extraction from API docs.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="nuxt",
                entity_type=entity_type,
            )

        # Scan API doc files (4.api/ directory)
        api_dir = docs_path / "4.api"
        if api_dir.exists():
            for md_file in sorted(api_dir.rglob("*.md")):
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
                        source="nuxt",
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
        # Strip angle brackets (component names like <NuxtLink>)
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
        if name.startswith(("create", "define")):
            return EntityType.GLOBAL_API
        if name.startswith(("onBefore", "onAfter", "onNuxt", "onPre")):
            return EntityType.LIFECYCLE_HOOK
        if name.startswith("Nuxt") or (name[0].isupper() and not name[0:2].isupper()):
            return EntityType.COMPONENT
        if name.startswith("nuxi "):
            return EntityType.OTHER
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for Nuxt."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]#app['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]#imports['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]nuxt/app['\"]"),
        ]
