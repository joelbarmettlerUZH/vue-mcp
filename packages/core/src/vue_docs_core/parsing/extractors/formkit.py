"""FormKit-specific entity extractor.

Scans FormKit documentation to extract its surface in three layers:

1. **API entries.** The api-reference folder uses MDC blocks like
   ``::api-entry{name="createInput()" type="function"} ... ::`` — one per
   public API. We parse the ``name=`` attribute directly so entries always
   keep their canonical type from the source.
2. **Input types.** Each markdown file in ``3.inputs/`` documents one input
   (text, select, checkbox, …) — the filename becomes the entity name.
3. **Top-level primitives.** ``<FormKit>``, ``<FormKitSchema>``,
   ``<FormKitMessages>``, ``createInput``, ``defineFormKitConfig`` and the
   handful of names that don't appear as ``::api-entry`` blocks.
"""

import re
from pathlib import Path

from vue_docs_core.models.entity import ApiEntity, EntityType

# Top-level primitives the docs reference frequently. The api-reference scan
# below catches the rest — this seed only needs the ones outside ``::api-entry``
# blocks (component names, framework defaults, well-known plugin packages).
_KNOWN_APIS: dict[str, EntityType] = {
    # Components (used inline + in code samples)
    "FormKit": EntityType.COMPONENT,
    "FormKitSchema": EntityType.COMPONENT,
    "FormKitMessages": EntityType.COMPONENT,
    "FormKitIcon": EntityType.COMPONENT,
    "FormKitSummary": EntityType.COMPONENT,
    # Top-level helpers / config
    "defineFormKitConfig": EntityType.GLOBAL_API,
    "plugin": EntityType.OTHER,
    "node": EntityType.OTHER,
    # Plugin packages (npm names, used as values in plugin lists)
    "@formkit/auto-animate": EntityType.OTHER,
    "@formkit/zod": EntityType.OTHER,
    "@formkit/auto-height-textarea": EntityType.OTHER,
    "@formkit/floating-labels": EntityType.OTHER,
    "@formkit/local-storage": EntityType.OTHER,
    "@formkit/multi-step": EntityType.OTHER,
    "@formkit/barcode": EntityType.OTHER,
    "@formkit/inertia": EntityType.OTHER,
}

# ``::api-entry{name="foo()" type="function"}`` — extract name+type from
# the attribute block. ``name`` always present; ``type`` may be missing
# in older docs but the canonical set has it.
_API_ENTRY_RE = re.compile(
    r'::api-entry\{\s*name="([^"]+)"\s*(?:type="([^"]*)")?[^}]*\}',
)

# Map FormKit's ``type=`` strings to our EntityType taxonomy.
_TYPE_MAP: dict[str, EntityType] = {
    "function": EntityType.GLOBAL_API,
    "interface": EntityType.OTHER,
    "type": EntityType.OTHER,
    "property": EntityType.INSTANCE_PROPERTY,
    "variable": EntityType.OTHER,
    "class": EntityType.OTHER,
}

_HEADING_RE = re.compile(r"^##?#?\s+(.+?)\s*$", re.MULTILINE)
_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_ANGLE_BRACKETS_RE = re.compile(r"^`?<(.+?)\s*/?>`?$")


class FormKitEntityExtractor:
    """Entity extractor for FormKit documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary in three passes.

        1. Seed from the curated ``_KNOWN_APIS`` table.
        2. Parse ``::api-entry{name="..." type="..."}`` blocks from
           ``6.api-reference/*.md`` — each yields a typed entity tied to
           the package page.
        3. Walk ``3.inputs/*.md`` and ``4.plugins/*.md`` so input types
           and plugins each become entities pointing to their own page.
        """
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="formkit",
                entity_type=entity_type,
            )

        # Pass 2: api-reference packages.
        api_dir = docs_path / "6.api-reference"
        if api_dir.exists():
            for md_file in sorted(api_dir.glob("*.md")):
                rel_path = str(md_file.relative_to(docs_path))
                raw = md_file.read_text(encoding="utf-8")
                for m in _API_ENTRY_RE.finditer(raw):
                    name_raw = m.group(1)
                    type_raw = (m.group(2) or "").strip()
                    name = _TRAILING_PARENS_RE.sub("", name_raw).strip()
                    if not name or name in dictionary:
                        continue
                    entity_type = _TYPE_MAP.get(type_raw, EntityType.OTHER)
                    if name.startswith("use") and name[3:4].isupper():
                        entity_type = EntityType.COMPOSABLE
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="formkit",
                        entity_type=entity_type,
                        page_path=rel_path,
                        section=name,
                    )

        # Pass 3: input types — one per file.
        inputs_dir = docs_path / "3.inputs"
        if inputs_dir.exists():
            for md_file in sorted(inputs_dir.glob("*.md")):
                input_name = md_file.stem
                if input_name in dictionary:
                    continue
                rel_path = str(md_file.relative_to(docs_path))
                dictionary[input_name] = ApiEntity(
                    name=input_name,
                    source="formkit",
                    entity_type=EntityType.OTHER,
                    page_path=rel_path,
                    section=f"{input_name} input",
                )

        # Pass 4: plugins — one per file.
        plugins_dir = docs_path / "4.plugins"
        if plugins_dir.exists():
            for md_file in sorted(plugins_dir.glob("*.md")):
                plugin_name = md_file.stem
                if plugin_name in dictionary:
                    continue
                rel_path = str(md_file.relative_to(docs_path))
                dictionary[plugin_name] = ApiEntity(
                    name=plugin_name,
                    source="formkit",
                    entity_type=EntityType.OTHER,
                    page_path=rel_path,
                    section=f"{plugin_name} plugin",
                )

        return dictionary

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for FormKit and its sub-packages."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@formkit/vue['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@formkit/[\w-]+['\"]"),
        ]
