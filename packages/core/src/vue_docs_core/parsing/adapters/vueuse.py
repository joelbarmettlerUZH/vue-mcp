"""Source adapter for VueUse documentation.

Handles VueUse-specific concerns:
  - Flat per-composable directory structure (``{package}/{functionName}/index.md``)
  - Frontmatter-based category sorting (no static sidebar config)
  - ``<CourseLink>`` component stripping
  - ``<script setup>`` block removal
  - TwoSlash cut markers and ``@include`` directives inside code fences
"""

import logging
import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vueuse import VueUseEntityExtractor, _parse_frontmatter

logger = logging.getLogger(__name__)

# Package directories containing composable function docs
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

# Root-level files to exclude (not useful for API documentation)
_EXCLUDED_ROOT_FILES = {
    "export-size.md",
    "team.md",
    "guidelines.md",
    "why-no-translations.md",
    "ecosystem.md",
}

# Root-level files to include beyond package/guide dirs
_INCLUDED_ROOT_FILES = {"index.md", "add-ons.md"}

# Content cleaning regexes
_COURSELINK_RE = re.compile(
    r"^\s*<CourseLink(?:\s[^>]*)?\s*/?\s*>\s*$",
    re.MULTILINE,
)
_COURSELINK_BLOCK_RE = re.compile(
    r"<CourseLink\b[^>]*>.*?</CourseLink>",
    re.DOTALL,
)

# <script setup> blocks at column 0 (not inside code fences)
_SCRIPT_SETUP_RE = re.compile(
    r"^<script\s+setup\b[^>]*>\n.*?^</script>\s*$",
    re.DOTALL | re.MULTILINE,
)

# TwoSlash markers (applied only inside code fences)
_CUT_START_RE = re.compile(r"^\s*//\s*---cut-start---\s*$")
_CUT_END_RE = re.compile(r"^\s*//\s*---cut-end---\s*$")
_INCLUDE_RE = re.compile(r"^\s*//\s*@include:\s*.+$")

# Guide pages in sidebar order
_GUIDE_ORDER = ["index", "best-practice", "config", "components", "work-with-ai"]


class VueUseAdapter:
    """Source adapter for VueUse documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No-op. VueUse docs are plain markdown with no build step."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all VueUse documentation markdown files.

        Includes composable docs (``{package}/{function}/index.md``),
        guide pages, and selected root-level pages. Excludes contributor/meta
        pages and the ``.vitepress/`` directory.
        """
        files: list[Path] = []

        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            # Skip .vitepress, node_modules, dist
            if parts[0] in (".vitepress", "node_modules", "dist", "metadata"):
                continue

            # Root-level files
            if len(parts) == 1:
                if rel.name in _INCLUDED_ROOT_FILES:
                    files.append(md_file)
                continue

            # Guide pages
            if parts[0] == "guide":
                files.append(md_file)
                continue

            # Package composable pages: {package}/{functionName}/index.md
            if parts[0] in _PACKAGE_DIRS and len(parts) == 3 and parts[2] == "index.md":
                files.append(md_file)
                continue

            # Components package top-level docs
            if parts[0] == "components" and parts[-1].endswith(".md"):
                files.append(md_file)
                continue

        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Build sort keys from frontmatter categories.

        VueUse has no static sidebar config. Instead, functions are grouped by
        their frontmatter ``category`` field. Guide pages get section 00,
        composable categories get sections 01+ sorted alphabetically.
        """
        docs_path = repo_root / "packages"
        if not docs_path.exists():
            return {}

        result: dict[str, str] = {}

        # Section 00: guide pages in fixed order
        for item_idx, name in enumerate(_GUIDE_ORDER):
            path = f"guide/{name}" if name != "index" else "guide/index"
            result[path] = f"00_00_{item_idx:02d}"

        # Root pages
        result["index"] = "00_01_00"
        result["add-ons"] = "00_01_01"

        # Collect categories from composable frontmatter
        category_functions: dict[str, list[str]] = {}

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

                raw = index_md.read_text(encoding="utf-8")
                fm = _parse_frontmatter(raw)
                category = fm.get("category", "Uncategorized")
                page_key = f"{pkg_name}/{fn_dir.name}/index"

                if category not in category_functions:
                    category_functions[category] = []
                category_functions[category].append(page_key)

        # Assign sort keys: categories sorted alphabetically -> section 01+
        for section_idx, category in enumerate(sorted(category_functions.keys()), start=1):
            for item_idx, page_key in enumerate(sorted(category_functions[category])):
                result[page_key] = f"{section_idx:02d}_00_{item_idx:02d}"

        return result

    def clean_content(self, raw: str) -> str:
        """Clean VueUse-specific content from markdown.

        Strips:
          - ``<CourseLink>`` components (self-closing and block forms)
          - ``<script setup>`` blocks at column 0
          - TwoSlash cut markers and ``@include`` directives inside code fences
          - ``twoslash`` language tag from code fence openings
        """
        result = raw

        # Remove <CourseLink> block form
        result = _COURSELINK_BLOCK_RE.sub("", result)

        # Remove self-closing <CourseLink> on their own line
        result = _COURSELINK_RE.sub("", result)

        # Remove <script setup>...</script> blocks
        result = _SCRIPT_SETUP_RE.sub("", result)

        # Process TwoSlash markers inside code fences
        result = self._clean_twoslash(result)

        return result

    def _clean_twoslash(self, text: str) -> str:
        """Remove TwoSlash artifacts from code fences."""
        lines = text.split("\n")
        output: list[str] = []
        in_fence = False
        in_cut = False

        for line in lines:
            # Track code fence boundaries
            stripped = line.lstrip()
            if stripped.startswith("```"):
                if not in_fence:
                    in_fence = True
                    # Strip 'twoslash' from the fence opening
                    line = re.sub(r"\btwoslash\b", "", line).rstrip()
                    output.append(line)
                    continue
                else:
                    in_fence = False
                    in_cut = False
                    output.append(line)
                    continue

            if in_fence:
                # Handle cut regions
                if _CUT_START_RE.match(line):
                    in_cut = True
                    continue
                if _CUT_END_RE.match(line):
                    in_cut = False
                    continue
                if in_cut:
                    continue
                # Strip @include directives
                if _INCLUDE_RE.match(line):
                    continue

            output.append(line)

        return "\n".join(output)

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VueUseEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VueUseEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [
            {"guide", "core"},
            {"guide", "shared"},
        ]
