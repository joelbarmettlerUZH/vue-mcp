"""VeeValidate-specific entity extractor.

Scans VeeValidate documentation to extract its form-validation surface:
the ``Form`` / ``Field`` / ``FieldArray`` / ``ErrorMessage`` components,
the composition-API helpers (``useForm``, ``useField``, ``useFieldArray``,
plus the granular ``useIsField*`` / ``useIsForm*`` / ``useSet*`` selectors),
the ``defineRule`` / ``configure`` global helpers, and the schema-validator
ecosystem (yup, zod, valibot, joi).
"""

import re
from pathlib import Path

from markdown_it import MarkdownIt

from vue_docs_core.models.entity import ApiEntity, EntityType

# Known VeeValidate APIs with their types. Sourced from
# packages/vee-validate/src/index.ts plus the documented integrations.
_KNOWN_APIS: dict[str, EntityType] = {
    # Composition API — primary
    "useField": EntityType.COMPOSABLE,
    "useForm": EntityType.COMPOSABLE,
    "useFieldArray": EntityType.COMPOSABLE,
    "useFormContext": EntityType.COMPOSABLE,
    # Composition API — granular field selectors
    "useFieldValue": EntityType.COMPOSABLE,
    "useFieldError": EntityType.COMPOSABLE,
    "useIsFieldDirty": EntityType.COMPOSABLE,
    "useIsFieldTouched": EntityType.COMPOSABLE,
    "useIsFieldValid": EntityType.COMPOSABLE,
    "useValidateField": EntityType.COMPOSABLE,
    # Composition API — granular form selectors
    "useFormValues": EntityType.COMPOSABLE,
    "useFormErrors": EntityType.COMPOSABLE,
    "useIsFormDirty": EntityType.COMPOSABLE,
    "useIsFormTouched": EntityType.COMPOSABLE,
    "useIsFormValid": EntityType.COMPOSABLE,
    "useIsSubmitting": EntityType.COMPOSABLE,
    "useIsValidating": EntityType.COMPOSABLE,
    "useValidateForm": EntityType.COMPOSABLE,
    "useSubmitCount": EntityType.COMPOSABLE,
    "useSubmitForm": EntityType.COMPOSABLE,
    "useResetForm": EntityType.COMPOSABLE,
    # Composition API — programmatic setters
    "useSetFieldError": EntityType.COMPOSABLE,
    "useSetFieldTouched": EntityType.COMPOSABLE,
    "useSetFieldValue": EntityType.COMPOSABLE,
    "useSetFormErrors": EntityType.COMPOSABLE,
    "useSetFormTouched": EntityType.COMPOSABLE,
    "useSetFormValues": EntityType.COMPOSABLE,
    # Components (renderless / scoped-slots)
    "Form": EntityType.COMPONENT,
    "Field": EntityType.COMPONENT,
    "FieldArray": EntityType.COMPONENT,
    "ErrorMessage": EntityType.COMPONENT,
    # Global / configuration
    "defineRule": EntityType.GLOBAL_API,
    "configure": EntityType.GLOBAL_API,
    "getConfig": EntityType.GLOBAL_API,
    "validate": EntityType.GLOBAL_API,
    "validateObject": EntityType.GLOBAL_API,
    "normalizeRules": EntityType.GLOBAL_API,
    # Schema integrations (the option keys passed to useForm/Form)
    "validationSchema": EntityType.OTHER,
    "toTypedSchema": EntityType.GLOBAL_API,
    # Form/Field option-bag types worth surfacing in api_lookup
    "FormOptions": EntityType.OTHER,
    "FieldOptions": EntityType.OTHER,
    "FormSlotProps": EntityType.OTHER,
    "FieldSlotProps": EntityType.OTHER,
    "RuleExpression": EntityType.OTHER,
    "FieldBindingObject": EntityType.OTHER,
    "ComponentFieldBindingObject": EntityType.OTHER,
    # Sibling packages (used as values: rules registry, i18n, nuxt module)
    "all": EntityType.GLOBAL_API,  # @vee-validate/rules — defineRule(...all)
    "@vee-validate/rules": EntityType.OTHER,
    "@vee-validate/i18n": EntityType.OTHER,
    "@vee-validate/zod": EntityType.OTHER,
    "@vee-validate/yup": EntityType.OTHER,
    "@vee-validate/valibot": EntityType.OTHER,
    "@vee-validate/joi": EntityType.OTHER,
    "@vee-validate/nuxt": EntityType.OTHER,
}

_SLUG_RE = re.compile(r"\{#[\w-]+\}\s*$")
_BACKTICK_RE = re.compile(r"^`(.+)`$")
_TRAILING_PARENS_RE = re.compile(r"\(\)$")


class VeeValidateEntityExtractor:
    """Entity extractor for VeeValidate documentation."""

    def build_dictionary(self, docs_path: Path) -> dict[str, ApiEntity]:
        """Build entity dictionary from VeeValidate docs.

        Combines the curated seed list with H2/H3 heading scans across the
        ``api/``, ``guide/``, ``tutorials/``, and ``examples/`` folders.
        """
        dictionary: dict[str, ApiEntity] = {}

        for name, entity_type in _KNOWN_APIS.items():
            dictionary[name] = ApiEntity(
                name=name,
                source="vee-validate",
                entity_type=entity_type,
            )

        for md_file in sorted(_iter_doc_files(docs_path)):
            self._scan_headings(md_file, docs_path, dictionary)

        return dictionary

    def _scan_headings(
        self, md_file: Path, docs_path: Path, dictionary: dict[str, ApiEntity]
    ) -> None:
        """Extract entities from H2/H3 headings in a markdown/MDX file."""
        md = MarkdownIt()
        raw = md_file.read_text(encoding="utf-8")
        tokens = md.parse(raw)
        rel_path = str(md_file.relative_to(docs_path))

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open" and tok.tag in ("h2", "h3") and i + 1 < len(tokens):
                inline = tokens[i + 1]
                heading_text = inline.content if inline.type == "inline" else ""
                name = self._clean_heading(heading_text)
                if name and name not in dictionary:
                    dictionary[name] = ApiEntity(
                        name=name,
                        source="vee-validate",
                        entity_type=self._classify(name),
                        page_path=rel_path,
                        section=heading_text.strip(),
                    )
            i += 1

    def _clean_heading(self, heading_text: str) -> str | None:
        text = _SLUG_RE.sub("", heading_text).strip()
        if not text:
            return None
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
        if name.startswith("define") or name.startswith("validate"):
            return EntityType.GLOBAL_API
        if name and name[0].isupper():
            return EntityType.COMPONENT
        return EntityType.OTHER

    def get_import_patterns(self) -> list[re.Pattern]:
        """Return import patterns for VeeValidate and its sub-packages."""
        return [
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]vee-validate['\"]"),
            re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]@vee-validate/[\w-]+['\"]"),
        ]


def _iter_doc_files(docs_path: Path):
    """Yield all .mdx files (and any stray .md files) under ``docs_path``."""
    seen: set[Path] = set()
    for ext in ("*.mdx", "*.md"):
        for p in docs_path.rglob(ext):
            if p not in seen:
                seen.add(p)
                yield p
