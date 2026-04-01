"""Source adapter for Nuxt documentation.

Handles Nuxt-specific concerns:
  - Nuxt Content documentation framework (not VitePress)
  - Numeric-prefix-based sort keys from file/directory names
  - ``5.community/`` directory exclusion
  - ``:read-more``, ``:video-accordion``, ``:link-example`` directive stripping
  - Entity extraction from known API list + heading scan
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.nuxt import NuxtEntityExtractor

# Directories to exclude from ingestion
_EXCLUDED_DIRS = frozenset({"5.community", "node_modules"})

# Inline Nuxt Content directives to strip (navigation links, video embeds)
_READ_MORE_RE = re.compile(r"^::read-more\{[^}]*\}\s*$", re.MULTILINE)
_VIDEO_ACCORDION_RE = re.compile(r"^\s*:video-accordion\{[^}]*\}\s*$", re.MULTILINE)
_LINK_EXAMPLE_RE = re.compile(r"^::link-example\{[^}]*\}\s*$", re.MULTILINE)

# Regex to extract numeric prefix from a path component (e.g., "01.introduction" -> (1, "introduction"))
_NUMERIC_PREFIX_RE = re.compile(r"^(\d+)\.(.+)")


class NuxtAdapter:
    """Source adapter for Nuxt documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for Nuxt docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all markdown files, excluding community and navigation configs."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            # Skip excluded directories
            if parts[0] in _EXCLUDED_DIRS:
                continue

            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Build sort keys from numeric file/directory name prefixes.

        Nuxt Content uses numeric prefixes for ordering:
        ``1.getting-started/01.introduction.md`` -> sort key ``01_00_01``,
        page path key ``getting-started/introduction``.
        """
        docs_path = repo_root / "docs"
        if not docs_path.exists():
            return {}

        result: dict[str, str] = {}

        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            # Skip excluded directories
            if parts[0] in _EXCLUDED_DIRS:
                continue

            # Extract numeric prefixes and clean path components
            nums: list[int] = []
            clean_parts: list[str] = []

            for part in parts:
                # Remove .md extension from last part
                name = part
                if name.endswith(".md"):
                    name = name[:-3]

                m = _NUMERIC_PREFIX_RE.match(name)
                if m:
                    nums.append(int(m.group(1)))
                    clean_parts.append(m.group(2))
                else:
                    nums.append(99)  # No prefix -> sort after numbered items
                    clean_parts.append(name)

            # Build sort key: pad to 3 levels (section, subsection, item)
            while len(nums) < 3:
                nums.append(0)

            sort_key = f"{nums[0]:02d}_{nums[1]:02d}_{nums[2]:02d}"

            # Build page path key (stripped of numeric prefixes and .md)
            page_path = "/".join(clean_parts)
            if page_path.endswith("/index"):
                page_path = page_path[:-6]  # Strip trailing /index

            result[page_path] = sort_key

        return result

    def clean_content(self, raw: str) -> str:
        """Strip Nuxt Content directives that are navigation/embed noise.

        Preserves ``::note``, ``::tip``, ``::warning`` blocks as they contain
        useful documentation content.
        """
        result = raw

        # Remove :read-more{...} directives
        result = _READ_MORE_RE.sub("", result)

        # Remove :video-accordion{...} directives
        result = _VIDEO_ACCORDION_RE.sub("", result)

        # Remove :link-example{...} directives
        result = _LINK_EXAMPLE_RE.sub("", result)

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return NuxtEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return NuxtEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [
            {"getting-started", "api"},
            {"guide", "api"},
            {"directory-structure", "api"},
        ]
