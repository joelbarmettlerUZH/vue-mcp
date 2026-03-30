"""Source adapter for Vitest documentation.

Handles Vitest-specific concerns:
  - ``blog/`` and meta-page exclusion (team, todo, cli-generated)
  - ``<Version>``, ``<Deprecated>``, ``<Experimental>``, ``<CRoot>`` stripping
  - ``<CourseLink>`` and ``<Badge>`` component stripping
  - ``<img img-light>`` / ``<img img-dark>`` theme image stripping
  - ``<script setup>`` block removal (fence-aware)
  - Standard VitePress ``.vitepress/config.ts`` sidebar parsing
  - Entity extraction from known API list + heading scan
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vitest import VitestEntityExtractor
from vue_docs_core.parsing.sort_keys import parse_sidebar_config

# Files and directories to exclude from ingestion
_EXCLUDED_DIRS = frozenset({".vitepress", "node_modules", "blog", "public"})
_EXCLUDED_ROOT_FILES = frozenset(
    {
        "team.md",
        "todo.md",
        "blog.md",
        "index.md",
    }
)
_EXCLUDED_FILES = frozenset(
    {
        "guide/cli-generated.md",
    }
)
_EXCLUDED_PATH_PREFIXES = ("guide/examples/",)

# Custom components to strip (self-closing and block forms)
_CUSTOM_COMPONENTS = (
    "Version",
    "Deprecated",
    "Experimental",
    "CRoot",
    "CourseLink",
)
_COMPONENT_NAMES_RE = "|".join(_CUSTOM_COMPONENTS)

# Self-closing or empty: <Component ... /> or <Component>text</Component> on one line
_COMPONENT_SELF_RE = re.compile(
    rf"^\s*<(?:{_COMPONENT_NAMES_RE})"
    r"(?:\s[^>]*)?\s*/?\s*>\s*$",
    re.MULTILINE,
)
# Block form: <Component ...>...</Component>
_COMPONENT_BLOCK_RE = re.compile(
    rf"<(?:{_COMPONENT_NAMES_RE})\b[^>]*>.*?</(?:{_COMPONENT_NAMES_RE})>",
    re.DOTALL,
)
# <Badge> tags (inline, not block)
_BADGE_RE = re.compile(r"<Badge\b[^>]*>.*?</Badge>", re.DOTALL)

# Inline self-closing components (e.g., <CRoot /> used mid-sentence)
_INLINE_SELF_CLOSE_RE = re.compile(
    rf"<(?:{_COMPONENT_NAMES_RE})\b[^>]*/\s*>",
)

# <img img-light ...> and <img img-dark ...> theme images on their own line
_IMG_THEME_RE = re.compile(
    r"^\s*<img\s+img-(?:light|dark)\b[^>]*/?\s*>\s*$",
    re.MULTILINE,
)

# <script setup> open/close patterns for fence-aware stripping
_SCRIPT_SETUP_OPEN_RE = re.compile(r"^<script\s+setup\b[^>]*>\s*$")
_SCRIPT_CLOSE_RE = re.compile(r"^</script>\s*$")


class VitestAdapter:
    """Source adapter for Vitest documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for Vitest docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all markdown files, excluding blog, meta pages, and generated files."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts
            rel_str = str(rel)

            # Skip excluded directories
            if parts[0] in _EXCLUDED_DIRS:
                continue

            # Skip excluded root-level files
            if len(parts) == 1 and parts[0] in _EXCLUDED_ROOT_FILES:
                continue

            # Skip specific excluded files
            if rel_str in _EXCLUDED_FILES:
                continue

            # Skip excluded path prefixes
            if any(rel_str.startswith(prefix) for prefix in _EXCLUDED_PATH_PREFIXES):
                continue

            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse the VitePress sidebar config for sort key ordering."""
        config_path = repo_root / "docs" / ".vitepress" / "config.ts"
        if config_path.exists():
            return parse_sidebar_config(config_path)
        return {}

    def clean_content(self, raw: str) -> str:
        """Strip Vitest-specific noise from markdown content."""
        result = raw

        # Remove block-form custom components
        result = _COMPONENT_BLOCK_RE.sub("", result)

        # Remove self-closing custom components (own line)
        result = _COMPONENT_SELF_RE.sub("", result)

        # Remove inline self-closing components (mid-sentence)
        result = _INLINE_SELF_CLOSE_RE.sub("", result)

        # Remove <Badge> tags
        result = _BADGE_RE.sub("", result)

        # Remove theme-specific images
        result = _IMG_THEME_RE.sub("", result)

        # Remove <script setup>...</script> blocks only outside code fences
        result = _strip_script_setup(result)

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VitestEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VitestEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [{"guide", "api"}, {"guide", "config"}, {"api", "config"}]


def _strip_script_setup(text: str) -> str:
    """Remove standalone <script setup> blocks while preserving code fences."""
    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    in_script = False

    for line in lines:
        stripped = line.lstrip()

        # Track code fence boundaries
        if stripped.startswith("```"):
            in_fence = not in_fence
            output.append(line)
            continue

        if not in_fence:
            if not in_script and _SCRIPT_SETUP_OPEN_RE.match(line):
                in_script = True
                continue
            if in_script:
                if _SCRIPT_CLOSE_RE.match(line):
                    in_script = False
                continue

        output.append(line)

    return "\n".join(output)
