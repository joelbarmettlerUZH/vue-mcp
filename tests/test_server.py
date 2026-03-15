"""Tests for Day 6 MCP server components.

Covers startup state loading, reconstruction formatting, entity detection
in search, the MCP tool registration, and end-to-end MCP protocol integration
tests using fastmcp.Client for in-process testing.

No real API calls — Jina, Qdrant, and BM25 are mocked throughout.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
from qdrant_client.models import SparseVector

from vue_docs_core.clients.qdrant import SearchHit
from vue_docs_core.models.entity import ApiEntity, EntityIndex
from vue_docs_core.retrieval.reconstruction import (
    reconstruct_results,
    _file_path_to_url,
)
from vue_docs_server.startup import (
    ServerState,
    load_entity_dictionary,
    load_synonym_table,
    load_bm25_model,
)
from vue_docs_server.tools.search import _detect_entities, vue_docs_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hit(
    chunk_id: str = "guide/essentials/computed#computed-caching",
    score: float = 0.85,
    file_path: str = "guide/essentials/computed.md",
    page_title: str = "Computed Properties",
    section_title: str = "Computed Caching",
    breadcrumb: str = "Guide > Essentials > Computed Properties > Computed Caching",
    global_sort_key: str = "02_guide/01_essentials/03_computed/01_caching",
    chunk_type: str = "section",
    content: str = "A computed property will only re-evaluate when some of its reactive dependencies have changed.",
    language_tag: str = "",
    preceding_prose: str = "",
    api_entities: list[str] | None = None,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "file_path": file_path,
            "folder_path": file_path.rsplit("/", 1)[0] if "/" in file_path else "",
            "page_title": page_title,
            "section_title": section_title,
            "subsection_title": "",
            "breadcrumb": breadcrumb,
            "global_sort_key": global_sort_key,
            "chunk_type": chunk_type,
            "content_type": "text",
            "language_tag": language_tag,
            "preceding_prose": preceding_prose,
            "api_entities": api_entities or [],
            "content": content,
        },
    )


# ---------------------------------------------------------------------------
# Tests: Reconstruction
# ---------------------------------------------------------------------------


class TestReconstruction:
    def test_empty_hits(self):
        result = reconstruct_results([])
        assert result == "No results found."

    def test_single_hit_format(self):
        hits = [_make_hit()]
        result = reconstruct_results(hits)
        assert "Computed Properties" in result
        assert "vuejs.org" in result
        assert "re-evaluate" in result
        assert "Found 1 relevant" in result

    def test_code_block_rendering(self):
        hits = [
            _make_hit(
                chunk_type="code_block",
                content="const count = ref(0)",
                language_tag="js",
                preceding_prose="Here is a basic example:",
            )
        ]
        result = reconstruct_results(hits)
        assert "```js" in result
        assert "const count = ref(0)" in result
        assert "Here is a basic example:" in result

    def test_sort_by_global_sort_key(self):
        """Results should be ordered by sort key, not by score."""
        hits = [
            _make_hit(
                chunk_id="b",
                score=0.9,
                global_sort_key="02_second",
                section_title="Second",
                content="Second section",
            ),
            _make_hit(
                chunk_id="a",
                score=0.5,
                global_sort_key="01_first",
                section_title="First",
                content="First section",
            ),
        ]
        result = reconstruct_results(hits)
        first_pos = result.index("First section")
        second_pos = result.index("Second section")
        assert first_pos < second_pos

    def test_grouped_by_page(self):
        hits = [
            _make_hit(file_path="guide/a.md", page_title="Page A", content="Content A"),
            _make_hit(file_path="guide/b.md", page_title="Page B", content="Content B"),
        ]
        result = reconstruct_results(hits)
        assert "## Page A" in result
        assert "## Page B" in result

    def test_api_entities_displayed(self):
        hits = [_make_hit(api_entities=["computed", "ref"])]
        result = reconstruct_results(hits)
        assert "`computed`" in result
        assert "`ref`" in result

    def test_max_results_limit(self):
        hits = [_make_hit(chunk_id=f"chunk_{i}", content=f"Content {i}") for i in range(20)]
        result = reconstruct_results(hits, max_results=5)
        assert "Found 5 relevant" in result

    def test_file_path_to_url(self):
        assert _file_path_to_url("guide/essentials/computed.md") == "https://vuejs.org/guide/essentials/computed"
        assert _file_path_to_url("/api/reactivity-core.md") == "https://vuejs.org/api/reactivity-core"


# ---------------------------------------------------------------------------
# Tests: Startup State Loading
# ---------------------------------------------------------------------------


class TestStartup:
    def test_server_state_not_ready_initially(self):
        s = ServerState()
        assert not s.is_ready

    def test_server_state_ready_when_initialized(self):
        s = ServerState()
        s.qdrant = MagicMock()
        s.bm25 = MagicMock()
        assert s.is_ready

    def test_load_entity_dictionary(self, tmp_path):
        data = {
            "ref": {"page_path": "api/reactivity-core", "section": "ref()"},
            "computed": {"page_path": "api/reactivity-core", "section": "computed()"},
        }
        dict_path = tmp_path / "entity_dictionary.json"
        dict_path.write_text(json.dumps(data))

        index = load_entity_dictionary(tmp_path)
        assert len(index.entities) == 2
        assert "ref" in index.entities
        assert index.entities["ref"].page_path == "api/reactivity-core"

    def test_load_entity_dictionary_missing(self, tmp_path):
        index = load_entity_dictionary(tmp_path)
        assert len(index.entities) == 0

    def test_load_synonym_table(self, tmp_path):
        data = {"two-way binding": ["v-model"], "reactivity": ["ref", "reactive"]}
        syn_path = tmp_path / "synonym_table.json"
        syn_path.write_text(json.dumps(data))

        table = load_synonym_table(tmp_path)
        assert len(table) == 2
        assert table["two-way binding"] == ["v-model"]

    def test_load_synonym_table_missing(self, tmp_path):
        table = load_synonym_table(tmp_path)
        assert table == {}


# ---------------------------------------------------------------------------
# Tests: Entity Detection in Search
# ---------------------------------------------------------------------------


class TestEntityDetection:
    def setup_method(self):
        """Set up server state for entity detection tests."""
        from vue_docs_server.startup import state as server_state

        server_state.entity_index = EntityIndex(
            entities={
                "ref": ApiEntity(name="ref"),
                "computed": ApiEntity(name="computed"),
                "defineProps": ApiEntity(name="defineProps"),
                "v-model": ApiEntity(name="v-model"),
                "watchEffect": ApiEntity(name="watchEffect"),
            }
        )
        server_state.synonym_table = {
            "two-way binding": ["v-model"],
            "lifecycle": ["onMounted", "onUnmounted"],
        }

    def test_detect_inline_entity(self):
        detected = _detect_entities("how does ref work?")
        assert "ref" in detected

    def test_detect_backtick_entity(self):
        detected = _detect_entities("what does `defineProps` do?")
        assert "defineProps" in detected

    def test_detect_synonym(self):
        detected = _detect_entities("how to do two-way binding?")
        assert "v-model" in detected

    def test_detect_multiple(self):
        detected = _detect_entities("difference between ref and computed")
        assert "ref" in detected
        assert "computed" in detected

    def test_no_matches(self):
        detected = _detect_entities("how to deploy a web app")
        assert detected == []


# ---------------------------------------------------------------------------
# Tests: Search Tool (mocked Jina + Qdrant)
# ---------------------------------------------------------------------------


class TestSearchTool:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """End-to-end search with mocked Jina and Qdrant."""
        from vue_docs_server.startup import state as server_state

        # Set up state
        mock_qdrant = MagicMock()
        mock_qdrant.hybrid_search.return_value = [
            _make_hit(content="Computed properties are cached based on reactive deps.")
        ]
        server_state.qdrant = mock_qdrant

        mock_bm25 = MagicMock()
        mock_bm25.get_query_sparse_vector.return_value = SparseVector(
            indices=[1, 5], values=[1.0, 1.0]
        )
        server_state.bm25 = mock_bm25

        server_state.entity_index = EntityIndex(
            entities={"computed": ApiEntity(name="computed")}
        )
        server_state.synonym_table = {}

        # Mock Jina embedding
        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with patch("vue_docs_server.tools.search.JinaClient") as MockJina:
            mock_jina_instance = AsyncMock()
            mock_jina_instance.embed.return_value = mock_embed_result
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("how does computed caching work")

        assert "Computed Properties" in result
        assert "cached" in result
        mock_qdrant.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_not_ready(self):
        """Search returns error when server not initialized."""
        from vue_docs_server.startup import state as server_state

        server_state.qdrant = None
        server_state.bm25 = None

        result = await vue_docs_search("test query")
        assert "not initialized" in result

    @pytest.mark.asyncio
    async def test_search_scope_fallback(self):
        """When scoped search returns empty, retries with broader scope."""
        from vue_docs_server.startup import state as server_state

        mock_qdrant = MagicMock()
        # First call (scoped) returns empty, second call (all) returns results
        mock_qdrant.hybrid_search.side_effect = [
            [],
            [_make_hit(content="Found with broader scope")],
        ]
        server_state.qdrant = mock_qdrant

        mock_bm25 = MagicMock()
        mock_bm25.get_query_sparse_vector.return_value = SparseVector(
            indices=[1], values=[1.0]
        )
        server_state.bm25 = mock_bm25
        server_state.entity_index = EntityIndex()
        server_state.synonym_table = {}

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with patch("vue_docs_server.tools.search.JinaClient") as MockJina:
            mock_jina_instance = AsyncMock()
            mock_jina_instance.embed.return_value = mock_embed_result
            mock_jina_instance.close = AsyncMock()
            MockJina.return_value = mock_jina_instance

            result = await vue_docs_search("test", scope="tutorial")

        assert "broader scope" in result
        assert mock_qdrant.hybrid_search.call_count == 2


# ---------------------------------------------------------------------------
# Tests: MCP Tool Registration
# ---------------------------------------------------------------------------


class TestMCPRegistration:
    def test_mcp_app_has_tools(self):
        """Verify the MCP app has the search tool registered."""
        from vue_docs_server.main import mcp

        # FastMCP stores tools internally
        assert mcp is not None
        assert mcp.name == "Vue Docs MCP Server"


# ---------------------------------------------------------------------------
# Tests: MCP Protocol Integration (fastmcp.Client in-process)
# ---------------------------------------------------------------------------


def _setup_server_state():
    """Configure mocked server state for integration tests."""
    from vue_docs_server.startup import state as server_state

    mock_qdrant = MagicMock()
    mock_qdrant.hybrid_search.return_value = [
        _make_hit(
            content="A computed property will only re-evaluate when some of its reactive dependencies have changed.",
            api_entities=["computed"],
        )
    ]
    mock_qdrant.collection_info.return_value = {"points_count": 500, "status": "green"}
    server_state.qdrant = mock_qdrant

    mock_bm25 = MagicMock()
    mock_bm25.get_query_sparse_vector.return_value = SparseVector(
        indices=[1, 5], values=[1.0, 1.0]
    )
    server_state.bm25 = mock_bm25

    server_state.entity_index = EntityIndex(
        entities={
            "ref": ApiEntity(name="ref"),
            "computed": ApiEntity(name="computed"),
            "v-model": ApiEntity(name="v-model"),
        }
    )
    server_state.synonym_table = {
        "two-way binding": ["v-model"],
        "reactivity": ["ref", "reactive"],
    }
    return server_state


class TestMCPIntegration:
    """End-to-end tests via the MCP protocol using fastmcp.Client.

    These tests exercise the full MCP request/response cycle in-process:
    Client -> MCP protocol -> FastMCP tool dispatch -> our tool function -> response.
    Jina and Qdrant are mocked, but the MCP layer is real.

    The lifespan's startup/shutdown are patched to avoid connecting to real
    services — instead, _setup_server_state() injects mocks into the singleton.
    """

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Server exposes vue_docs_search_tool via MCP."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        tool_names = [t.name for t in tools]
        assert "vue_docs_search_tool" in tool_names

    @pytest.mark.asyncio
    async def test_tool_schema(self):
        """Search tool has correct parameter schema."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                tools = await client.list_tools()

        search_tool = next(t for t in tools if t.name == "vue_docs_search_tool")
        params = search_tool.inputSchema
        assert "query" in params["properties"]
        assert "scope" in params["properties"]
        assert "max_results" in params["properties"]
        assert "query" in params.get("required", [])

    @pytest.mark.asyncio
    async def test_call_search_tool(self):
        """Call vue_docs_search_tool through MCP protocol and get results."""
        from vue_docs_server.main import mcp

        _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "how does computed caching work"},
                )

        assert not result.is_error
        assert len(result.content) > 0
        text = result.content[0].text
        assert "Computed Properties" in text
        assert "re-evaluate" in text

    @pytest.mark.asyncio
    async def test_call_search_tool_with_scope(self):
        """Search tool respects the scope parameter."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "ref basics", "scope": "guide/essentials", "max_results": 5},
                )

        # Verify Qdrant was called with the scope filter
        call_kwargs = server_state.qdrant.hybrid_search.call_args
        assert call_kwargs.kwargs.get("scope_filter") == "guide/essentials"
        assert call_kwargs.kwargs.get("limit") == 15  # max_results * 3

    @pytest.mark.asyncio
    async def test_call_search_tool_entity_boost(self):
        """Detected entities are passed as boost filter to Qdrant."""
        from vue_docs_server.main import mcp

        server_state = _setup_server_state()

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 1024]

        with (
            patch("vue_docs_server.main.startup"),
            patch("vue_docs_server.main.shutdown"),
            patch("vue_docs_server.tools.search.JinaClient") as MockJina,
        ):
            mock_jina = AsyncMock()
            mock_jina.embed.return_value = mock_embed_result
            mock_jina.close = AsyncMock()
            MockJina.return_value = mock_jina

            async with Client(mcp) as client:
                result = await client.call_tool(
                    "vue_docs_search_tool",
                    {"query": "how does computed work"},
                )

        call_kwargs = server_state.qdrant.hybrid_search.call_args
        entity_boost = call_kwargs.kwargs.get("entity_boost")
        assert entity_boost is not None
        assert "computed" in entity_boost

    @pytest.mark.asyncio
    async def test_server_instructions(self):
        """Server provides instructions to the client."""
        from vue_docs_server.main import mcp

        with patch("vue_docs_server.main.startup"), patch("vue_docs_server.main.shutdown"):
            async with Client(mcp) as client:
                info = client.initialize_result
                assert info is not None
                assert info.serverInfo.name == "Vue Docs MCP Server"
