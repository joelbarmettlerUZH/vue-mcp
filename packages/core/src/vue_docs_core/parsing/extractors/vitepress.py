"""VitePress-specific entity extractor.

Scans VitePress documentation to extract the static site generator's
runtime composables (useData, useRoute, useRouter), helpers (withBase),
default-theme components, the createContentLoader data loader, and the
config keys exposed by site-config / default-theme-config.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known VitePress APIs with their types. The seed guarantees coverage
# even when docs reorganize; the heading scan picks up additions.
_KNOWN_APIS: dict[str, EntityType] = {
    # Runtime composables
    "useData": EntityType.COMPOSABLE,
    "useRoute": EntityType.COMPOSABLE,
    "useRouter": EntityType.COMPOSABLE,
    "useLayout": EntityType.COMPOSABLE,
    "useSidebar": EntityType.COMPOSABLE,
    # Helpers
    "withBase": EntityType.GLOBAL_API,
    "defineConfig": EntityType.GLOBAL_API,
    "defineConfigWithTheme": EntityType.GLOBAL_API,
    "defineLoader": EntityType.GLOBAL_API,
    "createContentLoader": EntityType.GLOBAL_API,
    # Built-in / runtime components
    "Content": EntityType.COMPONENT,
    "ClientOnly": EntityType.COMPONENT,
    # Default theme components
    "VPTeamMembers": EntityType.COMPONENT,
    "VPTeamPage": EntityType.COMPONENT,
    "VPTeamPageTitle": EntityType.COMPONENT,
    "VPTeamPageSection": EntityType.COMPONENT,
    "VPSponsors": EntityType.COMPONENT,
    "VPHomeHero": EntityType.COMPONENT,
    "VPHomeFeatures": EntityType.COMPONENT,
    "VPDocAsideSponsors": EntityType.COMPONENT,
    "VPImage": EntityType.COMPONENT,
    "VPLink": EntityType.COMPONENT,
    "VPButton": EntityType.COMPONENT,
    "VPBadge": EntityType.COMPONENT,
    # Template globals (callable from within markdown)
    "$frontmatter": EntityType.OTHER,
    "$params": EntityType.OTHER,
    "$lang": EntityType.OTHER,
    "$theme": EntityType.OTHER,
    # CLI commands
    "vitepress dev": EntityType.OTHER,
    "vitepress build": EntityType.OTHER,
    "vitepress preview": EntityType.OTHER,
    "vitepress init": EntityType.OTHER,
    # Top-level site config keys (most-asked subset)
    "title": EntityType.OTHER,
    "titleTemplate": EntityType.OTHER,
    "description": EntityType.OTHER,
    "head": EntityType.OTHER,
    "lang": EntityType.OTHER,
    "base": EntityType.OTHER,
    "cleanUrls": EntityType.OTHER,
    "rewrites": EntityType.OTHER,
    "srcDir": EntityType.OTHER,
    "srcExclude": EntityType.OTHER,
    "outDir": EntityType.OTHER,
    "assetsDir": EntityType.OTHER,
    "ignoreDeadLinks": EntityType.OTHER,
    "markdown": EntityType.OTHER,
    "vite": EntityType.OTHER,
    "vue": EntityType.OTHER,
    "transformHead": EntityType.OTHER,
    "transformHtml": EntityType.OTHER,
    "transformPageData": EntityType.OTHER,
    "buildEnd": EntityType.OTHER,
    "postRender": EntityType.OTHER,
    "router": EntityType.OTHER,
    "scrollOffset": EntityType.OTHER,
    "lastUpdated": EntityType.OTHER,
    # Default-theme config keys
    "logo": EntityType.OTHER,
    "siteTitle": EntityType.OTHER,
    "nav": EntityType.OTHER,
    "sidebar": EntityType.OTHER,
    "aside": EntityType.OTHER,
    "outline": EntityType.OTHER,
    "socialLinks": EntityType.OTHER,
    "footer": EntityType.OTHER,
    "editLink": EntityType.OTHER,
    "search": EntityType.OTHER,
    "algolia": EntityType.OTHER,
    "carbonAds": EntityType.OTHER,
    "docFooter": EntityType.OTHER,
    "i18nRouting": EntityType.OTHER,
    "externalLinkIcon": EntityType.OTHER,
    "appearance": EntityType.OTHER,
    # Frontmatter-only keys
    "layout": EntityType.OTHER,
    "hero": EntityType.OTHER,
    "features": EntityType.OTHER,
    "navbar": EntityType.OTHER,
    "pageClass": EntityType.OTHER,
    # Markdown extensions / plugins
    "markdown.lineNumbers": EntityType.OTHER,
    "markdown.theme": EntityType.OTHER,
    "markdown.config": EntityType.OTHER,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)\s*/?>`?$")
# Strip an inline <Badge ... /> following a heading title.
_BADGE_INLINE_RE = re.compile(r"\s*<Badge\b[^>]*/?>\s*(?:</Badge>)?\s*$")


class VitePressEntityExtractor:
    """Entity extractor for VitePress documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from VitePress docs.

        Combines the curated seed list with H2/H3 heading scans across the
        ``reference/`` (API) and ``guide/`` (concepts) folders.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs first so they keep their canonical type.
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vitepress",
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
                        source="vitepress",
                        entity_type=self._classify(name),
                        page_path=rel_path,
                        section=heading_text.strip(),
                    )
            i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        """Clean an API heading into an entity name."""
        text = _SLUG_RE.sub("", heading_text).strip()
        text = _BADGE_INLINE_RE.sub("", text).strip()
        if not text:
            return None
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        m = _ANGLE_BRACKETS_RE.match(text)
        if m:
            text = m.group(1)
        text = _TRAILING_PARENS_RE.sub("", text)
        # Drop multi-word headings unless they look like a CLI command
        # ('vitepress build') or a dotted config path ('markdown.theme').
        if " " in text and not text.startswith("vitepress "):
            return None
        if not text:
            return None
        return text

    def _classify(self, name: str) -> EntityType:
        """Classify an entity by name pattern."""
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("$"):
            return EntityType.OTHER
        if name.startswith("vitepress "):
            return EntityType.OTHER
        if name.startswith("use") and name[3:4].isupper():
            return EntityType.COMPOSABLE
        if name.startswith(("define", "create", "with")):
            return EntityType.GLOBAL_API
        if name[0].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for vitepress."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vitepress['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vitepress/theme['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vitepress/theme-without-fonts['\"]"),
        ]
