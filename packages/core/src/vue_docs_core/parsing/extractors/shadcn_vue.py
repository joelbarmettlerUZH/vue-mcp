"""shadcn-vue-specific entity extractor.

Scans shadcn-vue documentation to extract its surface in two layers:

1. **Components.** Each markdown file in ``components/`` documents one
   component. The filename (kebab-case) is the entity name, paired with
   the PascalCase rendering for code-sample matching (``button`` →
   ``Button``).
2. **Installation / framework integration entities** (Vite, Nuxt, Astro,
   Laravel) and form-library wrappers (``vee-validate``, ``tanstack-form``)
   pulled from their respective folder pages.

The CLI ``npx shadcn-vue@latest add ...`` command pattern is the primary
entry point — covered by synonyms.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity, EntityType

# Top-level primitives the docs reference frequently outside per-component pages.
_KNOWN_APIS: dict[str, EntityType] = {
    # Core CLI / packages
    "shadcn-vue": EntityType.OTHER,
    "components.json": EntityType.OTHER,
    # Underlying primitives library (shadcn-vue is a styled wrapper).
    "reka-ui": EntityType.OTHER,
    # Theming / config
    "tailwind": EntityType.OTHER,
    "cn": EntityType.GLOBAL_API,  # the classic class-name helper
    "useColorMode": EntityType.COMPOSABLE,
    # Form integrations (top-level pages live under forms/)
    "vee-validate": EntityType.OTHER,
    "tanstack-form": EntityType.OTHER,
    # Framework integrations
    "Vite": EntityType.OTHER,
    "Nuxt": EntityType.OTHER,
    "Astro": EntityType.OTHER,
    "Laravel": EntityType.OTHER,
}


def _kebab_to_pascal(name: str) -> str:
    """``alert-dialog`` → ``AlertDialog``."""
    return "".join(part.capitalize() for part in name.split("-"))


_HEADING_RE = re.compile(r"^##?#?\s+(.+?)\s*$", re.MULTILINE)
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")


class ShadcnVueEntityExtractor:
    """Entity extractor for shadcn-vue documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary in three passes.

        1. Seed from the curated ``_KNOWN_APIS`` table.
        2. Each ``components/*.md`` file becomes both a kebab-case entity
           (``alert-dialog``) and its PascalCase counterpart
           (``AlertDialog``) so code-sample matches surface the same page.
        3. Heading scan across all docs picks up additions.
        """
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="shadcn-vue",
                entity_type=entity_type,
            )

        # Pass 2: components.
        components_dir = docs_path / "components"
        if components_dir.exists():
            for md_file in sorted(components_dir.glob("*.md")):
                kebab = md_file.stem
                pascal = _kebab_to_pascal(kebab)
                rel_path = str(md_file.relative_to(docs_path))
                # Kebab form (matches the install command + URL).
                if kebab not in dictionary:
                    dictionary[kebab] = ApiEntity(
                        name=kebab,
                        source="shadcn-vue",
                        entity_type=EntityType.COMPONENT,
                        page_path=rel_path,
                        section=f"{pascal} component",
                    )
                # PascalCase form (matches code samples like ``<Button>``).
                if pascal not in dictionary:
                    dictionary[pascal] = ApiEntity(
                        name=pascal,
                        source="shadcn-vue",
                        entity_type=EntityType.COMPONENT,
                        page_path=rel_path,
                        section=f"{pascal} component",
                    )

        # Pass 3: heading scan for anything else.
        for md_file in sorted(docs_path.rglob("*.md")):
            rel = md_file.relative_to(docs_path)
            # Skip hidden files (Nuxt Content draft convention).
            if any(p.startswith(".") for p in rel.parts):
                continue
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(
        self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]
    ) -> None:
        """Grab H2/H3 headings as additional entity names."""
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError:
            return
        rel_path = str(md_file.relative_to(docs_path))
        for m in _HEADING_RE.finditer(raw):
            heading = m.group(1).strip()
            name = self._clean_heading(heading)
            if name and name not in dictionary:
                dictionary[name] = ApiEntity(
                    name=name,
                    source="shadcn-vue",
                    entity_type=self._classify(name),
                    page_path=rel_path,
                    section=heading,
                )

    def _clean_heading(self, heading: str) -> str | None:
        text = heading
        m = _BACKTICK_RE.match(text)
        if m:
            text = m.group(1)
        text = _TRAILING_PARENS_RE.sub("", text)
        if " " in text and "." not in text:
            return None
        return text or None

    def _classify(self, name: str) -> EntityType:
        if name in _KNOWN_APIS:
            return _KNOWN_APIS[name]
        if name.startswith("use") and name[3:4].isupper():
            return EntityType.COMPOSABLE
        if name.startswith(("define", "create")):
            return EntityType.GLOBAL_API
        if name and name[0].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Components are typically imported from a project-local
        ``@/components/ui/...`` alias (set up by the shadcn CLI). We also
        match ``reka-ui`` for the underlying primitives."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@/components/ui/[\w-]+['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]reka-ui['\"]"),
        ]
