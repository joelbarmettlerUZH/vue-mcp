"""Get-related tool — find related documentation for a topic, per-source or combined."""

import time
from typing import Annotated

from fastmcp import Context
from fastmcp.exceptions import ToolError
from pydantic import Field

from vue_docs_core.data.sources import SOURCE_REGISTRY, SourceDefinition
from vue_docs_server.startup import state
from vue_docs_server.tools.common import framework_param, tool_ref
from vue_docs_server.usage import log_tool_call


async def _do_get_related(
    topic: str,
    source: str | None = None,
    ctx: Context = None,
) -> str:
    """Shared get-related implementation. source=None uses combined matcher."""
    if not state.is_ready:
        raise ToolError("Server not initialized. Please try again shortly.")

    t0 = time.monotonic()

    entity_matcher = state.entity_matchers.get(source) if source else state.entity_matcher
    entity_index = state.entity_indices.get(source) if source else state.entity_index
    if entity_index is None:
        entity_index = state.entity_index

    if entity_matcher is None:
        raise ToolError("Entity matcher not available.")

    match_result = entity_matcher.match(topic)

    search_tool = tool_ref("docs_search", source)

    if not match_result.entities:
        return (
            f"No matching APIs or concepts found for `{topic}`.\n\n"
            f'**Next step:** Use {search_tool} with query `"{topic}"` '
            f"for a broader documentation search."
        )

    lines: list[str] = [f'# Related documentation for "{topic}"\n']

    seen: set[str] = set()
    related_entities: list[str] = []

    for entity_name in match_result.entities:
        entity = entity_index.entities.get(entity_name)
        if entity is None:
            continue

        seen.add(entity_name)
        type_label = entity.entity_type.replace("_", " ").title()
        entity_source = getattr(entity, "source", source or "vue")
        source_def = SOURCE_REGISTRY.get(entity_source)
        base_url = source_def.base_url if source_def else "https://vuejs.org"

        lines.append(f"## `{entity_name}`\n")
        lines.append(f"> **{type_label}**")

        if entity.page_path:
            page = entity.page_path.removeprefix("/").removesuffix(".mdx").removesuffix(".md")
            lines[-1] += f" — [{page}]({base_url}/{page})"

        lines.append("")

        if entity.related:
            for r in entity.related:
                if r not in seen:
                    related_entities.append(r)
                    seen.add(r)

    if related_entities:
        lines.append("## Related APIs\n")
        lines.append("| API | Type | Documentation |")
        lines.append("|-----|------|---------------|")
        for rel_name in related_entities:
            rel_entity = entity_index.entities.get(rel_name)
            if rel_entity:
                type_label = rel_entity.entity_type.replace("_", " ").title()
                rel_source = getattr(rel_entity, "source", source or "vue")
                rel_def = SOURCE_REGISTRY.get(rel_source)
                rel_base = rel_def.base_url if rel_def else "https://vuejs.org"
                if rel_entity.page_path:
                    page = (
                        rel_entity.page_path.removeprefix("/")
                        .removesuffix(".mdx")
                        .removesuffix(".md")
                    )
                    doc_link = f"[{page}]({rel_base}/{page})"
                else:
                    doc_link = "—"
                lines.append(f"| `{rel_name}` | {type_label} | {doc_link} |")
            else:
                lines.append(f"| `{rel_name}` | — | — |")
        lines.append("")

    lines.append("---\n")
    lines.append("**Next steps:**")
    api_names = list(seen)[:3]
    lines.append(f'- {search_tool} with query `"{topic}"` for full documentation content')
    lookup_tool = tool_ref("api_lookup", source)
    for name in api_names:
        lines.append(f'- {lookup_tool} on `"{name}"` for API details')

    result = "\n".join(lines)
    log_tool_call(
        "get_related",
        query=topic,
        framework=source,
        latency_ms=max(1, round((time.monotonic() - t0) * 1000)),  # 0 would mean "not measured"
        response_chars=len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Per-source tool factory
# ---------------------------------------------------------------------------


def make_related_tool(sources: list[SourceDefinition]):
    """Create the framework-parameterised get-related tool."""
    Framework = framework_param(sources)

    async def get_related(
        framework: Framework,
        topic: Annotated[
            str,
            Field(description="An API name, concept, or topic to find related documentation for."),
        ],
        ctx: Context = None,
    ) -> str:
        """Find related documentation for a topic or API name in one framework.

        Uses entity matching, synonym resolution, and the API relationship
        graph to discover related concepts, APIs, and documentation pages.
        """
        return await _do_get_related(topic, source=framework, ctx=ctx)

    return get_related
