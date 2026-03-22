"""MCP prompt templates — per-source factories for Vue ecosystem workflows."""

from typing import Annotated

from fastmcp.prompts import Message, PromptResult
from pydantic import Field

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.tools.search import _tool_prefix


def make_debug_prompt(source_def: SourceDefinition):
    """Create a source-specific debug prompt function."""
    display = source_def.display_name
    prefix = _tool_prefix(source_def.name)

    def debug_issue(
        symptom: Annotated[
            str, Field(description="Description of the unexpected behavior or error message.")
        ],
        code_snippet: Annotated[
            str,
            Field(
                default="",
                description="Relevant code snippet where the issue occurs (optional).",
            ),
        ] = "",
    ) -> PromptResult:
        code_block = ""
        if code_snippet:
            code_block = f"\n\n```\n{code_snippet}\n```"

        return PromptResult(
            messages=[
                Message(
                    f"I'll help debug this {display} issue step-by-step using the "
                    f"official documentation. I'll identify the root cause, find "
                    f"relevant docs, and provide a fix with citations.",
                    role="assistant",
                ),
                Message(
                    f"## Issue\n\n"
                    f"{symptom}{code_block}\n\n"
                    f"## Debugging workflow\n\n"
                    f"Please follow these steps:\n\n"
                    f"1. **Identify the concept** — Determine which {display} concept "
                    f"is involved, then search with `{prefix}_docs_search`\n"
                    f"2. **Check API details** — Look up the specific APIs using "
                    f"`{prefix}_api_lookup` to find known gotchas or constraints\n"
                    f"3. **Explore related patterns** — Use `{prefix}_get_related` to "
                    f"discover if alternative approaches exist\n"
                    f"4. **Explain and fix** — Provide:\n"
                    f"   - **Root cause** with a reference to the relevant doc section\n"
                    f"   - **Fix** with corrected code\n"
                    f"   - **Prevention** tip to avoid this in the future",
                ),
            ],
        )

    debug_issue.__name__ = f"debug_{prefix}_issue"
    debug_issue.__doc__ = (
        f"Structured prompt for debugging a {display} issue using the documentation."
    )
    return debug_issue


def make_compare_prompt(source_def: SourceDefinition):
    """Create a source-specific comparison prompt function."""
    display = source_def.display_name
    prefix = _tool_prefix(source_def.name)

    def compare_apis(
        items: Annotated[
            str,
            Field(description=f"Comma-separated list of {display} APIs or patterns to compare."),
        ],
    ) -> PromptResult:
        api_list = [item.strip() for item in items.split(",") if item.strip()]
        formatted = ", ".join(f"`{a}`" for a in api_list)

        lookup_steps = "\n".join(f'   - `{prefix}_api_lookup` → `"{a}"`' for a in api_list)

        return PromptResult(
            messages=[
                Message(
                    f"I'll compare {formatted} using the official {display} documentation "
                    f"and present a structured comparison.",
                    role="assistant",
                ),
                Message(
                    f"## Compare: {formatted}\n\n"
                    f"### Research steps\n\n"
                    f"1. **Look up each API:**\n{lookup_steps}\n"
                    f"2. **Search for usage context** — `{prefix}_docs_search` for each API\n"
                    f"3. **Find connections** — `{prefix}_get_related` to discover shared "
                    f"patterns\n\n"
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

    compare_apis.__name__ = f"compare_{prefix}_apis"
    compare_apis.__doc__ = (
        f"Compare two or more {display} APIs or patterns using the official documentation."
    )
    return compare_apis


def make_migrate_prompt(source_def: SourceDefinition):
    """Create a source-specific migration prompt function."""
    display = source_def.display_name
    prefix = _tool_prefix(source_def.name)

    def migrate_pattern(
        from_pattern: Annotated[
            str,
            Field(description=f"The current {display} pattern or API being migrated from."),
        ],
        to_pattern: Annotated[
            str,
            Field(description=f"The target {display} pattern or API to migrate to."),
        ],
    ) -> PromptResult:
        return PromptResult(
            messages=[
                Message(
                    f"I'll create a comprehensive migration guide from "
                    f"**{from_pattern}** to **{to_pattern}** using the official "
                    f"{display} documentation.",
                    role="assistant",
                ),
                Message(
                    f"## Migrate: {from_pattern} → {to_pattern}\n\n"
                    f"### Research steps\n\n"
                    f"1. **Understand the source** — `{prefix}_docs_search` for "
                    f'`"{from_pattern}"`\n'
                    f"2. **Understand the target** — `{prefix}_docs_search` for "
                    f'`"{to_pattern}"`\n'
                    f"3. **Look up relevant APIs** — `{prefix}_api_lookup` for key APIs "
                    f"in both patterns\n"
                    f"4. **Find related concepts** — `{prefix}_get_related` to discover "
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

    migrate_pattern.__name__ = f"migrate_{prefix}_pattern"
    migrate_pattern.__doc__ = (
        f"Guide for migrating between {display} patterns using the official documentation."
    )
    return migrate_pattern
