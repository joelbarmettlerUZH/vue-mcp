"""Source adapter for Vue.js core documentation.

Handles Vue-specific concerns:
  - ``<div class="options-api/composition-api">`` wrapper stripping
  - ``[Try it in the Playground]`` link removal
  - Single-file ``.vitepress/config.ts`` sidebar parsing
  - Entity extraction from ``/api/`` folder via heading scan
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vue import VueEntityExtractor
from vue_docs_core.parsing.sort_keys import parse_sidebar_config

# Regexes for Vue-specific content cleaning (must match the old markdown.py patterns)
_API_DIV_OPEN_RE = re.compile(r'^\s*<div\s+class="(options-api|composition-api)">\s*$')
_DIV_CLOSE_RE = re.compile(r"^\s*</div>\s*$")
_PLAYGROUND_RE = re.compile(r"\[Try it in the Playground\]\([^)]+\)\s*")


class VueAdapter:
    """Source adapter for Vue.js core documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for Vue docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        return sorted(docs_path.rglob("*.md"))

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        config_path = repo_root / ".vitepress" / "config.ts"
        if config_path.exists():
            return parse_sidebar_config(config_path)
        return {}

    def clean_content(self, raw: str) -> str:
        # Strip <div class="options-api/composition-api"> and their closing </div>
        # We need stateful tracking to only remove </div> that close API divs
        lines = raw.split("\n")
        cleaned: list[str] = []
        api_div_depth = 0

        for line in lines:
            # Track and remove API-style div wrappers
            if _API_DIV_OPEN_RE.match(line):
                api_div_depth += 1
                continue
            if _DIV_CLOSE_RE.match(line) and api_div_depth > 0:
                api_div_depth -= 1
                continue

            # Remove playground links
            if _PLAYGROUND_RE.search(line):
                line = _PLAYGROUND_RE.sub("", line)
                if not line.strip():
                    continue

            cleaned.append(line)

        return "\n".join(cleaned)

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VueEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VueEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [{"guide", "api"}]
