"""Source adapter for Pinia documentation.

Handles Pinia-specific concerns:
  - ``zh/`` i18n directory exclusion
  - Split VitePress config with catch-all ``'/'`` sidebar key
  - ``<RuleKitLink>``, ``<MasteringPiniaLink>``, ``<VueSchoolLink>`` stripping
  - ``<script setup>`` block removal
  - Optional TypeDoc API generation (graceful skip without npm/node)
  - Entity extraction from known API list + heading scan
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.pinia import PiniaEntityExtractor

logger = logging.getLogger(__name__)

# Custom Vue components to strip (sponsorship, educational, promotional)
_CUSTOM_COMPONENTS = (
    "RuleKitLink",
    "MasteringPiniaLink",
    "VueSchoolLink",
    "VueMasteryLogoLink",
    "HomeSponsors",
)
_COMPONENT_NAMES_RE = "|".join(_CUSTOM_COMPONENTS)

# Self-closing: <Component ... /> or <Component></Component> on one line
_VUE_COMPONENT_RE = re.compile(
    rf"^\s*<(?:{_COMPONENT_NAMES_RE})"
    r"(?:\s[^>]*)?\s*/?\s*>\s*$",
    re.MULTILINE,
)
# Block form: <Component ...>...</Component>
_VUE_COMPONENT_BLOCK_RE = re.compile(
    rf"<(?:{_COMPONENT_NAMES_RE})\b[^>]*>.*?</(?:{_COMPONENT_NAMES_RE})>",
    re.DOTALL,
)
# <script setup> open/close for fence-aware stripping
_SCRIPT_SETUP_OPEN_RE = re.compile(r"^<script\s+setup\b[^>]*>\s*$")
_SCRIPT_CLOSE_RE = re.compile(r"^</script>\s*$")

# Sidebar parsing
_LINK_RE = re.compile(r"link:\s*'(/[^']*)'")
_ITEMS_RE = re.compile(r"items\s*:\s*\[")
_SECTION_RE = re.compile(r"'(/?[\w-]*/?)'\s*:\s*\[")


class PiniaAdapter:
    """Source adapter for Pinia documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """Generate TypeDoc API docs if not already present.

        Requires npm and node. Gracefully skips if unavailable.
        """
        docs_dir = repo_root / "packages" / "docs"
        api_dir = docs_dir / "api"

        if api_dir.exists() and any(api_dir.rglob("*.md")):
            logger.info("TypeDoc API docs already exist, skipping generation")
            return

        if not shutil.which("npm") or not shutil.which("node"):
            logger.info("npm/node not available, skipping TypeDoc generation")
            return

        root_pkg = repo_root / "package.json"
        if root_pkg.exists():
            result = subprocess.run(
                ["npm", "install", "--ignore-scripts"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning("npm install failed: %s", result.stderr[:500])

        typedoc_config = docs_dir / "typedoc.tsconfig.json"
        if not typedoc_config.exists():
            logger.info("typedoc config not found, skipping TypeDoc generation")
            return

        logger.info("Generating TypeDoc API docs...")
        result = subprocess.run(
            ["npx", "typedoc", "--options", str(typedoc_config)],
            cwd=str(docs_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "TypeDoc generation failed (will use seed entities): %s",
                result.stderr[:500],
            )

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all English markdown files, excluding zh/ translations."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts
            if parts[0] == "zh":
                continue
            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse the split VitePress config for Pinia.

        Handles the catch-all ``'/'`` sidebar key and ``'/api/'`` key.
        """
        config_path = repo_root / "packages" / "docs" / ".vitepress" / "config" / "en.ts"
        if not config_path.exists():
            return {}

        raw = config_path.read_text(encoding="utf-8")
        result: dict[str, str] = {}

        for section_idx, section_match in enumerate(_SECTION_RE.finditer(raw)):
            start = section_match.end()

            depth = 1
            pos = start
            while depth > 0 and pos < len(raw):
                if raw[pos] == "[":
                    depth += 1
                elif raw[pos] == "]":
                    depth -= 1
                pos += 1

            section_text = raw[start : pos - 1]
            self._extract_links(section_text, section_idx, result)

        return result

    def _extract_links(self, section_text: str, section_idx: int, result: dict[str, str]) -> None:
        """Extract link paths and assign sort keys from a sidebar section."""
        group_idx = -1
        item_idx = 0

        for line in section_text.split("\n"):
            if _ITEMS_RE.search(line):
                group_idx += 1
                item_idx = 0

            lm = _LINK_RE.search(line)
            if lm:
                path = lm.group(1).lstrip("/").rstrip("/")
                path = re.sub(r"\.html$", "", path)
                path = path.split("#")[0]

                if path:
                    sort_key = f"{section_idx:02d}_{max(0, group_idx):02d}_{item_idx:02d}"
                    result[path] = sort_key
                    item_idx += 1

    def clean_content(self, raw: str) -> str:
        """Strip Pinia-specific promotional components and script setup blocks."""
        result = raw

        # Remove block-form components
        result = _VUE_COMPONENT_BLOCK_RE.sub("", result)

        # Remove self-closing components on their own line
        result = _VUE_COMPONENT_RE.sub("", result)

        # Remove <script setup>...</script> blocks (fence-aware)
        result = _strip_script_setup(result)

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return PiniaEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return PiniaEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [{"core-concepts", "cookbook"}, {"core-concepts", "api"}]


def _strip_script_setup(text: str) -> str:
    """Remove standalone <script setup> blocks while preserving code fences."""
    lines = text.split("\n")
    output: list[str] = []
    in_fence = False
    in_script = False

    for line in lines:
        stripped = line.lstrip()

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
