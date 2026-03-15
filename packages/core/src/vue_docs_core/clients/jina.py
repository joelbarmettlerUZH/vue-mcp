"""Async wrapper for Jina AI embedding and reranking APIs."""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from vue_docs_core.config import settings

logger = logging.getLogger(__name__)

JINA_EMBEDDING_URL = "https://api.jina.ai/v1/embeddings"
JINA_RERANKER_URL = "https://api.jina.ai/v1/rerank"

# Task types for jina-embeddings-v4 and later
TASK_RETRIEVAL_PASSAGE = "retrieval.passage"
TASK_RETRIEVAL_QUERY = "retrieval.query"
TASK_TEXT_MATCHING = "text-matching"


@dataclass
class EmbeddingResult:
    embeddings: list[list[float]]
    total_tokens: int


@dataclass
class RerankResult:
    indices: list[int]
    scores: list[float]
    total_tokens: int


class JinaClient:
    """Async client for Jina AI embedding and reranking APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        reranker_model: str | None = None,
        dimensions: int = 1024,
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or settings.jina_api_key
        self.model = model or settings.jina_embedding_model
        self.reranker_model = reranker_model or settings.jina_reranker_model
        self.dimensions = dimensions
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self, url: str, payload: dict
    ) -> dict:
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                body = e.response.text
                if status == 429 or status >= 500:
                    wait = 2**attempt
                    logger.warning(
                        "Jina API %s (attempt %d/%d), retrying in %ds: %s",
                        status, attempt + 1, self.max_retries, wait, body,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error("Jina API error %s: %s", status, body)
                raise
            except httpx.TimeoutException as e:
                last_error = e
                wait = 2**attempt
                logger.warning(
                    "Jina API timeout (attempt %d/%d), retrying in %ds",
                    attempt + 1, self.max_retries, wait,
                )
                await asyncio.sleep(wait)
                continue

        raise RuntimeError(
            f"Jina API request failed after {self.max_retries} attempts"
        ) from last_error

    async def embed(
        self,
        texts: list[str],
        task: str = TASK_RETRIEVAL_PASSAGE,
    ) -> EmbeddingResult:
        """Embed a list of text strings.

        Args:
            texts: Texts to embed.
            task: Jina task type. Use TASK_RETRIEVAL_PASSAGE for documents,
                  TASK_RETRIEVAL_QUERY for queries.

        Returns:
            EmbeddingResult with embeddings and token usage.
        """
        if not texts:
            return EmbeddingResult(embeddings=[], total_tokens=0)

        payload: dict = {
            "model": self.model,
            "dimensions": self.dimensions,
            "normalized": True,
            "input": texts,
        }

        # v4+ uses task parameter with object inputs; v3 uses input_type with plain strings
        if "v3" not in self.model:
            payload["task"] = task
            payload["input"] = [{"text": t} for t in texts]
        else:
            # v3 mapping
            if task == TASK_RETRIEVAL_PASSAGE:
                payload["input_type"] = "document"
            elif task == TASK_RETRIEVAL_QUERY:
                payload["input_type"] = "query"

        data = await self._request_with_retry(JINA_EMBEDDING_URL, payload)

        embeddings = [item["embedding"] for item in data["data"]]
        total_tokens = data.get("usage", {}).get("total_tokens", 0)

        return EmbeddingResult(embeddings=embeddings, total_tokens=total_tokens)

    async def embed_batched(
        self,
        texts: list[str],
        task: str = TASK_RETRIEVAL_PASSAGE,
        batch_size: int = 64,
    ) -> EmbeddingResult:
        """Embed texts in batches to respect API limits.

        Args:
            texts: All texts to embed.
            task: Jina task type.
            batch_size: Max texts per API call.

        Returns:
            Combined EmbeddingResult.
        """
        if not texts:
            return EmbeddingResult(embeddings=[], total_tokens=0)

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = await self.embed(batch, task=task)
            all_embeddings.extend(result.embeddings)
            total_tokens += result.total_tokens

        return EmbeddingResult(
            embeddings=all_embeddings, total_tokens=total_tokens
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> RerankResult:
        """Rerank documents against a query.

        Args:
            query: The search query.
            documents: Documents to rerank.
            top_n: Number of top results to return. Defaults to all.

        Returns:
            RerankResult with reranked indices, scores, and token usage.
        """
        if not documents:
            return RerankResult(indices=[], scores=[], total_tokens=0)

        payload: dict = {
            "model": self.reranker_model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        data = await self._request_with_retry(JINA_RERANKER_URL, payload)

        results = data["results"]
        indices = [r["index"] for r in results]
        scores = [r["relevance_score"] for r in results]
        total_tokens = data.get("usage", {}).get("total_tokens", 0)

        return RerankResult(
            indices=indices, scores=scores, total_tokens=total_tokens
        )
