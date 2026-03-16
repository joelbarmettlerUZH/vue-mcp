"""Tests for Day 9-10: Gemini client, contextual enrichment, and HyPE.

Covers GeminiClient (mocked HTTP), enrichment orchestration, HyPE question
generation, HyPE embedding, HyPE indexing, and HyPE search resolution.
No real API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestGeminiClient:
    def _make_api_response(
        self, text: str = "Generated text", input_tokens: int = 100, output_tokens: int = 20
    ) -> dict:
        return {
            "candidates": [
                {"content": {"parts": [{"text": text}]}}
            ],
            "usageMetadata": {
                "promptTokenCount": input_tokens,
                "candidatesTokenCount": output_tokens,
            },
        }

    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        client = GeminiClient(api_key="test-key", model="gemini-2.5-flash")
        api_resp = self._make_api_response("Hello world")

        with patch.object(
            client, "_request_with_retry", new=AsyncMock(return_value=api_resp)
        ):
            result = await client.generate("Say hello")

        assert result.text == "Hello world"
        assert result.input_tokens == 100
        assert result.output_tokens == 20

    @pytest.mark.asyncio
    async def test_generate_strips_whitespace(self):
        client = GeminiClient(api_key="test-key")
        api_resp = self._make_api_response("  trimmed  \n")

        with patch.object(
            client, "_request_with_retry", new=AsyncMock(return_value=api_resp)
        ):
            result = await client.generate("prompt")

        assert result.text == "trimmed"

    @pytest.mark.asyncio
    async def test_generate_empty_response(self):
        client = GeminiClient(api_key="test-key")
        api_resp = {"candidates": [], "usageMetadata": {}}

        with patch.object(
            client, "_request_with_retry", new=AsyncMock(return_value=api_resp)
        ):
            result = await client.generate("prompt")

        assert result.text == ""

    @pytest.mark.asyncio
    async def test_generate_includes_system_instruction(self):
        client = GeminiClient(api_key="test-key")
        captured_payload = {}

        async def capture_request(url, payload):
            captured_payload.update(payload)
            return self._make_api_response("response")

        with patch.object(client, "_request_with_retry", side_effect=capture_request):
            await client.generate("prompt", system_instruction="Be helpful")

        assert "systemInstruction" in captured_payload
        assert captured_payload["systemInstruction"]["parts"][0]["text"] == "Be helpful"

    @pytest.mark.asyncio
    async def test_generate_without_system_instruction(self):
        client = GeminiClient(api_key="test-key")
        captured_payload = {}

        async def capture_request(url, payload):
            captured_payload.update(payload)
            return self._make_api_response("response")

        with patch.object(client, "_request_with_retry", side_effect=capture_request):
            await client.generate("prompt")

        assert "systemInstruction" not in captured_payload

    @pytest.mark.asyncio
    async def test_enrich_chunk_returns_prefix(self):
        client = GeminiClient(api_key="test-key")
        prefix = "This chunk explains computed property caching in Vue 3."

        with patch.object(
            client, "generate_cached",
            new=AsyncMock(return_value=GeminiResponse(text=prefix, input_tokens=500, output_tokens=30)),
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
        api_resp = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "my_func",
                            "args": {"key": "value", "count": 3},
                        }
                    }]
                }
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 20,
            },
        }

        with patch.object(
            client, "_request_with_retry", new=AsyncMock(return_value=api_resp)
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
    async def test_generate_with_tool_includes_tool_config(self):
        client = GeminiClient(api_key="test-key")
        captured_payload = {}

        async def capture_request(url, payload):
            captured_payload.update(payload)
            return {
                "candidates": [{"content": {"parts": [{"functionCall": {"name": "f", "args": {}}}]}}],
                "usageMetadata": {},
            }

        with patch.object(client, "_request_with_retry", side_effect=capture_request):
            await client.generate_with_tool(
                "prompt",
                function_name="f",
                function_description="desc",
                parameters_schema={"type": "object", "properties": {}},
            )

        assert "tools" in captured_payload
        assert captured_payload["tool_config"]["function_calling_config"]["mode"] == "ANY"
        assert captured_payload["tool_config"]["function_calling_config"]["allowed_function_names"] == ["f"]

    @pytest.mark.asyncio
    async def test_generate_with_tool_empty_response(self):
        client = GeminiClient(api_key="test-key")
        api_resp = {"candidates": [], "usageMetadata": {}}

        with patch.object(
            client, "_request_with_retry", new=AsyncMock(return_value=api_resp)
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
        enriched, skipped, errors = await enrich_chunks_contextual(
            chunks, page_contents, client
        )

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
            arguments={"questions": [
                "How does computed property caching work in Vue?",
                "Why is my computed not updating?",
                "What is the difference between computed and methods?",
            ]},
            input_tokens=500,
            output_tokens=50,
        )

        with patch.object(
            client, "generate_cached_with_tool",
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
            client, "generate_cached_with_tool",
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
            client, "generate_cached_with_tool",
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
            client, "generate_cached_with_tool",
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
        from vue_docs_core.clients.jina import EmbeddingResult, JinaClient, TASK_RETRIEVAL_QUERY
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
        from vue_docs_ingestion.indexer import _hype_payload
        from vue_docs_ingestion.embedder import HypeEmbedding

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
        from vue_docs_ingestion.indexer import _hype_payload
        from vue_docs_ingestion.embedder import HypeEmbedding

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
