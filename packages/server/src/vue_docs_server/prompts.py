"""MCP prompt templates for common Vue.js documentation workflows."""

from typing import Annotated

from pydantic import Field


def debug_vue_issue(
    symptom: Annotated[str, Field(
        description="Description of the unexpected behavior or error message."
    )],
    code_snippet: Annotated[str, Field(
        default="",
        description="Relevant code snippet where the issue occurs (optional)."
    )] = "",
) -> str:
    """Structured prompt for debugging a Vue.js issue using the documentation."""
    code_block = ""
    if code_snippet:
        code_block = f"\n\n**Code:**\n```\n{code_snippet}\n```"

    return (
        f"I need to debug a Vue.js issue.\n\n"
        f"**Symptom:** {symptom}{code_block}\n\n"
        f"Please help me diagnose this by:\n"
        f"1. Search the Vue.js documentation for the relevant concept "
        f"using `vue_docs_search`\n"
        f"2. Check if there are common gotchas documented for the APIs "
        f"involved using `vue_api_lookup`\n"
        f"3. Look for related patterns that might explain the behavior "
        f"using `vue_get_related`\n"
        f"4. Provide a clear explanation of why this happens and how to "
        f"fix it, citing specific documentation sections."
    )


def compare_vue_apis(
    items: Annotated[str, Field(
        description="Comma-separated list of Vue APIs or patterns to compare. "
                    "Examples: 'ref, reactive', 'computed, watch', 'v-if, v-show'."
    )],
) -> str:
    """Compare two or more Vue.js APIs or patterns using the official documentation."""
    api_list = [item.strip() for item in items.split(",") if item.strip()]
    formatted = ", ".join(f"`{a}`" for a in api_list)

    return (
        f"Please compare these Vue.js APIs/patterns: {formatted}\n\n"
        f"For each one:\n"
        f"1. Look up its documentation using `vue_api_lookup`\n"
        f"2. Search for usage details with `vue_docs_search`\n"
        f"3. Check related APIs with `vue_get_related`\n\n"
        f"Then provide a comparison covering:\n"
        f"- **Purpose**: What each one is for\n"
        f"- **Key differences**: When to use which\n"
        f"- **Performance**: Any performance implications\n"
        f"- **Common patterns**: Typical usage examples from the docs"
    )


def migrate_vue_pattern(
    from_pattern: Annotated[str, Field(
        description="The current pattern or API being migrated from. "
                    "Examples: 'Options API', 'Vue 2 mixins', 'event bus'."
    )],
    to_pattern: Annotated[str, Field(
        description="The target pattern or API to migrate to. "
                    "Examples: 'Composition API', 'composables', 'provide/inject'."
    )],
) -> str:
    """Guide for migrating between Vue.js patterns using the official documentation."""
    return (
        f"I need to migrate from **{from_pattern}** to **{to_pattern}** in Vue.js.\n\n"
        f"Please help by:\n"
        f"1. Search the Vue.js documentation for both patterns using "
        f"`vue_docs_search`\n"
        f"2. Look up relevant APIs for both approaches using `vue_api_lookup`\n"
        f"3. Find related concepts with `vue_get_related`\n\n"
        f"Then provide:\n"
        f"- **Why migrate**: Benefits of the new pattern\n"
        f"- **Key mappings**: How each concept in `{from_pattern}` maps to "
        f"`{to_pattern}`\n"
        f"- **Step-by-step**: Concrete migration steps with code examples "
        f"from the docs\n"
        f"- **Gotchas**: Common pitfalls during migration"
    )
