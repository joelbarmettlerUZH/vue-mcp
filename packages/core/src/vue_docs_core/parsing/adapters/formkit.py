"""Source adapter for FormKit documentation.

FormKit's docs live in a dedicated content repo (``formkit/docs-content``)
that powers formkit.com. The structure uses numbered folders + files for
deterministic navigation, plus Nuxt-Content / MDC syntax for rich blocks
(``::Component`` blocks, ``:component{...}`` inline shortcodes).

Numbered hierarchy:
    1.getting-started/
    2.essentials/
    3.inputs/             (one file per input type, no numeric prefix)
    4.plugins/            (one file per official plugin)
    5.guides/
    6.api-reference/      (one file per @formkit/* package)

Plus auxiliary folders we exclude: ``_changelog``, ``_changelog-pro``,
``_examples``, ``_install``, ``_marketing``, and root meta pages
(README, terms, privacy).

Content cleanup:
  - YAML frontmatter (Nuxt-Content style)
  - ``::api-entry{name="..." type="..."}`` wrappers (entries unwrapped, content kept)
  - Promotional / nav components fully dropped:
      ::ArticleCard, ::Cta, ::DocsButton, ::ExampleCard*, ::VideoCard,
      ::Sponsors, ::Link*, ::NpxSkillCta, ::InstallWizard, ::Example
  - Pedagogy components unwrapped (content preserved):
      ::Callout, ::callout, ::ReferenceTable
  - ``::FrameworkOnly{framework="react"} ... ::`` blocks dropped entirely
  - ``::FrameworkOnly{framework="vue"} ... ::`` blocks unwrapped
  - Inline shortcodes ``:InputPageHero``, ``:FormKitInputDiagrams{...}``,
    ``:CurrentTime``, ``:Sponsors`` — dropped
  - ``:FrameworkText{vue="..." react="..."}`` — replaced with the vue text
  - HTML wrappers (``<Sponsors>``, ``<LinkDiscord>``, ``<ExampleCardGrid>``,
    ``<LinkGithub>``, ``<LinkLocaleBuilder>``, ``<LinkStackOverflow>``,
    ``<InputChecklist>``) dropped
  - ``<FormKit>``, ``<FormKitSchema>``, ``<FormKitMessages>`` are FormKit's
    own API components and intentionally preserved.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.formkit import FormKitEntityExtractor

# Folders + meta files to skip.
_EXCLUDED_DIRS = frozenset({"_changelog", "_changelog-pro", "_examples", "_install", "_marketing"})
_EXCLUDED_ROOT_FILES = frozenset({"README.md", "privacy.md", "terms.md", "terms-unlimited.md"})

# Section indices, derived from the numeric folder prefixes.
_SECTION_INDEX: dict[str, int] = {
    "1.getting-started": 1,
    "2.essentials": 2,
    "3.inputs": 3,
    "4.plugins": 4,
    "5.guides": 5,
    "6.api-reference": 6,
}

# Numeric prefix on a folder or file name: ``2.essentials`` or ``3.your-first-form.md``.
_NUMERIC_PREFIX_RE = re.compile(r"^(\d+)\.")

# YAML frontmatter delimiter.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# MDC blocks: ``::Component\n...\n::`` (with optional ``{attrs}`` after the name).
# We match one block at a time, non-greedy, with the closing ``::`` on its own line.
def _block_re(name_pattern: str, *, dotall: bool = True) -> re.Pattern:
    flags = re.DOTALL | re.MULTILINE if dotall else re.MULTILINE
    return re.compile(
        rf"^::{name_pattern}(?:\{{[^}}]*\}})?\s*\n(.*?)^::\s*$",
        flags,
    )


# Promo / nav components — drop the whole block (we don't keep inner content).
_DROP_BLOCK_NAMES = (
    "ArticleCard",
    "Cta",
    "DocsButton",
    "ExampleCardGrid",
    "ExampleCard",
    "VideoCard",
    "Sponsors",
    "InstallWizard",
    "NpxSkillCta",
    "Example",
)
_DROP_BLOCK_RE = _block_re("(?:" + "|".join(_DROP_BLOCK_NAMES) + ")")

# Self-closing / single-line MDC blocks (``::Foo`` with no body and ``::`` close
# on the next line, plus the bare ``::`` ender for empty blocks).
_DROP_SELF_RE = re.compile(
    r"^::(?:" + "|".join(_DROP_BLOCK_NAMES) + r")(?:\{[^}]*\})?\s*\n::\s*$",
    re.MULTILINE,
)

# Pedagogy / content blocks — unwrap (drop the wrapper, keep inside).
_UNWRAP_BLOCK_NAMES = (
    "Callout",
    "callout",
    "ReferenceTable",
)
_UNWRAP_BLOCK_RE = _block_re("(?:" + "|".join(_UNWRAP_BLOCK_NAMES) + ")")

# ``::api-entry{name="..." type="..."}`` blocks — unwrap and keep the body
# so the API description survives.
_API_ENTRY_BLOCK_RE = re.compile(
    r"^::api-entry\{[^}]*\}\s*\n(.*?)^::\s*$",
    re.DOTALL | re.MULTILINE,
)

# ``::FrameworkOnly{framework="react"} ... ::`` — drop entirely.
_FRAMEWORK_REACT_BLOCK_RE = re.compile(
    r"^::FrameworkOnly\{\s*framework=\"react\"\s*\}\s*\n.*?^::\s*$",
    re.DOTALL | re.MULTILINE,
)
# ``::FrameworkOnly{framework="vue"} ... ::`` — unwrap.
_FRAMEWORK_VUE_BLOCK_RE = re.compile(
    r"^::FrameworkOnly\{\s*framework=\"vue\"\s*\}\s*\n(.*?)^::\s*$",
    re.DOTALL | re.MULTILINE,
)

# ``:FrameworkText{vue="..." react="..."}`` — keep vue text only.
_FRAMEWORK_TEXT_RE = re.compile(
    r":FrameworkText\{\s*vue=\"([^\"]*)\"\s*react=\"[^\"]*\"\s*\}",
)
_FRAMEWORK_TEXT_REACT_FIRST_RE = re.compile(
    r":FrameworkText\{\s*react=\"[^\"]*\"\s*vue=\"([^\"]*)\"\s*\}",
)

# Inline standalone shortcodes ``:Component`` or ``:Component{...}``.
_INLINE_DROP_NAMES = (
    "InputPageHero",
    "FormKitInputDiagrams",
    "CurrentTime",
    "Sponsors",
    "LinkDiscord",
    "LinkGithub",
    "LinkLocaleBuilder",
    "LinkStackOverflow",
    "InputChecklist",
)
_INLINE_DROP_RE = re.compile(
    r":(?:" + "|".join(_INLINE_DROP_NAMES) + r")(?:\{[^}]*\})?",
)

# Marketing / nav HTML wrappers (block + self-closing).
_HTML_DROP_NAMES = (
    "Sponsors",
    "LinkDiscord",
    "LinkGithub",
    "LinkLocaleBuilder",
    "LinkStackOverflow",
    "ExampleCardGrid",
    "InputChecklist",
)
_HTML_BLOCK_RE = re.compile(
    r"<(?:"
    + "|".join(_HTML_DROP_NAMES)
    + r")\b[^>]*>.*?</(?:"
    + "|".join(_HTML_DROP_NAMES)
    + r")>",
    re.DOTALL,
)
_HTML_SELF_RE = re.compile(
    r"^\s*<(?:" + "|".join(_HTML_DROP_NAMES) + r")\b[^>]*/?>\s*$",
    re.MULTILINE,
)


class FormKitAdapter:
    """Source adapter for FormKit documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed — docs-content is pure markdown."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all numbered-section markdown files, excluding auxiliary
        folders, hidden directories (``.dmux-hooks``, ``.claude``, etc.),
        and root meta pages."""
        files: list[Path] = []
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            parts = rel.parts

            # Skip hidden directories anywhere in the path.
            if any(p.startswith(".") for p in parts[:-1]):
                continue
            if parts[0] in _EXCLUDED_DIRS:
                continue
            if len(parts) == 1 and parts[0] in _EXCLUDED_ROOT_FILES:
                continue

            files.append(md_file)
        return files

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Derive sort keys from the numeric prefixes on folders + files.

        ``1.getting-started/2.installation.md`` → ``01_00_002``.
        Files without numeric prefixes (e.g. ``3.inputs/text.md``) get a
        999 fallback, which keeps them after numbered siblings but still
        ordered alphabetically by the standard fallback path.
        """
        result: dict[str, str] = {}
        docs_path = repo_root  # docs-content has no extra subpath

        for f in self.discover_files(docs_path):
            rel = f.relative_to(docs_path)
            parts = rel.parts

            section_idx = _SECTION_INDEX.get(parts[0], 99)

            # File index from numeric prefix on the leaf filename.
            leaf = parts[-1]
            m = _NUMERIC_PREFIX_RE.match(leaf)
            file_idx = int(m.group(1)) if m else 999

            # Strip extension + numeric prefixes for the keymap path.
            page_path = self._normalize_page_path(rel)
            result[page_path] = f"{section_idx:02d}_00_{file_idx:03d}"

        return result

    @staticmethod
    def _normalize_page_path(rel: Path) -> str:
        """Strip the ``.md`` extension; keep the numeric folder prefixes
        (``1.getting-started``) since downstream lookups match against
        the on-disk path the ingestion stores."""
        return str(rel).removesuffix(".md")

    def clean_content(self, raw: str) -> str:
        """Strip frontmatter, MDC promo/nav blocks, and resolve framework
        directives in favor of Vue."""
        result = raw

        # 1. YAML frontmatter.
        result = _FRONTMATTER_RE.sub("", result, count=1)

        # 2. React-only framework blocks before everything else (they may
        #    contain other MDC blocks that would otherwise survive).
        result = _FRAMEWORK_REACT_BLOCK_RE.sub("", result)
        # Vue-only framework blocks: unwrap.
        result = _FRAMEWORK_VUE_BLOCK_RE.sub(lambda m: m.group(1), result)

        # 3. Promo / nav blocks (drop entirely).
        result = _DROP_BLOCK_RE.sub("", result)
        result = _DROP_SELF_RE.sub("", result)

        # 4. Pedagogy / reference table blocks: unwrap.
        result = _UNWRAP_BLOCK_RE.sub(lambda m: m.group(1), result)

        # 5. ``::api-entry{...}`` blocks: unwrap and prepend a heading-style
        #    line so the entry's name remains a structural anchor for chunking.
        result = _API_ENTRY_BLOCK_RE.sub(lambda m: m.group(1).rstrip() + "\n", result)

        # 6. ``:FrameworkText{vue="..." react="..."}`` — replace with vue text.
        result = _FRAMEWORK_TEXT_RE.sub(lambda m: m.group(1), result)
        result = _FRAMEWORK_TEXT_REACT_FIRST_RE.sub(lambda m: m.group(1), result)

        # 7. Inline shortcodes (``:Hero``, ``:CurrentTime``, etc.).
        result = _INLINE_DROP_RE.sub("", result)

        # 8. HTML promo/nav wrappers.
        result = _HTML_BLOCK_RE.sub("", result)
        result = _HTML_SELF_RE.sub("", result)

        return result

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return FormKitEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return FormKitEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        # essentials → api-reference is the canonical concept-to-API jump.
        # inputs → essentials is the input-type to forms-concept jump.
        return [
            {"2.essentials", "6.api-reference"},
            {"3.inputs", "2.essentials"},
            {"5.guides", "6.api-reference"},
        ]
