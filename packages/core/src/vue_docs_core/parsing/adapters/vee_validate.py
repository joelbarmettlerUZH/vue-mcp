"""Source adapter for VeeValidate documentation.

VeeValidate's docs are an Astro site, not VitePress or Nuxt Content. Pages
are ``.mdx`` files under ``docs/src/pages/``. The sidebar is generated at
build time from frontmatter (``order: N``) plus the on-disk folder
hierarchy (``HomeLayout.astro`` / ``PageLayout.astro``):

    1. resources
    2. tutorials
    3. guide          (with guide/components and guide/composition-api as nested subgroups)
    4. examples
    5. integrations
    6. api

The adapter mirrors that ordering deterministically by reading frontmatter
``order`` and using a hard-coded section index.

Content cleanup handles MDX quirks:
  - ``import X from '...'`` JS-style import lines outside code fences
  - Pedagogy components: ``<DocTip>``, ``<DocBadge>``, ``<CodeTitle>``,
    ``<FeatureCard>`` — wrapper tags stripped, inner prose preserved
  - Self-closing demo components (``<DynamicForm />``, ``<FormWizard />``,
    ``<FormStep />``, ``<FieldEntry />``, ``<FieldArrayEntry />``,
    ``<FieldState />``, ``<FormState />``, ``<FormMeta />``,
    ``<FormValidationResult />``, ``<CustomInput />``, ``<CustomTextField />``)
    — rendered as live demos in the docs site, dropped here
  - VeeValidate's own API components (``<Form>``, ``<Field>``, ``<FieldArray>``,
    ``<ErrorMessage>``) are intentionally preserved, since their presence
    in code samples carries API signal.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity
from vue_docs_core.parsing.extractors.vee_validate import VeeValidateEntityExtractor

# Section ordering, derived from HomeLayout.astro / PageLayout.astro.
_SECTION_ORDER: dict[str, int] = {
    "resources": 0,
    "tutorials": 1,
    "guide": 2,
    "examples": 3,
    "integrations": 4,
    "api": 5,
}
# Subgroup ordering inside "guide".
_GUIDE_SUBGROUP_ORDER: dict[str, int] = {
    "": 0,  # top-level guide pages
    "components": 1,
    "composition-api": 2,
}

# Files and directories under docs/src/pages to skip.
_EXCLUDED_ROOT_FILES = frozenset({"index.mdx", "index.md", "404.mdx", "404.md"})

# Pedagogy components — wrapper-only, KEEP inner content.
_PEDAGOGY_COMPONENTS = ("DocTip", "DocBadge", "CodeTitle", "FeatureCard")
_PED_NAMES = "|".join(_PEDAGOGY_COMPONENTS)
# <DocTip ...>...</DocTip> — drop the tags, keep what's between.
_PED_BLOCK_RE = re.compile(rf"<(?:{_PED_NAMES})\b[^>]*>(.*?)</(?:{_PED_NAMES})>", re.DOTALL)
# Self-closing pedagogy or with no inner content — drop entirely.
_PED_SELF_RE = re.compile(rf"<(?:{_PED_NAMES})\b[^>]*/>")

# Demo components — fully drop (they render Astro live demos, no useful prose).
_DEMO_COMPONENTS = (
    "DynamicForm",
    "FormWizard",
    "FormStep",
    "FieldEntry",
    "FieldArrayEntry",
    "FieldState",
    "FormState",
    "FormMeta",
    "FormValidationResult",
    "CustomInput",
    "CustomTextField",
    "HomeLayout",
)
_DEMO_NAMES = "|".join(_DEMO_COMPONENTS)
_DEMO_BLOCK_RE = re.compile(rf"<(?:{_DEMO_NAMES})\b[^>]*>.*?</(?:{_DEMO_NAMES})>", re.DOTALL)
_DEMO_SELF_RE = re.compile(rf"^\s*<(?:{_DEMO_NAMES})\b[^>]*/>\s*$", re.MULTILINE)

# MDX import line: ``import X from '...';`` or ``import * as X from '...';``
_MDX_IMPORT_RE = re.compile(r"^\s*import\s+[^\n;]+from\s*['\"][^'\"]+['\"]\s*;?\s*$")

# Frontmatter delimiter (Astro / MDX uses standard YAML between --- markers).
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Match the ``order: N`` frontmatter field directly. Values are always
# small integers in VeeValidate's docs, so a regex avoids a YAML dep.
_ORDER_LINE_RE = re.compile(r"^order:\s*(\d+)\s*$", re.MULTILINE)


class VeeValidateAdapter:
    """Source adapter for VeeValidate documentation."""

    def post_clone(self, repo_root: Path) -> None:
        """No post-clone steps needed for the Astro docs."""

    def discover_files(self, docs_path: Path) -> list[Path]:
        """Find all ``.mdx`` and ``.md`` pages under ``src/pages``,
        excluding the homepage and 404."""
        files: list[Path] = []
        for ext in ("*.mdx", "*.md"):
            for f in docs_path.rglob(ext):
                rel = f.relative_to(docs_path)
                if len(rel.parts) == 1 and rel.parts[0] in _EXCLUDED_ROOT_FILES:
                    continue
                files.append(f)
        return sorted(set(files))

    def parse_sort_keys(self, repo_root: Path) -> dict[str, str]:
        """Derive sort keys from frontmatter ``order`` plus the section
        hierarchy. Returns ``{relative_path_without_ext: sort_key}``.
        """
        docs_path = repo_root / "docs" / "src" / "pages"
        if not docs_path.exists():
            return {}

        result: dict[str, str] = {}
        for f in self.discover_files(docs_path):
            rel = f.relative_to(docs_path)
            parts = rel.parts

            # Resolve section + subgroup
            if len(parts) == 1:
                # docs/src/pages/resources.mdx → section "resources", subgroup ""
                section = parts[0].rsplit(".", 1)[0]
                subgroup = ""
            else:
                section = parts[0]
                subgroup = parts[1] if len(parts) > 2 else ""
                if subgroup and "." in subgroup:
                    # parts[1] is a file (e.g. "guide/overview.mdx") → no subgroup
                    subgroup = ""

            section_idx = _SECTION_ORDER.get(section, 99)
            if section == "guide":
                group_idx = _GUIDE_SUBGROUP_ORDER.get(subgroup, 99)
            else:
                group_idx = 0

            order = _read_frontmatter_order(f)

            # Strip extension for the keymap (matches downstream lookups).
            page_path = str(rel).removesuffix(".mdx").removesuffix(".md")
            result[page_path] = f"{section_idx:02d}_{group_idx:02d}_{order:03d}"

        return result

    def clean_content(self, raw: str) -> str:
        """Strip MDX imports, pedagogy components, and demo components."""
        # 1. Remove the YAML frontmatter — markdown-it doesn't render it
        #    natively but leaving it would chunk as a raw paragraph.
        result = _FRONTMATTER_RE.sub("", raw, count=1)

        # 2. Drop self-closing and block-form demo components (no useful prose).
        result = _DEMO_BLOCK_RE.sub("", result)
        result = _DEMO_SELF_RE.sub("", result)

        # 3. Pedagogy block components: keep inner content, drop the tags.
        result = _PED_BLOCK_RE.sub(lambda m: m.group(1), result)
        # 4. Pedagogy self-closing: drop entirely (no inner text).
        result = _PED_SELF_RE.sub("", result)

        # 5. MDX imports outside code fences. Fence-aware to avoid stripping
        #    actual code-example imports.
        result = self._strip_mdx_imports(result)

        return result

    @staticmethod
    def _strip_mdx_imports(text: str) -> str:
        lines = text.split("\n")
        output: list[str] = []
        in_fence = False
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                output.append(line)
                continue
            if not in_fence and _MDX_IMPORT_RE.match(line):
                continue
            output.append(line)
        return "\n".join(output)

    def build_entity_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        return VeeValidateEntityExtractor().build_dictionary(docs_path)

    def get_import_patterns(self) -> list[re.Pattern]:
        return VeeValidateEntityExtractor().get_import_patterns()

    @property
    def high_value_folder_pairs(self) -> list[set[str]]:
        # Guide-to-API is the canonical concept-to-reference jump.
        return [{"guide", "api"}, {"tutorials", "api"}, {"guide", "examples"}]


def _read_frontmatter_order(file_path: Path) -> int:
    """Return the ``order`` frontmatter value, or 999 if missing."""
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return 999
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return 999
    om = _ORDER_LINE_RE.search(m.group(1))
    return int(om.group(1)) if om else 999
