"""Source adapter for Vue Router documentation.

Handles Vue Router-specific concerns:
  - TypeDoc API generation after clone
  - ``zh/`` i18n directory exclusion
  - Split VitePress config with catch-all ``'/'`` sidebar key
  - ``<VueSchoolLink>``, ``<RuleKitLink>``, ``<HomeSponsors>`` stripping
  - ``<script setup>`` block removal
  - Entity extraction from known API list + TypeDoc-generated headings
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vue_router import VueRouterEntityExtractor

logger = logging.getLogger(__name__)

# Regexes for content cleaning
# Custom Vue components to strip (sponsorship, educational, promotional)
_CUSTOM_COMPONENTS = (
    "VueSchoolLink",
    "RuleKitLink",
    "HomeSponsors",
    "VueMasteryLogoLink",
    "VueMasteryBanner",
    "VuejsdeConfBanner",
    "MadVueBanner",
    "AsideSponsors",
)
_COMPONENT_NAMES_RE = "|".join(_CUSTOM_COMPONENTS)

# Self-closing: <Component ... />  or empty: <Component></Component>
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
# Only match <script setup> blocks that are NOT inside code fences.
# These blocks start at column 0 (not indented, not inside ```) and span
# multiple lines ending with </script> also at column 0.
_SCRIPT_SETUP_RE = re.compile(
    r"^<script\s+setup\b[^>]*>\n.*?^</script>\s*$",
    re.DOTALL | re.MULTILINE,
)

# Sidebar parsing
_LINK_RE = re.compile(r"link:\s*'(/[^']*)'")
_ITEMS_RE = re.compile(r"items\s*:\s*\[")
_SECTION_RE = re.compile(r"'(/?[\w-]*/?)'\s*:\s*\[")


class VueRouterAdapter:
    """Source adapter for Vue Router documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """Generate TypeDoc API docs if not already present.

        Requires ``npm`` and ``node`` to be available.  If they are not
        (e.g. inside a Docker image without Node.js), this is a no-op and
        the entity dictionary falls back to the seed list.
        """
        docs_dir = repo_root / "packages" / "docs"
        api_dir = docs_dir / "api"

        if api_dir.exists() and any(api_dir.rglob("*.md")):
            logger.info("TypeDoc API docs already exist, skipping generation")
            return

        typedoc_script = docs_dir / "run-typedoc.mjs"
        if not typedoc_script.exists():
            logger.warning("run-typedoc.mjs not found, cannot generate API docs")
            return

        # Check if npm/node are available before attempting
        if not shutil.which("npm") or not shutil.which("node"):
            logger.info("npm/node not available, skipping TypeDoc generation")
            return

        logger.info("Installing docs dependencies for TypeDoc generation...")
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
                logger.warning("npm install (root) failed: %s", result.stderr[:500])

        logger.info("Generating TypeDoc API docs...")
        result = subprocess.run(
            ["node", "run-typedoc.mjs"],
            cwd=str(docs_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "TypeDoc generation failed (API docs will use seed entities only): %s",
                result.stderr[:500],
            )
        elif api_dir.exists():
            count = len(list(api_dir.rglob("*.md")))
            logger.info("TypeDoc generated %d API doc files", count)

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all English markdown files, excluding zh/ translations."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts
            # Skip Chinese translations
            if parts[0] == "zh":
                continue
            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse the split VitePress config for Vue Router.

        Handles:
          - ``config/en.ts`` with a catch-all ``'/'`` sidebar key
          - Inline function bodies (``sidebarFileBasedRouting``, ``sidebarDataLoaders``)
        """
        config_path = repo_root / "packages" / "docs" / ".vitepress" / "config" / "en.ts"
        if not config_path.exists():
            return {}

        raw = config_path.read_text(encoding="utf-8")
        result: dict[str, str] = {}

        # Parse all sidebar sections (including catch-all '/')
        for section_idx, section_match in enumerate(_SECTION_RE.finditer(raw)):
            start = section_match.end()

            # Find matching closing bracket
            depth = 1
            pos = start
            while depth > 0 and pos < len(raw):
                if raw[pos] == "[":
                    depth += 1
                elif raw[pos] == "]":
                    depth -= 1
                pos += 1

            section_text = raw[start : pos - 1]
            self._extract_links_from_section(section_text, section_idx, result)

        # Parse function bodies for file-based-routing and data-loaders
        # These are called inline in the sidebar as sidebarFileBasedRouting()
        # and sidebarDataLoaders(), but their definitions have the actual links
        for func_name in ("sidebarFileBasedRouting", "sidebarDataLoaders"):
            func_match = re.search(rf"function\s+{func_name}\s*\([^)]*\)\s*\{{", raw)
            if not func_match:
                continue
            start = func_match.end()
            depth = 1
            pos = start
            while depth > 0 and pos < len(raw):
                if raw[pos] == "{":
                    depth += 1
                elif raw[pos] == "}":
                    depth -= 1
                pos += 1
            func_body = raw[start : pos - 1]
            # Use section_idx continuing from the sidebar sections
            # The function items are part of the catch-all section so they
            # get the next group index within the same logical section
            section_idx_for_func = 0  # They belong to the '/' section
            # Count existing groups to continue numbering
            existing_groups = max(
                (int(v.split("_")[1]) for v in result.values() if v.startswith("00_")),
                default=-1,
            )
            self._extract_links_from_section(
                func_body, section_idx_for_func, result, group_offset=existing_groups + 1
            )

        return result

    def _extract_links_from_section(
        self,
        section_text: str,
        section_idx: int,
        result: dict[str, str],
        group_offset: int = 0,
    ) -> None:
        """Extract link paths and assign sort keys from a sidebar section."""
        group_idx = group_offset - 1
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
        result = raw

        # Remove <VueSchoolLink ...>...</VueSchoolLink> block form
        result = _VUE_COMPONENT_BLOCK_RE.sub("", result)

        # Remove self-closing Vue components on their own line
        result = _VUE_COMPONENT_RE.sub("", result)

        # Remove <script setup>...</script> blocks
        result = _SCRIPT_SETUP_RE.sub("", result)

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VueRouterEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VueRouterEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        return [
            {"guide", "api"},
            {"guide", "data-loaders"},
            {"guide", "file-based-routing"},
        ]
