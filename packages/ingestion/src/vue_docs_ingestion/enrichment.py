"""LLM enrichment orchestration (contextual, HyPE, summaries).

Day 9: Contextual enrichment — for each chunk, generate a short context
prefix (2-3 sentences) using Gemini that situates the chunk within its page.
The prefix is prepended to chunk content before embedding and stored separately
so it can be stripped when presenting results.

Day 10: HyPE (Hypothetical Question Generation) — for each chunk, generate
3-5 hypothetical developer questions that the chunk would answer. These are
embedded and stored as separate Qdrant points with parent_chunk_id references,
bridging the vocabulary gap between developer queries and documentation text.
"""

import asyncio
import logging
from collections import defaultdict

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_core.models.chunk import Chunk, ChunkType

logger = logging.getLogger(__name__)

# Chunk types that should receive contextual enrichment
_ENRICHABLE_TYPES = {
    ChunkType.SECTION,
    ChunkType.SUBSECTION,
    ChunkType.CODE_BLOCK,
    ChunkType.IMAGE,
}

# Max concurrent Gemini requests per page to avoid rate limits.
# Kept low to stay within Gemini's 1M tokens/minute quota when
# processing many pages concurrently.
_PAGE_CONCURRENCY = 3


async def enrich_chunks_contextual(
    chunks: list[Chunk],
    page_contents: dict[str, str],
    gemini_client: GeminiClient,
    *,
    max_concurrent_pages: int = 3,
) -> tuple[int, int, int]:
    """Add contextual prefixes to all enrichable chunks.

    Groups chunks by page, then for each page sends the full page content
    as context to Gemini along with each chunk. Gemini's implicit caching
    benefits from the repeated page prefix across chunks from the same page.

    Args:
        chunks: All chunks (modified in-place with contextual_prefix).
        page_contents: Mapping of file_path → full raw markdown content.
        gemini_client: Initialized Gemini client.
        max_concurrent_pages: Max pages to process in parallel.

    Returns:
        Tuple of (enriched_count, skipped_count, error_count).
    """
    # Group chunks by source file
    chunks_by_file: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.chunk_type in _ENRICHABLE_TYPES:
            chunks_by_file[chunk.metadata.file_path].append(chunk)

    enriched = 0
    skipped = 0
    errors = 0

    # Use a semaphore to limit concurrent page processing
    page_sem = asyncio.Semaphore(max_concurrent_pages)

    async def process_page(file_path: str, page_chunks: list[Chunk]) -> tuple[int, int, int]:
        page_content = page_contents.get(file_path, "")
        if not page_content:
            logger.warning("No page content for %s, skipping enrichment", file_path)
            return 0, len(page_chunks), 0

        page_title = page_chunks[0].metadata.page_title if page_chunks else file_path

        async with page_sem:
            return await _enrich_page_chunks(
                page_content=page_content,
                page_title=page_title,
                page_chunks=page_chunks,
                gemini_client=gemini_client,
            )

    # Process all pages concurrently (bounded by semaphore)
    tasks = [
        process_page(file_path, page_chunks)
        for file_path, page_chunks in chunks_by_file.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Page enrichment failed: %s", result)
            errors += 1
        else:
            e, s, err = result
            enriched += e
            skipped += s
            errors += err

    # Count non-enrichable chunks as skipped
    non_enrichable = sum(
        1 for c in chunks if c.chunk_type not in _ENRICHABLE_TYPES
    )
    skipped += non_enrichable

    return enriched, skipped, errors


async def generate_hype_questions(
    chunks: list[Chunk],
    page_contents: dict[str, str],
    gemini_client: GeminiClient,
    *,
    max_concurrent_pages: int = 3,
    num_questions: int = 5,
) -> tuple[int, int, int]:
    """Generate hypothetical questions for all enrichable chunks.

    Groups chunks by page, then for each page generates HyPE questions
    using Gemini. Questions are stored in chunk.hype_questions.

    Args:
        chunks: All chunks (modified in-place with hype_questions).
        page_contents: Mapping of file_path → full raw markdown content.
        gemini_client: Initialized Gemini client.
        max_concurrent_pages: Max pages to process in parallel.
        num_questions: Number of questions to generate per chunk.

    Returns:
        Tuple of (generated_count, skipped_count, error_count).
    """
    chunks_by_file: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.chunk_type in _ENRICHABLE_TYPES:
            chunks_by_file[chunk.metadata.file_path].append(chunk)

    generated = 0
    skipped = 0
    errors = 0

    page_sem = asyncio.Semaphore(max_concurrent_pages)

    async def process_page(file_path: str, page_chunks: list[Chunk]) -> tuple[int, int, int]:
        page_content = page_contents.get(file_path, "")
        if not page_content:
            logger.warning("No page content for %s, skipping HyPE", file_path)
            return 0, len(page_chunks), 0

        page_title = page_chunks[0].metadata.page_title if page_chunks else file_path

        async with page_sem:
            return await _generate_hype_page_chunks(
                page_content=page_content,
                page_title=page_title,
                page_chunks=page_chunks,
                gemini_client=gemini_client,
                num_questions=num_questions,
            )

    tasks = [
        process_page(file_path, page_chunks)
        for file_path, page_chunks in chunks_by_file.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Page HyPE generation failed: %s", result)
            errors += 1
        else:
            g, s, err = result
            generated += g
            skipped += s
            errors += err

    non_enrichable = sum(
        1 for c in chunks if c.chunk_type not in _ENRICHABLE_TYPES
    )
    skipped += non_enrichable

    return generated, skipped, errors


async def _generate_hype_page_chunks(
    page_content: str,
    page_title: str,
    page_chunks: list[Chunk],
    gemini_client: GeminiClient,
    num_questions: int = 5,
) -> tuple[int, int, int]:
    """Generate HyPE questions for all chunks from a single page."""
    generated = 0
    skipped = 0
    errors = 0

    chunk_sem = asyncio.Semaphore(_PAGE_CONCURRENCY)

    async def generate_one(chunk: Chunk) -> str:
        if chunk.hype_questions:
            return "skipped"

        async with chunk_sem:
            try:
                questions = await gemini_client.generate_hype_questions(
                    page_content=page_content,
                    chunk_content=chunk.content,
                    page_title=page_title,
                    num_questions=num_questions,
                )
                chunk.hype_questions = questions
                return "generated"
            except Exception as exc:
                logger.warning(
                    "Failed to generate HyPE for chunk %s: %s",
                    chunk.chunk_id, exc,
                )
                return "error"

    tasks = [generate_one(chunk) for chunk in page_chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            errors += 1
        elif result == "generated":
            generated += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    return generated, skipped, errors


async def _enrich_page_chunks(
    page_content: str,
    page_title: str,
    page_chunks: list[Chunk],
    gemini_client: GeminiClient,
) -> tuple[int, int, int]:
    """Enrich all chunks from a single page.

    Processes chunks with bounded concurrency within the page to benefit
    from Gemini's implicit prompt caching of the repeated page prefix.
    """
    enriched = 0
    skipped = 0
    errors = 0

    chunk_sem = asyncio.Semaphore(_PAGE_CONCURRENCY)

    # Return values: "enriched", "skipped", "error"
    async def enrich_one(chunk: Chunk) -> str:
        """Enrich a single chunk. Returns status string."""
        # Skip if already enriched
        if chunk.contextual_prefix:
            return "skipped"

        async with chunk_sem:
            try:
                prefix = await gemini_client.enrich_chunk(
                    page_content=page_content,
                    chunk_content=chunk.content,
                    page_title=page_title,
                )
                chunk.contextual_prefix = prefix
                return "enriched"
            except Exception as exc:
                logger.warning(
                    "Failed to enrich chunk %s: %s",
                    chunk.chunk_id, exc,
                )
                return "error"

    tasks = [enrich_one(chunk) for chunk in page_chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            errors += 1
        elif result == "enriched":
            enriched += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    return enriched, skipped, errors
