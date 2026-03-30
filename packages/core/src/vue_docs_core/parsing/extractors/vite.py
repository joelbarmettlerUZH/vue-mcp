"""Vite-specific entity extractor.

Scans Vite documentation to extract build tool APIs: JavaScript API functions
(createServer, build, defineConfig), plugin hooks (config, resolveId, load,
transform), HMR client APIs (import.meta.hot), and configuration options.
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known Vite APIs with their types
_KNOWN_APIS: dict[str, EntityType] = {
    # JavaScript API functions
    "createServer": EntityType.GLOBAL_API,
    "build": EntityType.GLOBAL_API,
    "preview": EntityType.GLOBAL_API,
    "defineConfig": EntityType.GLOBAL_API,
    "mergeConfig": EntityType.GLOBAL_API,
    "loadConfigFromFile": EntityType.GLOBAL_API,
    "loadEnv": EntityType.GLOBAL_API,
    "resolveConfig": EntityType.GLOBAL_API,
    "preprocessCSS": EntityType.GLOBAL_API,
    "transformWithEsbuild": EntityType.GLOBAL_API,
    "normalizePath": EntityType.GLOBAL_API,
    "searchForWorkspaceRoot": EntityType.GLOBAL_API,
    "createFilter": EntityType.GLOBAL_API,
    "createNodeDevEnvironment": EntityType.GLOBAL_API,
    "fetchModule": EntityType.GLOBAL_API,
    # Plugin hooks
    "config": EntityType.LIFECYCLE_HOOK,
    "configResolved": EntityType.LIFECYCLE_HOOK,
    "configureServer": EntityType.LIFECYCLE_HOOK,
    "configurePreviewServer": EntityType.LIFECYCLE_HOOK,
    "transformIndexHtml": EntityType.LIFECYCLE_HOOK,
    "handleHotUpdate": EntityType.LIFECYCLE_HOOK,
    "hotUpdate": EntityType.LIFECYCLE_HOOK,
    "resolveId": EntityType.LIFECYCLE_HOOK,
    "load": EntityType.LIFECYCLE_HOOK,
    "transform": EntityType.LIFECYCLE_HOOK,
    "buildStart": EntityType.LIFECYCLE_HOOK,
    "buildEnd": EntityType.LIFECYCLE_HOOK,
    "generateBundle": EntityType.LIFECYCLE_HOOK,
    "writeBundle": EntityType.LIFECYCLE_HOOK,
    "closeBundle": EntityType.LIFECYCLE_HOOK,
    "enforce": EntityType.LIFECYCLE_HOOK,
    "apply": EntityType.LIFECYCLE_HOOK,
    # HMR client API
    "import.meta.hot.accept": EntityType.INSTANCE_METHOD,
    "import.meta.hot.dispose": EntityType.INSTANCE_METHOD,
    "import.meta.hot.prune": EntityType.INSTANCE_METHOD,
    "import.meta.hot.invalidate": EntityType.INSTANCE_METHOD,
    "import.meta.hot.on": EntityType.INSTANCE_METHOD,
    "import.meta.hot.off": EntityType.INSTANCE_METHOD,
    "import.meta.hot.send": EntityType.INSTANCE_METHOD,
    "import.meta.hot.data": EntityType.INSTANCE_PROPERTY,
    # Special globals
    "import.meta.hot": EntityType.INSTANCE_PROPERTY,
    "import.meta.env": EntityType.INSTANCE_PROPERTY,
    "import.meta.glob": EntityType.GLOBAL_API,
    # Config options (top-level)
    "root": EntityType.OPTION,
    "base": EntityType.OPTION,
    "mode": EntityType.OPTION,
    "define": EntityType.OPTION,
    "plugins": EntityType.OPTION,
    "publicDir": EntityType.OPTION,
    "cacheDir": EntityType.OPTION,
    "appType": EntityType.OPTION,
    "customLogger": EntityType.OPTION,
    "envDir": EntityType.OPTION,
    "envPrefix": EntityType.OPTION,
    # Config options (nested)
    "resolve.alias": EntityType.OPTION,
    "resolve.dedupe": EntityType.OPTION,
    "resolve.conditions": EntityType.OPTION,
    "resolve.mainFields": EntityType.OPTION,
    "resolve.extensions": EntityType.OPTION,
    "css.modules": EntityType.OPTION,
    "css.postcss": EntityType.OPTION,
    "css.preprocessorOptions": EntityType.OPTION,
    "css.devSourcemap": EntityType.OPTION,
    "css.transformer": EntityType.OPTION,
    "css.lightningcss": EntityType.OPTION,
    "json.namedExports": EntityType.OPTION,
    "json.stringify": EntityType.OPTION,
    "esbuild": EntityType.OPTION,
    "assetsInclude": EntityType.OPTION,
    "logLevel": EntityType.OPTION,
    "clearScreen": EntityType.OPTION,
    "html.cspNonce": EntityType.OPTION,
    "server.host": EntityType.OPTION,
    "server.port": EntityType.OPTION,
    "server.strictPort": EntityType.OPTION,
    "server.https": EntityType.OPTION,
    "server.open": EntityType.OPTION,
    "server.proxy": EntityType.OPTION,
    "server.cors": EntityType.OPTION,
    "server.headers": EntityType.OPTION,
    "server.hmr": EntityType.OPTION,
    "server.warmup": EntityType.OPTION,
    "server.watch": EntityType.OPTION,
    "server.middlewareMode": EntityType.OPTION,
    "server.fs.strict": EntityType.OPTION,
    "server.fs.allow": EntityType.OPTION,
    "server.fs.deny": EntityType.OPTION,
    "server.origin": EntityType.OPTION,
    "server.sourcemapIgnoreList": EntityType.OPTION,
    "build.target": EntityType.OPTION,
    "build.outDir": EntityType.OPTION,
    "build.assetsDir": EntityType.OPTION,
    "build.assetsInlineLimit": EntityType.OPTION,
    "build.cssCodeSplit": EntityType.OPTION,
    "build.cssMinify": EntityType.OPTION,
    "build.cssTarget": EntityType.OPTION,
    "build.sourcemap": EntityType.OPTION,
    "build.lib": EntityType.OPTION,
    "build.manifest": EntityType.OPTION,
    "build.ssrManifest": EntityType.OPTION,
    "build.minify": EntityType.OPTION,
    "build.terserOptions": EntityType.OPTION,
    "build.write": EntityType.OPTION,
    "build.emptyOutDir": EntityType.OPTION,
    "build.copyPublicDir": EntityType.OPTION,
    "build.reportCompressedSize": EntityType.OPTION,
    "build.chunkSizeWarningLimit": EntityType.OPTION,
    "build.rollupOptions": EntityType.OPTION,
    "build.commonjsOptions": EntityType.OPTION,
    "build.dynamicImportVarsOptions": EntityType.OPTION,
    "build.ssr": EntityType.OPTION,
    "build.modulePreload": EntityType.OPTION,
    "preview.host": EntityType.OPTION,
    "preview.port": EntityType.OPTION,
    "preview.strictPort": EntityType.OPTION,
    "preview.https": EntityType.OPTION,
    "preview.open": EntityType.OPTION,
    "preview.proxy": EntityType.OPTION,
    "preview.cors": EntityType.OPTION,
    "preview.headers": EntityType.OPTION,
    "optimizeDeps.include": EntityType.OPTION,
    "optimizeDeps.exclude": EntityType.OPTION,
    "optimizeDeps.esbuildOptions": EntityType.OPTION,
    "optimizeDeps.force": EntityType.OPTION,
    "optimizeDeps.holdUntilCrawlEnd": EntityType.OPTION,
    "ssr.external": EntityType.OPTION,
    "ssr.noExternal": EntityType.OPTION,
    "ssr.target": EntityType.OPTION,
    "ssr.resolve.conditions": EntityType.OPTION,
    "ssr.resolve.externalConditions": EntityType.OPTION,
    "worker.format": EntityType.OPTION,
    "worker.plugins": EntityType.OPTION,
    "worker.rollupOptions": EntityType.OPTION,
}

_CONFIG_PREFIXES = frozenset(
    {
        "server",
        "build",
        "preview",
        "css",
        "resolve",
        "json",
        "html",
        "optimizeDeps",
        "ssr",
        "worker",
    }
)

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)>`?$")


class ViteEntityExtractor:
    """Entity extractor for Vite documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from Vite docs.

        Combines known API list with heading-based extraction from API doc files.
        """
        dictionary: dict[str, ApiEntity] = {}

        # Seed with known APIs
        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vite",
                entity_type=entity_type,
            )

        # Scan API doc files for additional entities
        api_files = [
            docs_path / "guide" / "api-plugin.md",
            docs_path / "guide" / "api-hmr.md",
            docs_path / "guide" / "api-javascript.md",
            docs_path / "guide" / "api-environment.md",
            docs_path / "guide" / "api-environment-instances.md",
            docs_path / "guide" / "api-environment-plugins.md",
            docs_path / "guide" / "api-environment-frameworks.md",
            docs_path / "guide" / "api-environment-runtimes.md",
        ]
        for api_file in api_files:
            if api_file.exists():
                self._scan_headings(api_file, docs_path, dictionary)

        # Scan config files
        config_dir = docs_path / "config"
        if config_dir.exists():
            for md_file in sorted(config_dir.rglob("*.md")):
                if md_file.name == "index.md":
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
                        source="vite",
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
        # HMR API
        if name.startswith("import.meta.hot"):
            return EntityType.INSTANCE_METHOD
        # Config options (dotted with known prefix)
        if "." in name:
            prefix = name.split(".")[0]
            if prefix in _CONFIG_PREFIXES:
                return EntityType.OPTION
            return EntityType.INSTANCE_METHOD
        # Factory/utility functions
        if name.startswith(("create", "define", "load", "merge", "resolve")):
            return EntityType.GLOBAL_API
        # PascalCase = component
        if name[0].isupper() and not name[0:2].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for vite."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vite['\"]"),
        ]
