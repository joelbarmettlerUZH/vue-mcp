"""MCP prompt templates for common Vue.js documentation workflows."""

from typing import Annotated

from fastmcp.prompts import Message, PromptResult
from pydantic import Field


def debug_vue_issue(
    symptom: Annotated[
        str, Field(description="Description of the unexpected behavior or error message.")
    ],
    code_snippet: Annotated[
        str,
        Field(default="", description="Relevant code snippet where the issue occurs (optional)."),
    ] = "",
) -> PromptResult:
    """Structured prompt for debugging a Vue.js issue using the documentation."""
    code_block = ""
    if code_snippet:
        code_block = f"\n\n```\n{code_snippet}\n```"

    return PromptResult(
        messages=[
            Message(
                "I'll help debug this Vue.js issue step-by-step using the "
                "official documentation. I'll identify the root cause, find "
                "relevant docs, and provide a fix with citations.",
                role="assistant",
            ),
            Message(
                f"## Issue\n\n"
                f"{symptom}{code_block}\n\n"
                f"## Debugging workflow\n\n"
                f"Please follow these steps:\n\n"
                f"1. **Identify the concept** — Determine which Vue.js concept "
                f"is involved, then search with `vue_docs_search`\n"
                f"2. **Check API details** — Look up the specific APIs using "
                f"`vue_api_lookup` to find known gotchas or constraints\n"
                f"3. **Explore related patterns** — Use `vue_get_related` to "
                f"discover if alternative approaches exist\n"
                f"4. **Explain and fix** — Provide:\n"
                f"   - **Root cause** with a reference to the relevant doc section\n"
                f"   - **Fix** with corrected code\n"
                f"   - **Prevention** tip to avoid this in the future",
            ),
        ],
    )


def compare_vue_apis(
    items: Annotated[
        str,
        Field(
            description="Comma-separated list of Vue APIs or patterns to compare. "
            "Examples: 'ref, reactive', 'computed, watch', 'v-if, v-show'."
        ),
    ],
) -> PromptResult:
    """Compare two or more Vue.js APIs or patterns using the official documentation."""
    api_list = [item.strip() for item in items.split(",") if item.strip()]
    formatted = ", ".join(f"`{a}`" for a in api_list)

    lookup_steps = "\n".join(f'   - `vue_api_lookup` → `"{a}"`' for a in api_list)

    return PromptResult(
        messages=[
            Message(
                f"I'll compare {formatted} using the official Vue.js documentation "
                f"and present a structured comparison.",
                role="assistant",
            ),
            Message(
                f"## Compare: {formatted}\n\n"
                f"### Research steps\n\n"
                f"1. **Look up each API:**\n{lookup_steps}\n"
                f"2. **Search for usage context** — `vue_docs_search` for each API\n"
                f"3. **Find connections** — `vue_get_related` to discover shared patterns\n\n"
                f"### Output format\n\n"
                f"Present the comparison as:\n\n"
                f"| Aspect | {' | '.join(f'`{a}`' for a in api_list)} |\n"
                f"|--------|{'|'.join('--------|' for _ in api_list)}\n"
                f"| Purpose | ... |\n"
                f"| Reactivity | ... |\n"
                f"| Performance | ... |\n"
                f"| Use when... | ... |\n\n"
                f"Then provide:\n"
                f"- **Key differences** with code examples from the docs\n"
                f"- **When to use which** — decision criteria\n"
                f"- **Common mistakes** when choosing between them",
            ),
        ],
    )


def migrate_vue_pattern(
    from_pattern: Annotated[
        str,
        Field(
            description="The current pattern or API being migrated from. "
            "Examples: 'Options API', 'Vue 2 mixins', 'event bus'."
        ),
    ],
    to_pattern: Annotated[
        str,
        Field(
            description="The target pattern or API to migrate to. "
            "Examples: 'Composition API', 'composables', 'provide/inject'."
        ),
    ],
) -> PromptResult:
    """Guide for migrating between Vue.js patterns using the official documentation."""
    return PromptResult(
        messages=[
            Message(
                f"I'll create a comprehensive migration guide from "
                f"**{from_pattern}** to **{to_pattern}** using the official "
                f"Vue.js documentation.",
                role="assistant",
            ),
            Message(
                f"## Migrate: {from_pattern} → {to_pattern}\n\n"
                f"### Research steps\n\n"
                f"1. **Understand the source** — `vue_docs_search` for "
                f'`"{from_pattern}"`\n'
                f"2. **Understand the target** — `vue_docs_search` for "
                f'`"{to_pattern}"`\n'
                f"3. **Look up relevant APIs** — `vue_api_lookup` for key APIs "
                f"in both patterns\n"
                f"4. **Find related concepts** — `vue_get_related` to discover "
                f"the full migration surface\n\n"
                f"### Output format\n\n"
                f"Structure the migration guide as:\n\n"
                f"1. **Why migrate** — Benefits of `{to_pattern}` over "
                f"`{from_pattern}`\n"
                f"2. **Concept mapping** — Table showing how each concept in "
                f"`{from_pattern}` maps to `{to_pattern}`:\n\n"
                f"   | {from_pattern} | {to_pattern} | Notes |\n"
                f"   |---|---|---|\n"
                f"   | ... | ... | ... |\n\n"
                f"3. **Step-by-step migration** — Concrete steps with before/after "
                f"code examples from the docs\n"
                f"4. **Gotchas** — Common pitfalls and how to avoid them",
            ),
        ],
    )
