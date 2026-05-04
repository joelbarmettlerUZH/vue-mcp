"""Source adapter for shadcn-vue documentation.

shadcn-vue's docs live in the main repo at ``apps/v4/content/docs`` and
are powered by Nuxt + Nuxt Content. The MDC syntax is similar to FormKit
but with a different vocabulary specific to component-library docs:

  - ``::component-preview`` — live demo wrapper, dropped
  - ``::component-source`` — source-code embed, dropped
  - ``::vue-school-link`` — educational link, dropped
  - ``::callout`` — pedagogy, unwrapped (content kept)
  - ``::code-tabs`` / ``::tabs`` / ``::tabs-list`` /
    ``::tabs-trigger`` / ``::tabs-content`` — tab UI for CLI vs Manual
    install. Unwrapped so the actual code blocks survive.
  - ``::code-collapsible-wrapper`` — drops the wrapper, keeps the code.
  - ``::steps`` / ``::step`` — instructional step blocks, unwrapped.

File discovery:
  - Docs root is ``apps/v4/content/docs``
  - Numbered files (``01.introduction.md``, …) drive top-level ordering
  - ``components/*.md`` is unnumbered (one file per component)
  - Hidden / draft files (Nuxt Content convention: prefix ``.``) are
    skipped along with the legacy ``deprecated/`` tree at the repo root
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.shadcn_vue import ShadcnVueEntityExtractor

# Top-level section ordering. Anything not listed sorts alphabetically
# after the numbered roots via the file-prefix fallback.
_TOP_LEVEL_FOLDERS_AFTER_ROOT: dict[str, int] = {
    "components": 50,
    "forms": 51,
    "installation": 52,
    "dark-mode": 53,
    "registry": 54,
}

# Numeric-prefix regex on either folders or files: ``02.installation`` or
# ``02.installation.md``.
_NUMERIC_PREFIX_RE = re.compile(r"^(\d+)\.")

# YAML frontmatter delimiter (Nuxt Content style).
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# MDC block matcher: ``::Component\n...\n::`` with optional ``{attrs}`` after the name.
# The closing ``::`` may be indented when blocks are nested (e.g. ``::tabs-trigger``
# living inside ``::tabs-list``), so allow leading whitespace on it.
def _block_re(name_pattern: str) -> re.Pattern:
    return re.compile(
        rf"^[ \t]*::{name_pattern}(?:\{{[^}}]*\}})?[ \t]*\n(.*?)^[ \t]*::[ \t]*$",
        re.DOTALL | re.MULTILINE,
    )


# Drop entirely (live demos / source embeds / marketing).
_DROP_BLOCK_NAMES = (
    "component-preview",
    "component-source",
    "vue-school-link",
)
_DROP_BLOCK_RE = _block_re("(?:" + "|".join(_DROP_BLOCK_NAMES) + ")")
_DROP_SELF_RE = re.compile(
    r"^[ \t]*::(?:" + "|".join(_DROP_BLOCK_NAMES) + r")(?:\{[^}]*\})?[ \t]*\n[ \t]*::[ \t]*$",
    re.MULTILINE,
)
# Inline form: ``:vue-school-link{...}`` — drop entirely.
_INLINE_DROP_NAMES = (
    "vue-school-link",
    "component-source",
)
_INLINE_DROP_RE = re.compile(
    r":(?:" + "|".join(_INLINE_DROP_NAMES) + r")(?:\{[^}]*\})?",
)

# Unwrap (drop the wrapper, keep inner content).
_UNWRAP_BLOCK_NAMES = (
    "callout",
    "code-collapsible-wrapper",
    "code-tabs",
    "tabs-list",
    "tabs-trigger",
    "tabs-content",
    "tabs",
    "steps",
    "step",
)
_UNWRAP_BLOCK_RE = _block_re("(?:" + "|".join(_UNWRAP_BLOCK_NAMES) + ")")


class ShadcnVueAdapter:
    """Source adapter for shadcn-vue documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed — Nuxt Content reads markdown directly."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all v4 markdown files, excluding hidden / draft files."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            # Hidden / draft files anywhere in the path (Nuxt Content
            # treats files starting with ``.`` as drafts).
            if any(p.startswith(".") for p in rel.parts):
                continue
            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Derive sort keys from numeric prefixes and folder ordering.

        ``02.installation.md`` → ``02_00_002``.
        ``components/button.md`` → ``50_00_999`` (folder index 50 — comes
        after numbered root files; alphabetical within folder via 999
        fallback handled by the pipeline's standard sort).
        """
        result: dict[str, str] = {}
        docs_path = repo_root / "apps" / "v4" / "content" / "docs"
        if not docs_path.exists():
            return {}

        for f in self.discover_files(docs_path):
            rel = f.relative_to(docs_path)
            parts = rel.parts

            if len(parts) == 1:
                # Root-level file — use its numeric prefix.
                m = _NUMERIC_PREFIX_RE.match(parts[0])
                section_idx = int(m.group(1)) if m else 99
                file_idx = 0
            else:
                # File inside a folder.
                folder = parts[0]
                section_idx = _TOP_LEVEL_FOLDERS_AFTER_ROOT.get(folder, 99)
                # File index from numeric prefix on the leaf filename.
                leaf = parts[-1]
                m = _NUMERIC_PREFIX_RE.match(leaf)
                file_idx = int(m.group(1)) if m else 999

            page_path = str(rel).removesuffix(".md")
            result[page_path] = f"{section_idx:02d}_00_{file_idx:03d}"

        return result

    def clean_content(self, raw: str) -> str:
        """Strip frontmatter, drop demo/marketing blocks, unwrap pedagogy
        and tab structures so their content survives."""
        result = raw

        # 1. YAML frontmatter.
        result = _FRONTMATTER_RE.sub("", result, count=1)

        # 2. Drop live-demo / source / marketing blocks.
        result = _DROP_BLOCK_RE.sub("", result)
        result = _DROP_SELF_RE.sub("", result)

        # 3. Inline shortcode drops (``:vue-school-link{...}``).
        result = _INLINE_DROP_RE.sub("", result)

        # 4. Unwrap pedagogy + tab UI structures (keep their code/content).
        # We loop because tabs nest: ``::code-tabs > ::tabs-list > ::tabs-trigger``.
        # A single pass leaves residual inner blocks; iterate until stable.
        for _ in range(6):
            new = _UNWRAP_BLOCK_RE.sub(lambda m: m.group(1), result)
            if new == result:
                break
            result = new

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return ShadcnVueEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return ShadcnVueEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        # Components-to-installation (how to add) and components-to-forms
        # (how to wire into form libraries) are the canonical jumps.
        return [{"components", "installation"}, {"components", "forms"}]
