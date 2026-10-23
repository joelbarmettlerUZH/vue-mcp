"""MCP prompt templates — framework-parameterised workflows for the Vue ecosystem."""

from typing import Annotated

from fastmcp.prompts import Message, PromptResult
from pydantic import Field

from vue_docs_core.data.sources import SourceDefinition
from vue_docs_server.tools.common import framework_param, tool_ref


def make_debug_prompt(sources: list[SourceDefinition]):
    """Create the framework-parameterised debug prompt function."""
    Framework = framework_param(sources)
    display_names = {s.name: s.display_name for s in sources}

    def debug_issue(
        framework: Framework,
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
        """Structured prompt for debugging an issue using the framework's documentation."""
        display = display_names[framework]
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
                    f"is involved, then search with {tool_ref('docs_search', framework)}\n"
                    f"2. **Check API details** — Look up the specific APIs using "
                    f"{tool_ref('api_lookup', framework)} to find known gotchas or constraints\n"
                    f"3. **Explore related patterns** — Use "
                    f"{tool_ref('get_related', framework)} to "
                    f"discover if alternative approaches exist\n"
                    f"4. **Explain and fix** — Provide:\n"
                    f"   - **Root cause** with a reference to the relevant doc section\n"
                    f"   - **Fix** with corrected code\n"
                    f"   - **Prevention** tip to avoid this in the future",
                ),
            ],
        )

    return debug_issue


def make_compare_prompt(sources: list[SourceDefinition]):
    """Create the framework-parameterised comparison prompt function."""
    Framework = framework_param(sources)
    display_names = {s.name: s.display_name for s in sources}

    def compare_apis(
        framework: Framework,
        items: Annotated[
            str,
            Field(description="Comma-separated list of APIs or patterns to compare."),
        ],
    ) -> PromptResult:
        """Compare two or more APIs or patterns using the framework's documentation."""
        display = display_names[framework]
        api_list = [item.strip() for item in items.split(",") if item.strip()]
        formatted = ", ".join(f"`{a}`" for a in api_list)

        lookup_steps = "\n".join(
            f'   - {tool_ref("api_lookup", framework)} → `"{a}"`' for a in api_list
        )

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
                    f"2. **Search for usage context** — {tool_ref('docs_search', framework)} "
                    f"for each API\n"
                    f"3. **Find connections** — {tool_ref('get_related', framework)} to "
                    f"discover shared patterns\n\n"
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

    return compare_apis


def make_migrate_prompt(sources: list[SourceDefinition]):
    """Create the framework-parameterised migration prompt function."""
    Framework = framework_param(sources)
    display_names = {s.name: s.display_name for s in sources}

    def migrate_pattern(
        framework: Framework,
        from_pattern: Annotated[
            str,
            Field(description="The current pattern or API being migrated from."),
        ],
        to_pattern: Annotated[
            str,
            Field(description="The target pattern or API to migrate to."),
        ],
    ) -> PromptResult:
        """Guide for migrating between patterns using the framework's documentation."""
        display = display_names[framework]
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
                    f"1. **Understand the source** — {tool_ref('docs_search', framework)} for "
                    f'`"{from_pattern}"`\n'
                    f"2. **Understand the target** — {tool_ref('docs_search', framework)} for "
                    f'`"{to_pattern}"`\n'
                    f"3. **Look up relevant APIs** — {tool_ref('api_lookup', framework)} for "
                    f"key APIs in both patterns\n"
                    f"4. **Find related concepts** — {tool_ref('get_related', framework)} to "
                    f"discover the full migration surface\n\n"
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

    return migrate_pattern
