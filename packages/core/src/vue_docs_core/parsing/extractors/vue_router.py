"""Vue Router-specific entity extractor.

Scans Vue Router documentation to extract router APIs: composables (useRouter,
useRoute), factory functions (createRouter, createWebHistory), navigation guards,
components (RouterLink, RouterView), and configuration options.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity, EntityType
from vue_docs_core.parsing.typedoc import TYPE_FOLDERS, iter_symbol_pages

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

        # TypeDoc-generated API reference: one page per symbol, registered by file name
        api_dir = docs_path / "api"
        if api_dir.exists():
            self._register_api_pages(api_dir, docs_path, dictionary)

        return dictionary

    def _register_api_pages(self, api_dir: Path, docs_path: Path, dictionary: dict[str, ApiEntity]):
        """Register one entity per TypeDoc symbol page and link seeded APIs to their page.

        Headings are deliberately not scanned: generated pages use section headings such as
        "Parameters" and "Returns" and list members, none of which are API names.
        """
        for symbol, page_path, kind in iter_symbol_pages(api_dir, docs_path):
            existing = dictionary.get(symbol)
            if existing is None:
                entity_type = EntityType.OTHER if kind in TYPE_FOLDERS else self._classify(symbol)
                dictionary[symbol] = ApiEntity(
                    name=symbol, source="vue-router", entity_type=entity_type, page_path=page_path
                )
            elif not existing.page_path:
                existing.page_path = page_path

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
