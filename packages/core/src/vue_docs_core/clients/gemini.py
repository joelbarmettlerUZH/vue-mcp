"""Async wrapper for Gemini query transformation and enrichment."""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from vue_docs_core.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass
class GeminiResponse:
    text: str
    input_tokens: int
    output_tokens: int


class GeminiClient:
    """Async client for Google Gemini API.

    Uses the REST API directly (no SDK dependency) for contextual enrichment,
    HyPE question generation, query transformation, and summary generation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_flash_model
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(self, url: str, payload: dict) -> dict:
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
                        "Gemini API %s (attempt %d/%d), retrying in %ds: %s",
                        status, attempt + 1, self.max_retries, wait, body,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error("Gemini API error %s: %s", status, body)
                raise
            except httpx.TimeoutException as e:
                last_error = e
                wait = 2**attempt
                logger.warning(
                    "Gemini API timeout (attempt %d/%d), retrying in %ds",
                    attempt + 1, self.max_retries, wait,
                )
                await asyncio.sleep(wait)
                continue

        raise RuntimeError(
            f"Gemini API request failed after {self.max_retries} attempts"
        ) from last_error

    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: str = "",
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        model: str | None = None,
    ) -> GeminiResponse:
        """Send a prompt to Gemini and return the response text.

        Args:
            prompt: The user prompt.
            system_instruction: Optional system instruction.
            temperature: Sampling temperature (0.0 = deterministic).
            max_output_tokens: Max tokens in response.
            model: Override model for this call.

        Returns:
            GeminiResponse with text and token usage.
        """
        model_name = model or self.model
        url = f"{GEMINI_API_BASE}/{model_name}:generateContent?key={self.api_key}"

        payload: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                # Disable thinking for enrichment tasks — thinking tokens
                # consume the maxOutputTokens budget, leaving truncated output.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data = await self._request_with_retry(url, payload)

        # Extract text from response
        text = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text = parts[0].get("text", "")

        # Extract token usage
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return GeminiResponse(
            text=text.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_cached(
        self,
        cached_content: str,
        per_chunk_prompt: str,
        *,
        system_instruction: str = "",
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        model: str | None = None,
    ) -> GeminiResponse:
        """Generate with a large cached prefix + small varying suffix.

        Gemini's implicit prompt caching automatically caches repeated prefixes.
        We structure the prompt so the page content is the stable prefix and the
        chunk-specific part varies.

        Args:
            cached_content: The large, repeated content (e.g., full page text).
            per_chunk_prompt: The varying part (e.g., specific chunk to enrich).
            system_instruction: Optional system instruction.
            temperature: Sampling temperature.
            max_output_tokens: Max tokens in response.
            model: Override model for this call.

        Returns:
            GeminiResponse with text and token usage.
        """
        # Gemini automatically caches repeated prefixes in multi-turn or
        # repeated requests. We concatenate but keep the structure clear.
        full_prompt = f"{cached_content}\n\n---\n\n{per_chunk_prompt}"
        return await self.generate(
            full_prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            model=model,
        )

    async def generate_hype_questions(
        self,
        page_content: str,
        chunk_content: str,
        page_title: str,
        num_questions: int = 5,
    ) -> list[str]:
        """Generate hypothetical developer questions that a chunk would answer.

        Uses the full page as context to produce questions that bridge the
        vocabulary gap between how developers ask questions and how the
        documentation explains concepts.

        Args:
            page_content: The full markdown content of the page.
            chunk_content: The specific chunk text to generate questions for.
            page_title: The page title for context.
            num_questions: Number of questions to generate (3-5).

        Returns:
            A list of hypothetical developer questions.
        """
        system_instruction = (
            "You are a Vue.js documentation expert. Your task is to generate "
            f"{num_questions} hypothetical developer questions that the given "
            "documentation chunk would answer. The questions should:\n"
            "- Sound like real developer questions (natural, conversational)\n"
            "- Cover different phrasings and angles for the same concept\n"
            "- Include questions about common problems or debugging scenarios\n"
            "- Use terminology developers would actually search for\n"
            "- Range from beginner to intermediate level\n\n"
            "Output ONLY the questions, one per line, no numbering or bullets."
        )

        per_chunk_prompt = (
            f"Given the following chunk from the page \"{page_title}\", "
            f"generate {num_questions} hypothetical developer questions:\n\n"
            f"CHUNK:\n{chunk_content}"
        )

        result = await self.generate_cached(
            cached_content=f"PAGE CONTENT:\n{page_content}",
            per_chunk_prompt=per_chunk_prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=300,
        )

        # Parse response: one question per line, filter empty lines
        questions = [
            q.strip() for q in result.text.split("\n") if q.strip()
        ]
        return questions[:num_questions]

    async def enrich_chunk(
        self,
        page_content: str,
        chunk_content: str,
        page_title: str,
    ) -> str:
        """Generate a contextual prefix for a chunk.

        Uses the full page as context to produce 2-3 sentences that situate
        the chunk within the page's topic, mentioning relevant Vue concepts
        and API names.

        Args:
            page_content: The full markdown content of the page.
            chunk_content: The specific chunk text to enrich.
            page_title: The page title for context.

        Returns:
            A 2-3 sentence contextual prefix string.
        """
        system_instruction = (
            "You are a technical documentation expert. Your task is to generate "
            "a brief contextual summary (2-3 sentences) that situates a specific "
            "documentation chunk within its parent page. The summary should:\n"
            "- Mention the Vue.js concept or feature being discussed\n"
            "- Reference any API names (e.g., ref, computed, v-model) relevant to the chunk\n"
            "- Explain how this chunk relates to the page's overall topic\n"
            "- Be concise and factual — no opinions or filler\n\n"
            "Output ONLY the contextual summary, nothing else."
        )

        per_chunk_prompt = (
            f"Given the following chunk from the page \"{page_title}\", "
            f"write a contextual summary:\n\n"
            f"CHUNK:\n{chunk_content}"
        )

        result = await self.generate_cached(
            cached_content=f"PAGE CONTENT:\n{page_content}",
            per_chunk_prompt=per_chunk_prompt,
            system_instruction=system_instruction,
            temperature=0.0,
            max_output_tokens=200,
        )
        return result.text
