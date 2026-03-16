"""Tests for Day 9-10-13: Gemini client, contextual enrichment, HyPE, and RAPTOR summaries.

Covers GeminiClient (mocked HTTP), enrichment orchestration, HyPE question
generation, HyPE embedding, HyPE indexing, HyPE search resolution, and
RAPTOR hierarchical summary generation (page, folder, top-level).
No real API calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vue_docs_core.clients.gemini import GeminiClient, GeminiFunctionCallResponse, GeminiResponse
from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType
from vue_docs_ingestion.enrichment import enrich_chunks_contextual, generate_hype_questions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str = "guide/essentials/computed#computed-caching",
    content: str = "Computed properties are cached.",
    chunk_type: ChunkType = ChunkType.SECTION,
    file_path: str = "guide/essentials/computed.md",
    folder_path: str = "guide/essentials",
    page_title: str = "Computed Properties",
    contextual_prefix: str = "",
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        content=content,
        metadata=ChunkMetadata(
            file_path=file_path,
            folder_path=folder_path,
            page_title=page_title,
            section_title="Computed Caching",
        ),
        contextual_prefix=contextual_prefix,
        content_hash="abc123",
    )


# ---------------------------------------------------------------------------
# GeminiClient tests (mocked HTTP)
# ---------------------------------------------------------------------------


def _mock_sdk_response(text="Generated text", input_tokens=100, output_tokens=20):
    """Create a mock google-genai SDK response object."""
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.candidates = [
        MagicMock(
            content=MagicMock(
                parts=[MagicMock(text=text, function_call=None)]
            )
        )
    ]
    mock_resp.usage_metadata = MagicMock(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
    )
    return mock_resp


def _mock_sdk_function_call_response(
    function_name="my_func", arguments=None, input_tokens=100, output_tokens=20
):
    """Create a mock google-genai SDK response with a function call."""
    args = arguments or {}
    fc = MagicMock()
    fc.name = function_name
    fc.args = args

    part = MagicMock()
    part.function_call = fc

    mock_resp = MagicMock()
    mock_resp.text = None
    mock_resp.candidates = [MagicMock(content=MagicMock(parts=[part]))]
    mock_resp.usage_metadata = MagicMock(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
    )
    return mock_resp


class TestGeminiClient:
    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        client = GeminiClient(api_key="test-key", model="gemini-2.5-flash")
        mock_resp = _mock_sdk_response("Hello world")

        with patch.object(
            client._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)
        ):
            result = await client.generate("Say hello")

        assert result.text == "Hello world"
        assert result.input_tokens == 100
        assert result.output_tokens == 20

    @pytest.mark.asyncio
    async def test_generate_strips_whitespace(self):
        client = GeminiClient(api_key="test-key")
        mock_resp = _mock_sdk_response("  trimmed  \n")

        with patch.object(
            client._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)
        ):
            result = await client.generate("prompt")

        assert result.text == "trimmed"

    @pytest.mark.asyncio
    async def test_generate_empty_response(self):
        client = GeminiClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.text = None
        mock_resp.candidates = []
        mock_resp.usage_metadata = None

        with patch.object(
            client._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)
        ):
            result = await client.generate("prompt")

        assert result.text == ""

    @pytest.mark.asyncio
    async def test_enrich_chunk_returns_prefix(self):
        client = GeminiClient(api_key="test-key")
        prefix = "This chunk explains computed property caching in Vue 3."

        with patch.object(
            client,
            "generate_cached",
            new=AsyncMock(
                return_value=GeminiResponse(text=prefix, input_tokens=500, output_tokens=30)
            ),
        ):
            result = await client.enrich_chunk(
                page_content="# Computed\n\nFull page here...",
                chunk_content="Computed properties are cached.",
                page_title="Computed Properties",
            )

        assert result == prefix

    @pytest.mark.asyncio
    async def test_generate_cached_combines_content(self):
        client = GeminiClient(api_key="test-key")
        captured_prompt = ""

        async def capture_generate(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return GeminiResponse(text="result", input_tokens=10, output_tokens=5)

        with patch.object(client, "generate", side_effect=capture_generate):
            await client.generate_cached(
                cached_content="PAGE CONTENT",
                per_chunk_prompt="CHUNK PROMPT",
            )

        assert "PAGE CONTENT" in captured_prompt
        assert "CHUNK PROMPT" in captured_prompt
        assert "---" in captured_prompt

    @pytest.mark.asyncio
    async def test_generate_with_tool_returns_function_call(self):
        client = GeminiClient(api_key="test-key")
        mock_resp = _mock_sdk_function_call_response(
            function_name="my_func",
            arguments={"key": "value", "count": 3},
            input_tokens=100,
            output_tokens=20,
        )

        with patch.object(
            client._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)
        ):
            result = await client.generate_with_tool(
                "Generate something",
                function_name="my_func",
                function_description="A test function",
                parameters_schema={
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "count": {"type": "integer"}},
                    "required": ["key"],
                },
            )

        assert result.function_name == "my_func"
        assert result.arguments == {"key": "value", "count": 3}
        assert result.input_tokens == 100
        assert result.output_tokens == 20

    @pytest.mark.asyncio
    async def test_generate_with_tool_empty_response(self):
        client = GeminiClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.text = None
        mock_resp.candidates = []
        mock_resp.usage_metadata = None

        with patch.object(
            client._client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)
        ):
            result = await client.generate_with_tool(
                "prompt",
                function_name="f",
                function_description="desc",
                parameters_schema={"type": "object", "properties": {}},
            )

        assert result.arguments == {}


# ---------------------------------------------------------------------------
# Enrichment orchestration tests
# ---------------------------------------------------------------------------


class TestEnrichChunksContextual:
    @pytest.mark.asyncio
    async def test_enriches_section_chunks(self):
        chunks = [
            _make_chunk(chunk_id="page#s1", content="Section 1 content"),
            _make_chunk(chunk_id="page#s2", content="Section 2 content"),
        ]
        page_contents = {"guide/essentials/computed.md": "# Full page\n\nAll content here."}

        client = GeminiClient(api_key="test-key")
        call_count = 0

        async def fake_enrich(page_content, chunk_content, page_title):
            nonlocal call_count
            call_count += 1
            return f"Context for: {chunk_content[:20]}"

        with patch.object(client, "enrich_chunk", side_effect=fake_enrich):
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        assert enriched == 2
        assert errors == 0
        assert chunks[0].contextual_prefix == "Context for: Section 1 content"
        assert chunks[1].contextual_prefix == "Context for: Section 2 content"

    @pytest.mark.asyncio
    async def test_skips_non_enrichable_types(self):
        chunks = [
            _make_chunk(chunk_id="page#summary", chunk_type=ChunkType.PAGE_SUMMARY),
            _make_chunk(chunk_id="page#hype", chunk_type=ChunkType.HYPE_QUESTION),
            _make_chunk(chunk_id="page#section", chunk_type=ChunkType.SECTION),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page content"}

        client = GeminiClient(api_key="test-key")

        async def fake_enrich(page_content, chunk_content, page_title):
            return "enriched"

        with patch.object(client, "enrich_chunk", side_effect=fake_enrich):
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        # Only SECTION should be enriched; PAGE_SUMMARY and HYPE_QUESTION are non-enrichable
        assert enriched == 1
        assert skipped == 2

    @pytest.mark.asyncio
    async def test_skips_already_enriched_chunks(self):
        chunks = [
            _make_chunk(
                chunk_id="page#s1",
                contextual_prefix="Already enriched",
            ),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page content"}

        client = GeminiClient(api_key="test-key")
        with patch.object(client, "enrich_chunk", new=AsyncMock()) as mock_enrich:
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        # Should not call enrich_chunk for already-enriched chunk
        mock_enrich.assert_not_called()
        assert enriched == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_handles_missing_page_content(self):
        chunks = [_make_chunk(chunk_id="page#s1")]
        page_contents = {}  # No page content available

        client = GeminiClient(api_key="test-key")
        enriched, skipped, errors = await enrich_chunks_contextual(chunks, page_contents, client)

        assert enriched == 0
        assert skipped >= 1

    @pytest.mark.asyncio
    async def test_handles_enrichment_errors_gracefully(self):
        chunks = [
            _make_chunk(chunk_id="page#s1", content="Good chunk"),
            _make_chunk(chunk_id="page#s2", content="Bad chunk"),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page content"}

        client = GeminiClient(api_key="test-key")

        async def flaky_enrich(page_content, chunk_content, page_title):
            if "Bad" in chunk_content:
                raise RuntimeError("API error")
            return "enriched successfully"

        with patch.object(client, "enrich_chunk", side_effect=flaky_enrich):
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        # One should succeed, one should fail gracefully
        assert enriched == 1
        assert errors >= 1
        assert chunks[0].contextual_prefix == "enriched successfully"
        assert chunks[1].contextual_prefix == ""  # Failed chunk keeps empty prefix

    @pytest.mark.asyncio
    async def test_enriches_code_block_and_image_chunks(self):
        chunks = [
            _make_chunk(chunk_id="page#code", chunk_type=ChunkType.CODE_BLOCK),
            _make_chunk(chunk_id="page#img", chunk_type=ChunkType.IMAGE),
            _make_chunk(chunk_id="page#sub", chunk_type=ChunkType.SUBSECTION),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page"}

        client = GeminiClient(api_key="test-key")

        async def fake_enrich(page_content, chunk_content, page_title):
            return "enriched"

        with patch.object(client, "enrich_chunk", side_effect=fake_enrich):
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        assert enriched == 3  # All three types are enrichable

    @pytest.mark.asyncio
    async def test_groups_chunks_by_file(self):
        chunks = [
            _make_chunk(chunk_id="file1#s1", file_path="guide/a.md"),
            _make_chunk(chunk_id="file1#s2", file_path="guide/a.md"),
            _make_chunk(chunk_id="file2#s1", file_path="guide/b.md"),
        ]
        page_contents = {
            "guide/a.md": "# Page A",
            "guide/b.md": "# Page B",
        }

        client = GeminiClient(api_key="test-key")
        pages_seen = set()

        async def fake_enrich(page_content, chunk_content, page_title):
            pages_seen.add(page_content)
            return "enriched"

        with patch.object(client, "enrich_chunk", side_effect=fake_enrich):
            enriched, skipped, errors = await enrich_chunks_contextual(
                chunks, page_contents, client
            )

        assert enriched == 3
        assert pages_seen == {"# Page A", "# Page B"}


# ---------------------------------------------------------------------------
# Embedder with contextual prefix
# ---------------------------------------------------------------------------


class TestEmbedderWithPrefix:
    @pytest.mark.asyncio
    async def test_embed_prepends_contextual_prefix(self):
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient
        from vue_docs_ingestion.embedder import embed_dense

        chunk = _make_chunk(
            content="Computed properties are cached.",
            contextual_prefix="This section covers computed property caching in Vue.",
        )
        captured_texts = []

        async def fake_embed(texts, task):
            captured_texts.extend(texts)
            return EmbeddingResult(embeddings=[[0.0] * 1024], total_tokens=10)

        client = JinaClient(api_key="test")
        with patch.object(client, "embed", side_effect=fake_embed):
            await embed_dense([chunk], client)

        assert len(captured_texts) == 1
        assert captured_texts[0].startswith("This section covers")
        assert "Computed properties are cached." in captured_texts[0]

    @pytest.mark.asyncio
    async def test_embed_without_prefix_uses_raw_content(self):
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient
        from vue_docs_ingestion.embedder import embed_dense

        chunk = _make_chunk(content="Raw content only.")
        captured_texts = []

        async def fake_embed(texts, task):
            captured_texts.extend(texts)
            return EmbeddingResult(embeddings=[[0.0] * 1024], total_tokens=5)

        client = JinaClient(api_key="test")
        with patch.object(client, "embed", side_effect=fake_embed):
            await embed_dense([chunk], client)

        assert captured_texts == ["Raw content only."]


# ---------------------------------------------------------------------------
# Indexer stores contextual_prefix
# ---------------------------------------------------------------------------


class TestIndexerContextualPrefix:
    def test_payload_includes_contextual_prefix(self):
        from vue_docs_ingestion.indexer import _chunk_payload

        chunk = _make_chunk(contextual_prefix="This is the context.")
        payload = _chunk_payload(chunk)
        assert payload["contextual_prefix"] == "This is the context."

    def test_payload_empty_prefix(self):
        from vue_docs_ingestion.indexer import _chunk_payload

        chunk = _make_chunk()
        payload = _chunk_payload(chunk)
        assert payload["contextual_prefix"] == ""


# ---------------------------------------------------------------------------
# Day 10: HyPE question generation
# ---------------------------------------------------------------------------


class TestGeminiHypeGeneration:
    @pytest.mark.asyncio
    async def test_generate_hype_questions_returns_list(self):
        client = GeminiClient(api_key="test-key")
        fc_response = GeminiFunctionCallResponse(
            function_name="save_questions",
            arguments={
                "questions": [
                    "How does computed property caching work in Vue?",
                    "Why is my computed not updating?",
                    "What is the difference between computed and methods?",
                ]
            },
            input_tokens=500,
            output_tokens=50,
        )

        with patch.object(
            client,
            "generate_cached_with_tool",
            new=AsyncMock(return_value=fc_response),
        ):
            result = await client.generate_hype_questions(
                page_content="# Computed\n\nFull page...",
                chunk_content="Computed properties are cached.",
                page_title="Computed Properties",
                num_questions=3,
            )

        assert len(result) == 3
        assert "computed property caching" in result[0].lower()

    @pytest.mark.asyncio
    async def test_generate_hype_filters_empty_strings(self):
        client = GeminiClient(api_key="test-key")
        fc_response = GeminiFunctionCallResponse(
            function_name="save_questions",
            arguments={"questions": ["Question one?", "", "Question two?"]},
            input_tokens=100,
            output_tokens=20,
        )

        with patch.object(
            client,
            "generate_cached_with_tool",
            new=AsyncMock(return_value=fc_response),
        ):
            result = await client.generate_hype_questions(
                page_content="page",
                chunk_content="chunk",
                page_title="Title",
                num_questions=5,
            )

        assert len(result) == 2
        assert result[0] == "Question one?"
        assert result[1] == "Question two?"

    @pytest.mark.asyncio
    async def test_generate_hype_truncates_to_num_questions(self):
        client = GeminiClient(api_key="test-key")
        fc_response = GeminiFunctionCallResponse(
            function_name="save_questions",
            arguments={"questions": ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?", "Q6?", "Q7?"]},
            input_tokens=100,
            output_tokens=30,
        )

        with patch.object(
            client,
            "generate_cached_with_tool",
            new=AsyncMock(return_value=fc_response),
        ):
            result = await client.generate_hype_questions(
                page_content="page",
                chunk_content="chunk",
                page_title="Title",
                num_questions=3,
            )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_generate_hype_handles_missing_questions_key(self):
        client = GeminiClient(api_key="test-key")
        fc_response = GeminiFunctionCallResponse(
            function_name="save_questions",
            arguments={},  # Missing "questions" key
            input_tokens=100,
            output_tokens=10,
        )

        with patch.object(
            client,
            "generate_cached_with_tool",
            new=AsyncMock(return_value=fc_response),
        ):
            result = await client.generate_hype_questions(
                page_content="page",
                chunk_content="chunk",
                page_title="Title",
            )

        assert result == []


class TestHypeQuestionOrchestration:
    @pytest.mark.asyncio
    async def test_generates_questions_for_enrichable_chunks(self):
        chunks = [
            _make_chunk(chunk_id="page#s1", content="Section 1"),
            _make_chunk(chunk_id="page#s2", content="Section 2"),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page"}

        client = GeminiClient(api_key="test-key")

        async def fake_hype(page_content, chunk_content, page_title, num_questions=5):
            return [f"Q about {chunk_content[:10]}?"]

        with patch.object(client, "generate_hype_questions", side_effect=fake_hype):
            generated, skipped, errors = await generate_hype_questions(
                chunks, page_contents, client
            )

        assert generated == 2
        assert errors == 0
        assert len(chunks[0].hype_questions) == 1
        assert len(chunks[1].hype_questions) == 1

    @pytest.mark.asyncio
    async def test_skips_non_enrichable_types(self):
        chunks = [
            _make_chunk(chunk_id="page#summary", chunk_type=ChunkType.PAGE_SUMMARY),
            _make_chunk(chunk_id="page#section", chunk_type=ChunkType.SECTION),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page"}

        client = GeminiClient(api_key="test-key")

        async def fake_hype(page_content, chunk_content, page_title, num_questions=5):
            return ["Q?"]

        with patch.object(client, "generate_hype_questions", side_effect=fake_hype):
            generated, skipped, errors = await generate_hype_questions(
                chunks, page_contents, client
            )

        assert generated == 1
        assert skipped == 1  # PAGE_SUMMARY is non-enrichable

    @pytest.mark.asyncio
    async def test_skips_already_generated(self):
        chunk = _make_chunk(chunk_id="page#s1")
        chunk.hype_questions = ["Existing question?"]
        chunks = [chunk]
        page_contents = {"guide/essentials/computed.md": "# Page"}

        client = GeminiClient(api_key="test-key")
        with patch.object(client, "generate_hype_questions", new=AsyncMock()) as mock:
            generated, skipped, errors = await generate_hype_questions(
                chunks, page_contents, client
            )

        mock.assert_not_called()
        assert generated == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_handles_errors_gracefully(self):
        chunks = [
            _make_chunk(chunk_id="page#s1", content="Good"),
            _make_chunk(chunk_id="page#s2", content="Bad"),
        ]
        page_contents = {"guide/essentials/computed.md": "# Page"}

        client = GeminiClient(api_key="test-key")

        async def flaky_hype(page_content, chunk_content, page_title, num_questions=5):
            if "Bad" in chunk_content:
                raise RuntimeError("API error")
            return ["Q?"]

        with patch.object(client, "generate_hype_questions", side_effect=flaky_hype):
            generated, skipped, errors = await generate_hype_questions(
                chunks, page_contents, client
            )

        assert generated == 1
        assert errors >= 1
        assert chunks[0].hype_questions == ["Q?"]
        assert chunks[1].hype_questions == []


# ---------------------------------------------------------------------------
# Day 10: HyPE embedding
# ---------------------------------------------------------------------------


class TestHypeEmbedding:
    @pytest.mark.asyncio
    async def test_embeds_hype_questions_with_query_task(self):
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient
        from vue_docs_core.config import TASK_RETRIEVAL_QUERY
        from vue_docs_ingestion.embedder import embed_hype_questions

        chunk = _make_chunk(chunk_id="page#s1")
        chunk.hype_questions = ["Q1?", "Q2?"]

        captured_tasks = []

        async def fake_embed(texts, task):
            captured_tasks.append(task)
            return EmbeddingResult(
                embeddings=[[0.1] * 1024 for _ in texts],
                total_tokens=len(texts) * 5,
            )

        client = JinaClient(api_key="test")
        with patch.object(client, "embed", side_effect=fake_embed):
            hype_embeddings, tokens = await embed_hype_questions([chunk], client)

        assert len(hype_embeddings) == 2
        assert all(t == TASK_RETRIEVAL_QUERY for t in captured_tasks)
        assert hype_embeddings[0].parent_chunk_id == "page#s1"
        assert hype_embeddings[0].question == "Q1?"
        assert hype_embeddings[1].question == "Q2?"

    @pytest.mark.asyncio
    async def test_skips_chunks_without_questions(self):
        from vue_docs_core.clients.jina import JinaClient
        from vue_docs_ingestion.embedder import embed_hype_questions

        chunk = _make_chunk(chunk_id="page#s1")
        # No hype_questions set

        client = JinaClient(api_key="test")
        hype_embeddings, tokens = await embed_hype_questions([chunk], client)

        assert len(hype_embeddings) == 0
        assert tokens == 0


# ---------------------------------------------------------------------------
# Day 10: HyPE indexer
# ---------------------------------------------------------------------------


class TestHypeIndexer:
    def test_hype_payload_structure(self):
        from vue_docs_ingestion.embedder import HypeEmbedding
        from vue_docs_ingestion.indexer import _hype_payload

        parent = _make_chunk(chunk_id="guide/computed#caching")
        hype = HypeEmbedding(
            question="How does caching work?",
            parent_chunk_id="guide/computed#caching",
            parent_chunk=parent,
            embedding=[0.1] * 1024,
        )
        payload = _hype_payload(hype)

        assert payload["chunk_type"] == "hype_question"
        assert payload["parent_chunk_id"] == "guide/computed#caching"
        assert payload["content"] == "How does caching work?"
        assert payload["file_path"] == parent.metadata.file_path
        assert payload["folder_path"] == parent.metadata.folder_path

    def test_hype_payload_inherits_parent_metadata(self):
        from vue_docs_ingestion.embedder import HypeEmbedding
        from vue_docs_ingestion.indexer import _hype_payload

        parent = _make_chunk(
            chunk_id="guide/computed#section",
            page_title="Computed Properties",
        )
        parent.metadata.api_entities = ["computed", "ref"]
        parent.metadata.api_style = "composition"

        hype = HypeEmbedding(
            question="Q?",
            parent_chunk_id=parent.chunk_id,
            parent_chunk=parent,
            embedding=[0.0],
        )
        payload = _hype_payload(hype)

        assert payload["page_title"] == "Computed Properties"
        assert payload["api_entities"] == ["computed", "ref"]
        assert payload["api_style"] == "composition"


# ---------------------------------------------------------------------------
# Day 10: HyPE search resolution
# ---------------------------------------------------------------------------


class TestHypeSearchResolution:
    def test_resolves_hype_hits_to_parent(self):
        from vue_docs_core.clients.qdrant import SearchHit
        from vue_docs_server.tools.search import _resolve_hype_hits

        # Mock state.qdrant
        parent_payload = {
            "chunk_id": "guide/computed#caching",
            "chunk_type": "section",
            "content": "Computed properties are cached.",
            "file_path": "guide/essentials/computed.md",
        }

        hype_hit = SearchHit(
            chunk_id="guide/computed#caching#hype#0",
            score=0.9,
            payload={
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/computed#caching",
                "content": "How does caching work?",
            },
        )

        with patch("vue_docs_server.tools.search.state") as mock_state:
            mock_state.qdrant.get_by_chunk_ids.return_value = [parent_payload]
            result = _resolve_hype_hits([hype_hit])

        assert len(result) == 1
        assert result[0].chunk_id == "guide/computed#caching"
        assert result[0].payload["content"] == "Computed properties are cached."

    def test_deduplicates_hype_and_regular_hits(self):
        from vue_docs_core.clients.qdrant import SearchHit
        from vue_docs_server.tools.search import _resolve_hype_hits

        regular_hit = SearchHit(
            chunk_id="guide/computed#caching",
            score=0.8,
            payload={"chunk_type": "section", "content": "Cached."},
        )
        hype_hit = SearchHit(
            chunk_id="guide/computed#caching#hype#0",
            score=0.9,
            payload={
                "chunk_type": "hype_question",
                "parent_chunk_id": "guide/computed#caching",
            },
        )

        with patch("vue_docs_server.tools.search.state") as mock_state:
            mock_state.qdrant = None  # Parent already in results, no fetch needed
            result = _resolve_hype_hits([regular_hit, hype_hit])

        # Should keep only the regular hit (already present, deduplication)
        assert len(result) == 1
        assert result[0].chunk_id == "guide/computed#caching"

    def test_passes_through_regular_hits(self):
        from vue_docs_core.clients.qdrant import SearchHit
        from vue_docs_server.tools.search import _resolve_hype_hits

        hit = SearchHit(
            chunk_id="guide/ref#intro",
            score=0.85,
            payload={"chunk_type": "section", "content": "ref is..."},
        )

        with patch("vue_docs_server.tools.search.state") as mock_state:
            mock_state.qdrant = None
            result = _resolve_hype_hits([hit])

        assert len(result) == 1
        assert result[0].chunk_id == "guide/ref#intro"


# ---------------------------------------------------------------------------
# Day 13: RAPTOR hierarchical summaries
# ---------------------------------------------------------------------------


class TestGeminiGenerateSummary:
    @pytest.mark.asyncio
    async def test_generate_page_summary(self):
        client = GeminiClient(api_key="test-key")

        with patch.object(
            client,
            "generate",
            new=AsyncMock(
                return_value=GeminiResponse(
                    text="This page covers computed properties in Vue 3.",
                    input_tokens=500,
                    output_tokens=30,
                )
            ),
        ):
            result = await client.generate_summary(
                "# Computed\n\nFull page content...",
                level="page",
                title="Computed Properties",
            )

        assert "computed" in result.lower()

    @pytest.mark.asyncio
    async def test_generate_folder_summary(self):
        client = GeminiClient(api_key="test-key")

        with patch.object(
            client,
            "generate",
            new=AsyncMock(
                return_value=GeminiResponse(
                    text="This section covers Vue essentials.",
                    input_tokens=300,
                    output_tokens=20,
                )
            ),
        ):
            result = await client.generate_summary(
                "**Reactivity:** ...\n\n**Computed:** ...",
                level="folder",
                title="Guide > Essentials",
            )

        assert "essentials" in result.lower()

    @pytest.mark.asyncio
    async def test_generate_top_summary(self):
        client = GeminiClient(api_key="test-key")

        with patch.object(
            client,
            "generate",
            new=AsyncMock(
                return_value=GeminiResponse(
                    text="The guide covers all core Vue concepts.",
                    input_tokens=200,
                    output_tokens=15,
                )
            ),
        ):
            result = await client.generate_summary(
                "**Essentials:** ...\n\n**Components:** ...",
                level="top",
                title="Guide",
            )

        assert len(result) > 0


class TestGeneratePageSummaries:
    @pytest.mark.asyncio
    async def test_generates_one_summary_per_page(self):
        from vue_docs_ingestion.enrichment import generate_page_summaries

        chunks = [
            _make_chunk(chunk_id="page#s1", file_path="guide/a.md", page_title="Page A"),
            _make_chunk(chunk_id="page#s2", file_path="guide/a.md", page_title="Page A"),
            _make_chunk(
                chunk_id="page2#s1",
                file_path="guide/b.md",
                page_title="Page B",
                folder_path="guide",
            ),
        ]
        page_contents = {
            "guide/a.md": "# Page A content",
            "guide/b.md": "# Page B content",
        }

        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="page", title=""):
            return f"Summary of {title}"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_page_summaries(chunks, page_contents, client)

        assert len(summaries) == 2
        assert all(s.chunk_type == ChunkType.PAGE_SUMMARY for s in summaries)
        ids = {s.chunk_id for s in summaries}
        assert "guide/a#page_summary" in ids
        assert "guide/b#page_summary" in ids

    @pytest.mark.asyncio
    async def test_page_summary_inherits_metadata(self):
        from vue_docs_ingestion.enrichment import generate_page_summaries

        chunk = _make_chunk(
            chunk_id="guide/essentials/computed#s1",
            file_path="guide/essentials/computed.md",
            folder_path="guide/essentials",
            page_title="Computed Properties",
        )
        chunk.metadata.api_entities = ["computed"]
        chunk.metadata.api_style = "composition"

        page_contents = {"guide/essentials/computed.md": "# Computed"}
        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="page", title=""):
            return "Summary text"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_page_summaries([chunk], page_contents, client)

        assert len(summaries) == 1
        s = summaries[0]
        assert s.metadata.folder_path == "guide/essentials"
        assert s.metadata.page_title == "Computed Properties"
        assert s.metadata.api_style == "composition"
        assert "computed" in s.metadata.api_entities

    @pytest.mark.asyncio
    async def test_skips_pages_without_content(self):
        from vue_docs_ingestion.enrichment import generate_page_summaries

        chunks = [_make_chunk(file_path="guide/missing.md")]
        page_contents = {}  # No content

        client = GeminiClient(api_key="test-key")
        summaries = await generate_page_summaries(chunks, page_contents, client)

        assert len(summaries) == 0

    @pytest.mark.asyncio
    async def test_handles_llm_errors_gracefully(self):
        from vue_docs_ingestion.enrichment import generate_page_summaries

        chunks = [
            _make_chunk(chunk_id="p1#s1", file_path="guide/a.md", page_title="A"),
            _make_chunk(
                chunk_id="p2#s1", file_path="guide/b.md", page_title="B", folder_path="guide"
            ),
        ]
        page_contents = {"guide/a.md": "# A", "guide/b.md": "# B"}
        client = GeminiClient(api_key="test-key")

        call_count = 0

        async def flaky_summary(content, *, level="page", title=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API error")
            return "Summary"

        with patch.object(client, "generate_summary", side_effect=flaky_summary):
            summaries = await generate_page_summaries(chunks, page_contents, client)

        # One succeeds, one fails — should get 1 summary
        assert len(summaries) == 1


class TestGenerateFolderSummaries:
    @pytest.mark.asyncio
    async def test_generates_one_summary_per_folder(self):
        from vue_docs_ingestion.enrichment import generate_folder_summaries

        page_summaries = [
            Chunk(
                chunk_id="guide/essentials/computed#page_summary",
                chunk_type=ChunkType.PAGE_SUMMARY,
                content="Summary of computed",
                metadata=ChunkMetadata(
                    file_path="guide/essentials/computed.md",
                    folder_path="guide/essentials",
                    page_title="Computed Properties",
                    global_sort_key="02_guide/01_essentials/03_computed",
                ),
            ),
            Chunk(
                chunk_id="guide/essentials/reactivity#page_summary",
                chunk_type=ChunkType.PAGE_SUMMARY,
                content="Summary of reactivity",
                metadata=ChunkMetadata(
                    file_path="guide/essentials/reactivity.md",
                    folder_path="guide/essentials",
                    page_title="Reactivity Fundamentals",
                    global_sort_key="02_guide/01_essentials/02_reactivity",
                ),
            ),
            Chunk(
                chunk_id="guide/components/props#page_summary",
                chunk_type=ChunkType.PAGE_SUMMARY,
                content="Summary of props",
                metadata=ChunkMetadata(
                    file_path="guide/components/props.md",
                    folder_path="guide/components",
                    page_title="Props",
                    global_sort_key="02_guide/02_components/01_props",
                ),
            ),
        ]

        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="folder", title=""):
            return f"Folder summary for {title}"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_folder_summaries(page_summaries, client)

        assert len(summaries) == 2
        assert all(s.chunk_type == ChunkType.FOLDER_SUMMARY for s in summaries)
        ids = {s.chunk_id for s in summaries}
        assert "guide/essentials#folder_summary" in ids
        assert "guide/components#folder_summary" in ids

    @pytest.mark.asyncio
    async def test_folder_summary_aggregates_entities(self):
        from vue_docs_ingestion.enrichment import generate_folder_summaries

        ps1 = Chunk(
            chunk_id="g/e/a#page_summary",
            chunk_type=ChunkType.PAGE_SUMMARY,
            content="Summary A",
            metadata=ChunkMetadata(
                file_path="g/e/a.md",
                folder_path="g/e",
                page_title="A",
                api_entities=["ref", "computed"],
                global_sort_key="01",
            ),
        )
        ps2 = Chunk(
            chunk_id="g/e/b#page_summary",
            chunk_type=ChunkType.PAGE_SUMMARY,
            content="Summary B",
            metadata=ChunkMetadata(
                file_path="g/e/b.md",
                folder_path="g/e",
                page_title="B",
                api_entities=["reactive", "ref"],
                global_sort_key="02",
            ),
        )

        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="folder", title=""):
            return "Folder summary"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_folder_summaries([ps1, ps2], client)

        assert len(summaries) == 1
        entities = summaries[0].metadata.api_entities
        assert "ref" in entities
        assert "computed" in entities
        assert "reactive" in entities


class TestGenerateTopSummaries:
    @pytest.mark.asyncio
    async def test_generates_one_summary_per_top_level(self):
        from vue_docs_ingestion.enrichment import generate_top_summaries

        folder_summaries = [
            Chunk(
                chunk_id="guide/essentials#folder_summary",
                chunk_type=ChunkType.FOLDER_SUMMARY,
                content="Essentials summary",
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path="guide/essentials",
                    page_title="Guide > Essentials",
                    global_sort_key="02_guide/01_essentials",
                ),
            ),
            Chunk(
                chunk_id="guide/components#folder_summary",
                chunk_type=ChunkType.FOLDER_SUMMARY,
                content="Components summary",
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path="guide/components",
                    page_title="Guide > Components",
                    global_sort_key="02_guide/02_components",
                ),
            ),
            Chunk(
                chunk_id="api#folder_summary",
                chunk_type=ChunkType.FOLDER_SUMMARY,
                content="API summary",
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path="api",
                    page_title="Api",
                    global_sort_key="05_api",
                ),
            ),
        ]

        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="top", title=""):
            return f"Top summary for {title}"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_top_summaries(folder_summaries, client)

        assert len(summaries) == 2
        assert all(s.chunk_type == ChunkType.TOP_SUMMARY for s in summaries)
        ids = {s.chunk_id for s in summaries}
        assert "guide#top_summary" in ids
        assert "api#top_summary" in ids

    @pytest.mark.asyncio
    async def test_handles_single_level_folder_path(self):
        from vue_docs_ingestion.enrichment import generate_top_summaries

        folder_summaries = [
            Chunk(
                chunk_id="tutorial#folder_summary",
                chunk_type=ChunkType.FOLDER_SUMMARY,
                content="Tutorial summary",
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path="tutorial",
                    page_title="Tutorial",
                    global_sort_key="06_tutorial",
                ),
            ),
        ]

        client = GeminiClient(api_key="test-key")

        async def fake_summary(content, *, level="top", title=""):
            return "Top summary"

        with patch.object(client, "generate_summary", side_effect=fake_summary):
            summaries = await generate_top_summaries(folder_summaries, client)

        assert len(summaries) == 1
        assert summaries[0].chunk_id == "tutorial#top_summary"

    @pytest.mark.asyncio
    async def test_handles_llm_error(self):
        from vue_docs_ingestion.enrichment import generate_top_summaries

        folder_summaries = [
            Chunk(
                chunk_id="guide/essentials#folder_summary",
                chunk_type=ChunkType.FOLDER_SUMMARY,
                content="Essentials",
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path="guide/essentials",
                    page_title="Essentials",
                    global_sort_key="01",
                ),
            ),
        ]

        client = GeminiClient(api_key="test-key")

        async def fail_summary(content, *, level="top", title=""):
            raise RuntimeError("API down")

        with patch.object(client, "generate_summary", side_effect=fail_summary):
            summaries = await generate_top_summaries(folder_summaries, client)

        assert len(summaries) == 0
