"""Gemini client wrapper using official google-genai SDK with offline mock engine & token simulator."""

from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator, Iterator, Optional

from core.humanizer.engine.deep import DeepParaphraser
from core.humanizer.engine.guardrails import replace_banned_buzzwords, sanitize_and_verify_grammar
from core.humanizer.engine.prompt import estimate_prompt_tokens
from core.humanizer.models import UsageMetadata

import logging
from core.logger import get_logger

logger = get_logger("humanizer_generator")

try:
    from google import genai
    from google.genai import types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    GOOGLE_GENAI_AVAILABLE = False


class GeminiGenerator:
    """Handles communication with Gemini Flash Lite endpoints or deterministic offline simulation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite",
        fallback_model: str = "gemini-2.0-flash-lite",
        mock_mode: bool = False,
    ) -> None:
        self.model = model
        self.fallback_model = fallback_model
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        self.api_key = resolved_key

        # Determine if offline mock mode should be active
        self.mock_mode = mock_mode or not resolved_key
        self._paraphraser = DeepParaphraser()

        self._client: Optional[genai.Client] = None
        if not self.mock_mode and GOOGLE_GENAI_AVAILABLE and genai:
            try:
                self._client = genai.Client(api_key=resolved_key)
            except Exception as e:
                logger.warning(f"Could not initialize google-genai Client: {e}. Will use direct REST fallback.")
                self._client = None

    def _offline_transform(self, prompt: str, system_instruction: str) -> str:
        """Perform genuine rule-based transformation offline when no API key is present."""
        # Detect tone from system instruction
        tone = "neutral"
        if "conversational" in system_instruction.lower():
            tone = "casual"
        elif "analytical" in system_instruction.lower() or "scholarly" in system_instruction.lower():
            tone = "academic"
        elif "executive" in system_instruction.lower() or "business" in system_instruction.lower():
            tone = "professional"

        # Detect reading level from system instruction
        reading_level = "general"
        if "middle school" in system_instruction.lower():
            reading_level = "middle_school"
        elif "college" in system_instruction.lower():
            reading_level = "college"
        elif "high school" in system_instruction.lower():
            reading_level = "high_school"

        transformed, _ = self._paraphraser.transform(prompt, tone=tone, reading_level=reading_level)
        return transformed

    def generate_sync(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
    ) -> tuple[str, UsageMetadata]:
        """Execute synchronous text generation."""
        if self.mock_mode or not self.api_key:
            output_text = self._offline_transform(prompt, system_instruction)
            prompt_tokens = estimate_prompt_tokens(prompt)
            system_tokens = estimate_prompt_tokens(system_instruction)
            completion_tokens = estimate_prompt_tokens(output_text)
            usage = UsageMetadata(
                prompt_tokens=prompt_tokens + system_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + system_tokens + completion_tokens,
                prompt_overhead_tokens=system_tokens,
            )
            return output_text, usage

        # Candidate models to try in order
        candidate_models = [self.model, self.fallback_model, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        seen = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        for mod in models_to_try:
            try:
                return self._call_gemini_sync(mod, prompt, system_instruction, temperature)
            except Exception as e:
                logger.debug(f"Gemini generation failed for model {mod}: {e}")
                continue

        # If all live endpoints fail, fall back to offline transform
        logger.warning("All Gemini endpoints failed; falling back to offline paraphraser.")
        output_text = self._offline_transform(prompt, system_instruction)
        prompt_tokens = estimate_prompt_tokens(prompt)
        system_tokens = estimate_prompt_tokens(system_instruction)
        completion_tokens = estimate_prompt_tokens(output_text)
        usage = UsageMetadata(
            prompt_tokens=prompt_tokens + system_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + system_tokens + completion_tokens,
            prompt_overhead_tokens=system_tokens,
        )
        return output_text, usage

    def _call_gemini_sync(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str,
        temperature: float,
    ) -> tuple[str, UsageMetadata]:
        if self._client is not None:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                output_text = response.text or ""
                meta = response.usage_metadata
                p_tokens = meta.prompt_token_count if meta else estimate_prompt_tokens(prompt + system_instruction)
                c_tokens = meta.candidates_token_count if meta else estimate_prompt_tokens(output_text)
                raw_prompt_tokens = estimate_prompt_tokens(prompt)
                overhead = max(0, p_tokens - raw_prompt_tokens)

                usage = UsageMetadata(
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    total_tokens=p_tokens + c_tokens,
                    prompt_overhead_tokens=overhead,
                )
                return output_text, usage
            except Exception as sdk_err:
                logger.debug(f"SDK call failed for {model_name}: {sdk_err}. Trying REST fallback...")

        # Direct REST API fallback via requests
        if getattr(self, "api_key", None):
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {"temperature": temperature},
            }
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                output_text = ""
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    output_text = "".join(p.get("text", "") for p in parts)
                usage_meta = data.get("usageMetadata", {})
                p_tokens = usage_meta.get("promptTokenCount", estimate_prompt_tokens(prompt + system_instruction))
                c_tokens = usage_meta.get("candidatesTokenCount", estimate_prompt_tokens(output_text))
                return output_text, UsageMetadata(
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    total_tokens=p_tokens + c_tokens,
                    prompt_overhead_tokens=max(0, p_tokens - estimate_prompt_tokens(prompt)),
                )
            raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text}")

        raise RuntimeError("No client or API key available for Gemini generation.")

    async def generate_async(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
    ) -> tuple[str, UsageMetadata]:
        """Execute asynchronous text generation."""
        if self.mock_mode or not self.api_key:
            loop = asyncio.get_running_loop()
            output_text = await loop.run_in_executor(None, self._offline_transform, prompt, system_instruction)
            prompt_tokens = estimate_prompt_tokens(prompt)
            system_tokens = estimate_prompt_tokens(system_instruction)
            completion_tokens = estimate_prompt_tokens(output_text)
            usage = UsageMetadata(
                prompt_tokens=prompt_tokens + system_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + system_tokens + completion_tokens,
                prompt_overhead_tokens=system_tokens,
            )
            return output_text, usage

        candidate_models = [self.model, self.fallback_model, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        seen = set()
        models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

        loop = asyncio.get_running_loop()
        for mod in models_to_try:
            try:
                if self._client is not None:
                    return await self._call_gemini_async(mod, prompt, system_instruction, temperature)
                else:
                    return await loop.run_in_executor(None, self._call_gemini_sync, mod, prompt, system_instruction, temperature)
            except Exception as e:
                logger.debug(f"Async Gemini generation failed for model {mod}: {e}")
                continue

        logger.warning("All async Gemini endpoints failed; falling back to offline paraphraser.")
        output_text = await loop.run_in_executor(None, self._offline_transform, prompt, system_instruction)
        prompt_tokens = estimate_prompt_tokens(prompt)
        system_tokens = estimate_prompt_tokens(system_instruction)
        completion_tokens = estimate_prompt_tokens(output_text)
        return output_text, UsageMetadata(
            prompt_tokens=prompt_tokens + system_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + system_tokens + completion_tokens,
            prompt_overhead_tokens=system_tokens,
        )

    async def _call_gemini_async(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str,
        temperature: float,
    ) -> tuple[str, UsageMetadata]:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )
        response = await self._client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
        output_text = response.text or ""
        meta = response.usage_metadata
        p_tokens = meta.prompt_token_count if meta else estimate_prompt_tokens(prompt + system_instruction)
        c_tokens = meta.candidates_token_count if meta else estimate_prompt_tokens(output_text)
        raw_prompt_tokens = estimate_prompt_tokens(prompt)
        overhead = max(0, p_tokens - raw_prompt_tokens)

        usage = UsageMetadata(
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=p_tokens + c_tokens,
            prompt_overhead_tokens=overhead,
        )
        return output_text, usage

    def generate_stream_sync(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
    ) -> Iterator[str]:
        """Stream chunks synchronously with automatic fallback model recovery."""
        if self.mock_mode or not self.api_key or self._client is None:
            full_text, _ = self.generate_sync(prompt, system_instruction, temperature)
            words = full_text.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i : i + 3])
                if i + 3 < len(words):
                    chunk += " "
                yield chunk
            return

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        has_yielded = False
        try:
            stream = self._client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=config,
            )
            for chunk in stream:
                if chunk.text:
                    has_yielded = True
                    yield chunk.text
        except Exception:
            if not has_yielded and self.fallback_model and self.fallback_model != self.model:
                fallback_stream = self._client.models.generate_content_stream(
                    model=self.fallback_model,
                    contents=prompt,
                    config=config,
                )
                for chunk in fallback_stream:
                    if chunk.text:
                        yield chunk.text
            else:
                full_text, _ = self.generate_sync(prompt, system_instruction, temperature)
                for chunk in [full_text]:
                    yield chunk

    async def generate_stream_async(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream chunks asynchronously (for SSE / FastAPI endpoints) with model fallback."""
        if self.mock_mode or not self.api_key or self._client is None:
            full_text, _ = await self.generate_async(prompt, system_instruction, temperature)
            words = full_text.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i : i + 3])
                if i + 3 < len(words):
                    chunk += " "
                await asyncio.sleep(0.01)
                yield chunk
            return

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        has_yielded = False
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    has_yielded = True
                    yield chunk.text
        except Exception:
            if not has_yielded and self.fallback_model and self.fallback_model != self.model:
                fallback_stream = await self._client.aio.models.generate_content_stream(
                    model=self.fallback_model,
                    contents=prompt,
                    config=config,
                )
                async for chunk in fallback_stream:
                    if chunk.text:
                        yield chunk.text
            else:
                full_text, _ = await self.generate_async(prompt, system_instruction, temperature)
                yield full_text
