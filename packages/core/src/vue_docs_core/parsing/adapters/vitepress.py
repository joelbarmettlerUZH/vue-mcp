"""Source adapter for VitePress documentation.

Handles VitePress-specific concerns:
  - Multi-locale repo layout: docs live under ``docs/en`` (other languages
    such as ``zh/``, ``pt/``, ``ja/`` etc. live as siblings and are excluded
    by setting ``docs_subpath`` to ``docs/en``).
  - Sidebar config at ``docs/config.ts`` (sibling of ``en/``), using the
    ``defineAdditionalConfig`` shape with a per-section ``base`` and bare
    relative ``link`` values that need the ``base`` re-applied.
  - ``<Badge>`` markup stripping (heading-trailing badges and inline forms).
  - ``<script setup>`` and ``<script client>`` block removal.
  - ``<VPTeamMembers />``, ``<VPTeamPage>...</VPTeamPage>`` block removal.
  - Entity extraction via the dedicated VitePress extractor.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vitepress import VitePressEntityExtractor

# Files and directories to exclude from ingestion within docs/en.
_EXCLUDED_DIRS = frozenset({".vitepress", "node_modules", "public", "snippets", "components"})
_EXCLUDED_ROOT_FILES = frozenset({"index.md"})

# <Badge type="info" text="composable" /> — both self-closing and block form.
_BADGE_SELF_RE = re.compile(r"<Badge\b[^>]*/>")
_BADGE_BLOCK_RE = re.compile(r"<Badge\b[^>]*>.*?</Badge>", re.DOTALL)

# <VPTeam*> components only appear in team/contributor pages, but strip
# defensively in case they show up in regular content.
_VPTEAM_BLOCK_RE = re.compile(
    r"<VPTeam(?:Members|Page|PageTitle|PageSection)\b[^>]*>.*?"
    r"</VPTeam(?:Members|Page|PageTitle|PageSection)>",
    re.DOTALL,
)
_VPTEAM_SELF_RE = re.compile(
    r"^\s*<VPTeam(?:Members|Page|PageTitle|PageSection)\b[^>]*/>\s*$",
    re.MULTILINE,
)

# <script setup> / <script client> open/close — fence-aware stripping.
_SCRIPT_OPEN_RE = re.compile(r"^<script\s+(?:setup|client)\b[^>]*>\s*$")
_SCRIPT_CLOSE_RE = re.compile(r"^</script>\s*$")

# Sidebar parsing for the VitePress repo's docs/config.ts shape.
#
#   sidebar: {
#     '/guide/': { base: '/guide/', items: sidebarGuide() },
#     '/reference/': { base: '/reference/', items: sidebarReference() }
#   }
#
#   function sidebarGuide() {
#     return [
#       { text: 'Introduction', items: [
#         { text: 'What is VitePress?', link: 'what-is-vitepress' }, ...
#       ]}, ...
#     ]
#   }
#
# Section keys carry the base prefix; links are bare names that need the
# base reapplied to match the on-disk page paths (guide/what-is-vitepress).
_FUNCTION_RE = re.compile(r"function\s+(sidebar\w+)\s*\(")
_SIDEBAR_KEY_RE = re.compile(r"'(/(?:[\w-]+/?))'\s*:\s*\{[^}]*?items\s*:\s*(\w+)\s*\(")
_ITEMS_RE = re.compile(r"\bitems\s*:\s*\[")
_LINK_RE = re.compile(r"link\s*:\s*'([^']+)'")


class VitePressAdapter:
    """Source adapter for VitePress documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for VitePress docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all English markdown files under docs/en, skipping the
        homepage, snippets, public assets, and the components directory."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            if parts[0] in _EXCLUDED_DIRS:
                continue
            if len(parts) == 1 and parts[0] in _EXCLUDED_ROOT_FILES:
                continue

            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Parse the VitePress repo's ``docs/config.ts`` sidebar.

        The sidebar uses ``{ base: '/guide/', items: sidebarGuide() }`` form
        and ``link: 'what-is-vitepress'`` bare values. The on-disk path for
        each entry is ``{base without slashes}/{link}``, e.g.
        ``guide/what-is-vitepress``.
        """
        config_path = repo_root / "docs" / "config.ts"
        if not config_path.exists():
            return {}

        raw = config_path.read_text(encoding="utf-8")
        result: dict[str, str] = {}

        # Map from the section key ('/guide/') to the function name that
        # builds its items array ('sidebarGuide').
        section_to_fn: dict[str, str] = {}
        for m in _SIDEBAR_KEY_RE.finditer(raw):
            section_to_fn[m.group(1)] = m.group(2)

        # Locate each builder function body and extract links in order.
        function_bodies = self._extract_function_bodies(raw)

        for section_idx, (section_key, fn_name) in enumerate(section_to_fn.items()):
            base = section_key.strip("/")
            body = function_bodies.get(fn_name, "")

            group_idx = -1
            item_idx = 0
            for line in body.split("\n"):
                if _ITEMS_RE.search(line):
                    group_idx += 1
                    item_idx = 0
                lm = _LINK_RE.search(line)
                if lm:
                    link = lm.group(1).lstrip("/").rstrip("/")
                    link = re.sub(r"\.html$", "", link)
                    link = link.split("#")[0]
                    if not link:
                        continue
                    # Reattach the section base unless the link already
                    # carries one (defensive against future refactors).
                    if base and not link.startswith(f"{base}/"):
                        path = f"{base}/{link}"
                    else:
                        path = link
                    sort_key = f"{section_idx:02d}_{max(0, group_idx):02d}_{item_idx:02d}"
                    result[path] = sort_key
                    item_idx += 1

        return result

    @staticmethod
    def _extract_function_bodies(raw: str) -> dict[str, str]:
        """Return ``{function_name: body_text}`` for each top-level
        ``function sidebar*()`` declaration in the config file."""
        bodies: dict[str, str] = {}
        for m in _FUNCTION_RE.finditer(raw):
            name = m.group(1)
            # Skip past the parameter list and the opening brace of the body.
            i = raw.find("{", m.end())
            if i == -1:
                continue
            depth = 1
            j = i + 1
            while j < len(raw) and depth > 0:
                if raw[j] == "{":
                    depth += 1
                elif raw[j] == "}":
                    depth -= 1
                j += 1
            bodies[name] = raw[i + 1 : j - 1]
        return bodies

    def clean_content(self, raw: str) -> str:
        """Strip VitePress-specific noise from markdown content."""
        result = raw

        # Remove <Badge> markup (block form first to avoid leaving </Badge>).
        result = _BADGE_BLOCK_RE.sub("", result)
        result = _BADGE_SELF_RE.sub("", result)

        # Remove <VPTeam*> blocks (only appear in team/contributor pages).
        result = _VPTEAM_BLOCK_RE.sub("", result)
        result = _VPTEAM_SELF_RE.sub("", result)

        # Remove <script setup>/<script client> blocks outside code fences.
        result = self._strip_script_blocks(result)

        return result

    @staticmethod
    def _strip_script_blocks(text: str) -> str:
        """Remove standalone <script setup|client> blocks while preserving
        code fences."""
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
                if not in_script and _SCRIPT_OPEN_RE.match(line):
                    in_script = True
                    continue
                if in_script:
                    if _SCRIPT_CLOSE_RE.match(line):
                        in_script = False
                    continue

            output.append(line)

        return "\n".join(output)

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VitePressEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VitePressEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        # Guide-to-reference is the canonical concept-to-API jump for
        # VitePress, mirroring Vite's guide-to-config classification.
        return [{"guide", "reference"}]
