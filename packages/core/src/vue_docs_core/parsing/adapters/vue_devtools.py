"""Source adapter for Vue DevTools documentation.

Handles Vue DevTools-specific concerns:
  - ``<Home />`` and ``<UseModeList />`` component stripping
  - Standard VitePress ``.vitepress/config.ts`` sidebar parsing
  - Entity extraction from known API list + heading scan
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vue_devtools import VueDevToolsEntityExtractor

# Custom components to strip
_CUSTOM_COMPONENTS = ("Home", "UseModeList")
_COMPONENT_NAMES_RE = "|".join(_CUSTOM_COMPONENTS)

_VUE_COMPONENT_RE = re.compile(
    rf"^\s*<(?:{_COMPONENT_NAMES_RE})"
    r"(?:\s[^>]*)?\s*/?\s*>\s*$",
    re.MULTILINE,
)

# Root index.md is a VitePress hero landing page, not documentation content
_EXCLUDED_ROOT_FILES = frozenset({"index.md"})


class VueDevToolsAdapter:
    """Source adapter for Vue DevTools documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            if parts[0] in (".vitepress", "node_modules", "public"):
                continue

            if len(parts) == 1 and parts[0] in _EXCLUDED_ROOT_FILES:
                continue

            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse sort keys from the VitePress config.

        DevTools defines sidebar links in separate const arrays (GETTING_STARTED,
        GUIDES, etc.) referenced by variable name. We scan the full config file
        for all link patterns and assign sort keys by order of appearance.
        """
        config_path = repo_root / "docs" / ".vitepress" / "config.ts"
        if not config_path.exists():
            return {}

        raw = config_path.read_text(encoding="utf-8")
        result: dict[str, str] = {}
        link_re = re.compile(r"link:\s*'(/[^']+)'")

        for idx, m in enumerate(link_re.finditer(raw)):
            path = m.group(1).lstrip("/").rstrip("/")
            path = re.sub(r"\.html$", "", path)
            path = path.split("#")[0]
            if path:
                sort_key = f"00_{idx // 10:02d}_{idx % 10:02d}"
                result[path] = sort_key

        return result

    def clean_content(self, raw: str) -> str:
        result = _VUE_COMPONENT_RE.sub("", raw)
        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VueDevToolsEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VueDevToolsEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [{"getting-started", "plugins"}, {"guide", "plugins"}]
