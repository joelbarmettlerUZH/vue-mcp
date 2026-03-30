"""Source adapter for Vite documentation.

Handles Vite-specific concerns:
  - ``blog/`` and meta-page exclusion (team, releases, acknowledgements)
  - ``<ScrimbaLink>`` and ``<audio>`` element stripping
  - ``<script setup>`` block removal
  - ``<!-- prettier-ignore -->`` comment removal
  - Standard VitePress ``.vitepress/config.ts`` sidebar parsing
  - Entity extraction from known API list + heading scan
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vite import ViteEntityExtractor
from vue_docs_core.parsing.sort_keys import parse_sidebar_config

# Files and directories to exclude from ingestion
_EXCLUDED_DIRS = frozenset({".vitepress", "node_modules", "blog", "public", "_data"})
_EXCLUDED_ROOT_FILES = frozenset(
    {
        "team.md",
        "releases.md",
        "acknowledgements.md",
        "live.md",
        "blog.md",
        "index.md",
    }
)

# Regexes for content cleaning
_SCRIMBA_LINK_BLOCK_RE = re.compile(
    r"<ScrimbaLink\b[^>]*>.*?</ScrimbaLink>",
    re.DOTALL,
)
_SCRIMBA_LINK_SELF_RE = re.compile(
    r"^\s*<ScrimbaLink\b[^>]*/>\s*$",
    re.MULTILINE,
)
_AUDIO_BLOCK_RE = re.compile(
    r"<audio\b[^>]*>.*?</audio>",
    re.DOTALL,
)
_AUDIO_SELF_RE = re.compile(
    r"^\s*<audio\b[^>]*/>\s*$",
    re.MULTILINE,
)
# <script setup> open/close patterns for fence-aware stripping
_SCRIPT_SETUP_OPEN_RE = re.compile(r"^<script\s+setup\b[^>]*>\s*$")
_SCRIPT_CLOSE_RE = re.compile(r"^</script>\s*$")
_PRETTIER_IGNORE_RE = re.compile(r"^\s*<!--\s*prettier-ignore\s*-->\s*$", re.MULTILINE)


class ViteAdapter:
    """Source adapter for Vite documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for Vite docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all markdown files, excluding blog, meta pages, and build artifacts."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            # Skip excluded directories
            if parts[0] in _EXCLUDED_DIRS:
                continue

            # Skip excluded root-level files
            if len(parts) == 1 and parts[0] in _EXCLUDED_ROOT_FILES:
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
        """Strip Vite-specific noise from markdown content."""
        result = raw

        # Remove <ScrimbaLink>...</ScrimbaLink> block form
        result = _SCRIMBA_LINK_BLOCK_RE.sub("", result)

        # Remove self-closing <ScrimbaLink ... />
        result = _SCRIMBA_LINK_SELF_RE.sub("", result)

        # Remove <audio>...</audio> block form
        result = _AUDIO_BLOCK_RE.sub("", result)

        # Remove self-closing <audio ... />
        result = _AUDIO_SELF_RE.sub("", result)

        # Remove <!-- prettier-ignore --> comments
        result = _PRETTIER_IGNORE_RE.sub("", result)

        # Remove <script setup>...</script> blocks only outside code fences
        result = self._strip_script_setup(result)

        return result

    @staticmethod
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

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return ViteEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return ViteEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [{"guide", "config"}]
