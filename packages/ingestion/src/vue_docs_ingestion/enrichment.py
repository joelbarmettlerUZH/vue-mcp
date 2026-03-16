"""LLM enrichment orchestration (contextual, HyPE, summaries).

Day 9: Contextual enrichment — for each chunk, generate a short context
prefix (2-3 sentences) using Gemini that situates the chunk within its page.
The prefix is prepended to chunk content before embedding and stored separately
so it can be stripped when presenting results.

Day 10: HyPE (Hypothetical Question Generation) — for each chunk, generate
3-5 hypothetical developer questions that the chunk would answer. These are
embedded and stored as separate Qdrant points with parent_chunk_id references,
bridging the vocabulary gap between developer queries and documentation text.

Day 13: RAPTOR-inspired hierarchical summaries — generate page summaries
(Layer 1) from leaf chunks, folder summaries (Layer 2) from page summaries,
and top-level summaries (Layer 3) from folder summaries. All stored as chunks
in the same Qdrant collection for unified retrieval.
"""

import asyncio
import logging
from collections import defaultdict

from vue_docs_core.clients.gemini import GeminiClient
from vue_docs_core.config import PAGE_CONCURRENCY
from vue_docs_core.models.chunk import Chunk, ChunkMetadata, ChunkType

logger = logging.getLogger(__name__)

# Chunk types that should receive contextual enrichment
_ENRICHABLE_TYPES = {
    ChunkType.SECTION,
    ChunkType.SUBSECTION,
    ChunkType.CODE_BLOCK,
    ChunkType.IMAGE,
}


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
        process_page(file_path, page_chunks) for file_path, page_chunks in chunks_by_file.items()
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
    non_enrichable = sum(1 for c in chunks if c.chunk_type not in _ENRICHABLE_TYPES)
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
        process_page(file_path, page_chunks) for file_path, page_chunks in chunks_by_file.items()
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

    non_enrichable = sum(1 for c in chunks if c.chunk_type not in _ENRICHABLE_TYPES)
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

    chunk_sem = asyncio.Semaphore(PAGE_CONCURRENCY)

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
                    chunk.chunk_id,
                    exc,
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


async def generate_page_summaries(
    chunks: list[Chunk],
    page_contents: dict[str, str],
    gemini_client: GeminiClient,
    *,
    max_concurrent: int = 5,
) -> list[Chunk]:
    """Generate page-level summaries (RAPTOR Layer 1).

    For each unique page in the chunk set, generates a 3-5 sentence summary
    capturing what the page teaches, which APIs it covers, and what a developer
    would learn from reading it.

    Returns:
        List of page summary Chunk objects.
    """
    # Collect metadata per page from the first chunk of each file
    page_meta: dict[str, Chunk] = {}
    page_entities: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        fp = chunk.metadata.file_path
        if fp not in page_meta and chunk.chunk_type in _ENRICHABLE_TYPES:
            page_meta[fp] = chunk
        for entity in chunk.metadata.api_entities:
            page_entities[fp].add(entity)

    sem = asyncio.Semaphore(max_concurrent)
    summaries: list[Chunk] = []
    errors = 0

    async def summarize_page(file_path: str) -> Chunk | None:
        nonlocal errors
        content = page_contents.get(file_path, "")
        if not content:
            logger.warning("No page content for %s, skipping summary", file_path)
            return None

        ref_chunk = page_meta[file_path]
        page_title = ref_chunk.metadata.page_title

        async with sem:
            try:
                summary_text = await gemini_client.generate_summary(
                    content,
                    level="page",
                    title=page_title,
                )
            except Exception as exc:
                logger.warning("Failed to generate page summary for %s: %s", file_path, exc)
                errors += 1
                return None

        # Build chunk ID: strip .md and append #page_summary
        chunk_id = file_path.removesuffix(".md") + "#page_summary"
        return Chunk(
            chunk_id=chunk_id,
            chunk_type=ChunkType.PAGE_SUMMARY,
            content=summary_text,
            metadata=ChunkMetadata(
                file_path=file_path,
                folder_path=ref_chunk.metadata.folder_path,
                page_title=page_title,
                section_title="",
                breadcrumb=page_title,
                global_sort_key=ref_chunk.metadata.global_sort_key,
                api_style=ref_chunk.metadata.api_style,
                api_entities=sorted(page_entities.get(file_path, set())),
            ),
        )

    tasks = [summarize_page(fp) for fp in page_meta]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Page summary task failed: %s", result)
            errors += 1
        elif result is not None:
            summaries.append(result)

    logger.info(
        "Generated %d page summaries (%d errors)",
        len(summaries),
        errors,
    )
    return summaries


