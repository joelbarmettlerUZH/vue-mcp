"""Async wrapper for Gemini using the official google-genai SDK."""

import logging
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from vue_docs_core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GeminiResponse:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class GeminiFunctionCallResponse:
    """Response from a Gemini function calling request."""

    function_name: str
    arguments: dict[str, Any]
    input_tokens: int
    output_tokens: int


class GeminiClient:
    """Async client for Google Gemini API via the official google-genai SDK."""

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
        self._client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )

    async def close(self) -> None:
        """No-op for SDK client (no persistent connection to close)."""

    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: str = "",
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        model: str | None = None,
    ) -> GeminiResponse:
        """Send a prompt to Gemini and return the response text."""
        model_name = model or self.model

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        text = response.text or ""
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count if usage else 0
        output_tokens = usage.candidates_token_count if usage else 0

        return GeminiResponse(
            text=text.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_with_tool(
        self,
        prompt: str,
        *,
        function_name: str,
        function_description: str,
        parameters_schema: dict,
        system_instruction: str = "",
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        model: str | None = None,
    ) -> GeminiFunctionCallResponse:
        """Send a prompt with forced function calling for structured output.

        Defines a single tool and forces Gemini to call it, ensuring the
        response conforms to the provided JSON schema.
        """
        model_name = model or self.model

        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=function_name,
                    description=function_description,
                    parameters=parameters_schema,
                )
            ]
        )

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=[tool],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[function_name],
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        # Extract function call from response
        arguments: dict = {}
        fn_name = function_name
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    fn_name = part.function_call.name or function_name
                    arguments = dict(part.function_call.args) if part.function_call.args else {}
                    break

        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count if usage else 0
        output_tokens = usage.candidates_token_count if usage else 0

        return GeminiFunctionCallResponse(
            function_name=fn_name,
            arguments=arguments,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_cached_with_tool(
        self,
        cached_content: str,
        per_chunk_prompt: str,
        *,
        function_name: str,
        function_description: str,
        parameters_schema: dict,
        system_instruction: str = "",
        temperature: float = 0.0,
        max_output_tokens: int = 256,
        model: str | None = None,
    ) -> GeminiFunctionCallResponse:
        """Generate with cached prefix + function calling for structured output."""
        full_prompt = f"{cached_content}\n\n---\n\n{per_chunk_prompt}"
        return await self.generate_with_tool(
            full_prompt,
            function_name=function_name,
            function_description=function_description,
            parameters_schema=parameters_schema,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            model=model,
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
        """
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

        Uses forced function calling to get a structured list of questions,
        avoiding brittle newline-based parsing.
        """
        system_instruction = (
            "You are a Vue.js documentation expert. Your task is to generate "
            f"{num_questions} hypothetical developer questions that the given "
            "documentation chunk would answer. The questions should:\n"
            "- Sound like real developer questions (natural, conversational)\n"
            "- Cover different phrasings and angles for the same concept\n"
            "- Include questions about common problems or debugging scenarios\n"
            "- Use terminology developers would actually search for\n"
            "- Range from beginner to intermediate level"
        )

        per_chunk_prompt = (
            f'Given the following chunk from the page "{page_title}", '
            f"generate {num_questions} hypothetical developer questions:\n\n"
            f"CHUNK:\n{chunk_content}"
        )

        result = await self.generate_cached_with_tool(
            cached_content=f"PAGE CONTENT:\n{page_content}",
            per_chunk_prompt=per_chunk_prompt,
            function_name="save_questions",
            function_description="Save the generated hypothetical developer questions.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "List of hypothetical developer questions.",
                        "items": {"type": "string"},
                    }
                },
                "required": ["questions"],
            },
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=300,
        )

        questions = result.arguments.get("questions", [])
        return [q for q in questions if isinstance(q, str) and q.strip()][:num_questions]

    async def generate_summary(
        self,
        content: str,
        *,
        level: str = "page",
        title: str = "",
    ) -> str:
        """Generate a summary for a page, folder, or top-level section."""
        level_instructions = {
            "page": (
                "Generate a 3-5 sentence summary of this Vue.js documentation page. "
                "The summary should capture what the page teaches, which APIs it covers, "
                "and what a developer would learn from reading it. Be specific about "
                "Vue concepts and API names mentioned."
            ),
            "folder": (
                "Generate a 3-5 sentence summary of this Vue.js documentation section. "
                "You are given summaries of all pages within this section. "
                "Capture the overall theme, the key concepts taught, and the progression "
                "of topics. Mention the most important APIs and patterns covered."
            ),
            "top": (
                "Generate a 2-3 sentence summary of this top-level Vue.js documentation area. "
                "You are given summaries of all sub-sections. Capture the overall purpose "
                "and scope of this documentation area at a high level."
            ),
        }

        system_instruction = (
            "You are a Vue.js documentation expert. "
            + level_instructions.get(level, level_instructions["page"])
            + "\n\nOutput ONLY the summary, nothing else."
        )

        title_prefix = f'Summary for "{title}":\n\n' if title else ""
        prompt = f"{title_prefix}CONTENT:\n{content}"

        max_tokens = 200 if level == "top" else 300

        result = await self.generate(
            prompt,
            system_instruction=system_instruction,
            temperature=0.0,
            max_output_tokens=max_tokens,
        )
        return result.text

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
            f'Given the following chunk from the page "{page_title}", '
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