async def generate_folder_summaries(
    page_summaries: list[Chunk],
    gemini_client: GeminiClient,
    *,
    max_concurrent: int = 5,
) -> list[Chunk]:
    """Generate folder-level summaries (RAPTOR Layer 2).

    For each unique folder, concatenates all page summaries within it and
    generates a 3-5 sentence summary capturing the section's theme.

    Returns:
        List of folder summary Chunk objects.
    """
    # Group page summaries by folder
    by_folder: dict[str, list[Chunk]] = defaultdict(list)
    for ps in page_summaries:
        by_folder[ps.metadata.folder_path].append(ps)

    sem = asyncio.Semaphore(max_concurrent)
    summaries: list[Chunk] = []
    errors = 0

    async def summarize_folder(folder_path: str, folder_pages: list[Chunk]) -> Chunk | None:
        nonlocal errors
        # Sort by sort key for logical ordering
        folder_pages.sort(key=lambda c: c.metadata.global_sort_key)

        # Concatenate page summaries with titles
        parts = []
        for ps in folder_pages:
            parts.append(f"**{ps.metadata.page_title}:** {ps.content}")
        combined = "\n\n".join(parts)

        # Derive folder title from folder path
        folder_title = folder_path.replace("/", " > ").title()

        async with sem:
            try:
                summary_text = await gemini_client.generate_summary(
                    combined,
                    level="folder",
                    title=folder_title,
                )
            except Exception as exc:
                logger.warning("Failed to generate folder summary for %s: %s", folder_path, exc)
                errors += 1
                return None

        # Aggregate entities from all pages in folder
        all_entities: set[str] = set()
        for ps in folder_pages:
            all_entities.update(ps.metadata.api_entities)

        # Use first page's sort key prefix for folder-level ordering
        sort_key = folder_pages[0].metadata.global_sort_key if folder_pages else folder_path

        chunk_id = f"{folder_path}#folder_summary"
        return Chunk(
            chunk_id=chunk_id,
            chunk_type=ChunkType.FOLDER_SUMMARY,
            content=summary_text,
            metadata=ChunkMetadata(
                file_path="",
                folder_path=folder_path,
                page_title=folder_title,
                section_title="",
                breadcrumb=folder_title,
                global_sort_key=sort_key,
                api_entities=sorted(all_entities),
            ),
        )

    tasks = [summarize_folder(fp, pages) for fp, pages in by_folder.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Folder summary task failed: %s", result)
            errors += 1
        elif result is not None:
            summaries.append(result)

    logger.info(
        "Generated %d folder summaries (%d errors)",
        len(summaries),
        errors,
    )
    return summaries


async def generate_top_summaries(
    folder_summaries: list[Chunk],
    gemini_client: GeminiClient,
) -> list[Chunk]:
    """Generate top-level summaries (RAPTOR Layer 3).

    For each top-level documentation area (guide, api, tutorial, examples),
    generates a 2-3 sentence summary from the folder summaries.

    Returns:
        List of top-level summary Chunk objects.
    """
    # Group folder summaries by top-level path segment
    by_top: dict[str, list[Chunk]] = defaultdict(list)
    for fs in folder_summaries:
        top = (
            fs.metadata.folder_path.split("/")[0]
            if "/" in fs.metadata.folder_path
            else fs.metadata.folder_path
        )
        by_top[top].append(fs)

    summaries: list[Chunk] = []
    errors = 0

    for top_path, top_folders in by_top.items():
        top_folders.sort(key=lambda c: c.metadata.global_sort_key)

        parts = []
        for fs in top_folders:
            parts.append(f"**{fs.metadata.page_title}:** {fs.content}")
        combined = "\n\n".join(parts)

        top_title = top_path.replace("/", " > ").title()

        try:
            summary_text = await gemini_client.generate_summary(
                combined,
                level="top",
                title=top_title,
            )
        except Exception as exc:
            logger.warning("Failed to generate top summary for %s: %s", top_path, exc)
            errors += 1
            continue

        # Aggregate entities
        all_entities: set[str] = set()
        for fs in top_folders:
            all_entities.update(fs.metadata.api_entities)

        sort_key = top_folders[0].metadata.global_sort_key if top_folders else top_path

        chunk_id = f"{top_path}#top_summary"
        summaries.append(
            Chunk(
                chunk_id=chunk_id,
                chunk_type=ChunkType.TOP_SUMMARY,
                content=summary_text,
                metadata=ChunkMetadata(
                    file_path="",
                    folder_path=top_path,
                    page_title=top_title,
                    section_title="",
                    breadcrumb=top_title,
                    global_sort_key=sort_key,
                    api_entities=sorted(all_entities),
                ),
            )
        )

    logger.info(
        "Generated %d top summaries (%d errors)",
        len(summaries),
        errors,
    )
    return summaries


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

    chunk_sem = asyncio.Semaphore(PAGE_CONCURRENCY)

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
                    chunk.chunk_id,
                    exc,
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
