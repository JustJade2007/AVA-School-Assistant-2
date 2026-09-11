"""Core Humanizer client interface providing sync, async, and streaming methods."""

from __future__ import annotations

import os
import re
from typing import AsyncIterator, Iterator, Literal, Optional

from core.humanizer.engine.generator import GeminiGenerator
from core.humanizer.engine.guardrails import (
    audit_vocabulary,
    replace_banned_buzzwords,
    sanitize_and_verify_grammar,
)
from core.humanizer.engine.prompt import get_budget_prompt, get_deep_prompt
from core.humanizer.engine.readability import calculate_readability
from core.humanizer.engine.thesaurus import deflate_descriptors
from core.humanizer.models import HumanizeResult, ModePreset, ReadingLevelPreset, TonePreset
from core.humanizer.parser import BlockType, InlineMasker, MarkdownDocument, MaskState


class StreamChunkAccumulator:
    """Accumulates and safely emits streaming chunks without leaking placeholders or buzzwords."""

    # Words that can begin a multi-word banned AI cliché or transition phrase
    BUZZWORD_STARTERS = {
        "serves", "serve",
        "it",
        "shed", "sheds",
        "paradigm",
        "game",
        "by",
        "delve", "delves", "delved", "delving",
        "tapestry", "tapestries",
        "in",
        "to",
        "testament", "testaments",
        "symphony", "symphonies",
        "plethora",
        "myriad",
        "realm", "realms",
        "interplay",
        "beacon", "beacons",
    }

    # All internal vocabulary words that can appear inside multi-word banned phrases
    BUZZWORD_INTERNAL_WORDS = {
        "as", "a", "testament", "testaments", "to", "beacon", "beacons", "of",
        "reminder", "is", "worth", "noting", "that", "important", "remember",
        "light", "on", "shift", "changer", "and", "large", "into", "summary",
        "conclusion", "sum", "up",
    }

    PLACEHOLDER_REGEX = re.compile(r"⟦\s*(?:CODE_FENCE|CODE_BLOCK|TABLE_BLOCK|INLINE_CODE|URL|MATH)_(\d+)\s*⟧")
    SENTENCE_BOUNDARY_REGEX = re.compile(r"([.!?]\s+|\n+)")

    def __init__(
        self,
        fences: Optional[list[str]] = None,
        mask_state: Optional[MaskState] = None,
    ) -> None:
        self.fences = fences or []
        self.mask_state = mask_state
        self.buffer = ""

    def _resolve_placeholder(self, raw_match: str, idx: int) -> str:
        if self.mask_state and raw_match in self.mask_state.token_map:
            return self.mask_state.token_map[raw_match]
        if idx < len(self.fences):
            return self.fences[idx]
        return raw_match

    def feed(self, chunk: str) -> Iterator[str]:
        """Feed an incoming chunk and yield any safely sanitized and restored output."""
        if not chunk:
            return

        self.buffer += chunk

        while True:
            # 1. Check for complete code fence or token placeholder in buffer
            placeholder_match = self.PLACEHOLDER_REGEX.search(self.buffer)
            if placeholder_match:
                prefix = self.buffer[:placeholder_match.start()]
                if prefix:
                    deflated_prefix, _ = deflate_descriptors(prefix)
                    clean_prefix, _ = replace_banned_buzzwords(deflated_prefix)
                    if clean_prefix:
                        yield clean_prefix

                idx = int(placeholder_match.group(1))
                restored = self._resolve_placeholder(placeholder_match.group(0), idx)
                yield restored

                self.buffer = self.buffer[placeholder_match.end():]
                continue

            # 2. Check for partial placeholder at end of buffer
            partial_idx = self.buffer.rfind("⟦")
            candidate_text = self.buffer
            reserved_tail = ""
            if partial_idx != -1:
                tail = self.buffer[partial_idx:]
                if "\n" not in tail and len(tail) < 50 and "⟧" not in tail:
                    candidate_text = self.buffer[:partial_idx]
                    reserved_tail = tail

            if not candidate_text:
                break

            # 3. Check for safe prose emission in candidate_text
            # Look for sentence boundary
            sentence_matches = list(self.SENTENCE_BOUNDARY_REGEX.finditer(candidate_text))
            if sentence_matches:
                last_match = sentence_matches[-1]
                safe_slice = candidate_text[:last_match.end()]
                remainder = candidate_text[last_match.end():]

                clean_slice, _ = replace_banned_buzzwords(safe_slice)
                if clean_slice:
                    yield clean_slice

                self.buffer = remainder + reserved_tail
                continue

            # Check word boundaries for safe split points
            emitted = False
            space_indices = [m.start() for m in re.finditer(r"\s+", candidate_text)]
            for s_idx in reversed(space_indices):
                pre_slice = candidate_text[:s_idx]
                post_slice = candidate_text[s_idx:]

                words = re.findall(r"[a-zA-Z]+", pre_slice)
                if not words:
                    continue
                last_word = words[-1].lower()

                # If last word could begin or continue a multi-word phrase, hold in buffer
                if last_word in self.BUZZWORD_STARTERS or last_word in self.BUZZWORD_INTERNAL_WORDS:
                    continue

                clean_slice, _ = replace_banned_buzzwords(pre_slice)
                if clean_slice:
                    yield clean_slice

                self.buffer = post_slice + reserved_tail
                emitted = True
                break

            if not emitted:
                break

    def flush(self) -> Iterator[str]:
        """Flush any remaining text in buffer on stream completion."""
        if not self.buffer:
            return

        while True:
            m = self.PLACEHOLDER_REGEX.search(self.buffer)
            if not m:
                break
            prefix = self.buffer[:m.start()]
            if prefix:
                deflated_prefix, _ = deflate_descriptors(prefix)
                clean_prefix, _ = replace_banned_buzzwords(deflated_prefix)
                if clean_prefix:
                    yield clean_prefix

            idx = int(m.group(1))
            restored = self._resolve_placeholder(m.group(0), idx)
            yield restored

            self.buffer = self.buffer[m.end():]

        if self.buffer:
            deflated_tail, _ = deflate_descriptors(self.buffer)
            clean_tail, _ = replace_banned_buzzwords(deflated_tail)
            if clean_tail:
                yield clean_tail
            self.buffer = ""


class Humanizer:
    """Core text humanizer client conforming to PROJECT.md § Interface Contracts."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash-lite",
        fallback_model: str = "gemini-2.0-flash-lite",
        mock_mode: bool = False,
    ) -> None:
        """Initialize the Humanizer client.

        Args:
            api_key: Optional Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Primary Flash Lite model. Defaults to 'gemini-2.5-flash-lite'.
            fallback_model: Secondary fallback model. Defaults to 'gemini-2.0-flash-lite'.
            mock_mode: When True, runs deterministic offline engine without network calls.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.fallback_model = fallback_model
        self.generator = GeminiGenerator(
            api_key=api_key,
            model=model,
            fallback_model=fallback_model,
            mock_mode=mock_mode,
        )
        self.mock_mode = self.generator.mock_mode

    def _prepare_prompt(
        self,
        mode: Literal["budget", "deep"],
        tone: Literal["neutral", "casual", "academic", "professional"],
        reading_level: Literal["middle_school", "high_school", "college", "general"],
    ) -> str:
        if mode == "deep":
            return get_deep_prompt(tone=tone, reading_level=reading_level)
        return get_budget_prompt(tone=tone, reading_level=reading_level)

    def _protect_code_blocks(self, text: str) -> tuple[str, list[str]]:
        """Safeguard fenced code blocks from modification."""
        fences: list[str] = []

        def _repl(m: re.Match[str]) -> str:
            fences.append(m.group(0))
            return f"⟦CODE_FENCE_{len(fences)-1}⟧"

        protected = re.sub(r"```[\s\S]*?```", _repl, text)
        return protected, fences

    def _restore_code_blocks(self, text: str, fences: list[str]) -> str:
        """Restore protected code blocks bit-for-bit."""
        restored = text
        for idx, fence in enumerate(fences):
            target = f"⟦CODE_FENCE_{idx}⟧"
            if target in restored:
                restored = restored.replace(target, fence)
            else:
                pattern = rf"⟦\s*CODE_FENCE_{idx}\s*⟧"
                restored = re.sub(pattern, lambda _: fence, restored)
        return restored

    def _post_process(
        self,
        raw_output: str,
        original_text: str,
        mode: str,
        tone: str,
        reading_level: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        fences: list[str],
    ) -> HumanizeResult:
        # 1. Thesaurus de-flater (strip melodramatic descriptors & purple prose)
        deflated_text, deflated_phrases = deflate_descriptors(raw_output)

        # 2. 0-tolerance banned AI buzzwords audit and replacement on prose
        # Fenced code block placeholders ⟦CODE_FENCE_X⟧ remain masked and untouched
        clean_text, buzzwords_replaced = replace_banned_buzzwords(deflated_text)

        # Capture buzzwords eliminated from original_text prose (excluding code blocks)
        original_prose = re.sub(r"```[\s\S]*?```", " ", original_text) if fences else original_text
        original_buzzwords = audit_vocabulary(original_prose)
        all_buzzwords = list(buzzwords_replaced)
        for dp in deflated_phrases:
            if dp not in all_buzzwords:
                all_buzzwords.append(dp)
        for bw in original_buzzwords:
            if not re.search(r"\b" + re.escape(bw) + r"\b", clean_text, re.IGNORECASE):
                if bw not in all_buzzwords:
                    all_buzzwords.append(bw)

        # 2. Automated syntax & grammar verification on prose only
        grammar_res = sanitize_and_verify_grammar(clean_text)
        repaired_prose = grammar_res.repaired_text

        # 3. RESTORE CODE BLOCKS AS THE ABSOLUTE LAST STEP OF TEXT TRANSFORMATION
        # Code comments, string literals, and syntax formatting inside fenced blocks
        # are NEVER altered by guardrails or grammar sanitizers
        final_text = self._restore_code_blocks(repaired_prose, fences)

        # 4. Readability score calculation (calculate_readability strips code blocks internally)
        readability = calculate_readability(final_text)

        return HumanizeResult(
            text=final_text,
            original_text=original_text,
            mode=mode,
            tone=tone,
            reading_level=reading_level,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            buzzwords_replaced=all_buzzwords,
            flesch_reading_ease=readability["flesch_reading_ease"],
            flesch_kincaid_grade=readability["flesch_kincaid_grade"],
            grammar_repaired=not grammar_res.is_valid,
            is_offline=self.mock_mode,
            engine="gemini-flash-lite (offline)" if self.mock_mode else self.model,
            api_tokens_used=0 if self.mock_mode else total_tokens,
        )

    def humanize(
        self,
        text: str,
        mode: Literal["budget", "deep"] = "budget",
        tone: Literal["neutral", "casual", "academic", "professional"] = "neutral",
        reading_level: Literal["middle_school", "high_school", "college", "general"] = "general",
        preserve_markdown: bool = True,
    ) -> HumanizeResult:
        """Synchronously humanize text with quality guardrails and readability evaluation."""
        if not text or not text.strip():
            return HumanizeResult(
                text=text,
                original_text=text,
                mode=mode,
                tone=tone,
                reading_level=reading_level,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                buzzwords_replaced=[],
                flesch_reading_ease=100.0,
                flesch_kincaid_grade=0.0,
                grammar_repaired=False,
                is_offline=self.mock_mode,
                engine="gemini-flash-lite (offline)" if self.mock_mode else self.model,
                api_tokens_used=0,
            )

        if preserve_markdown:
            doc = MarkdownDocument(text)
            chunks = doc.extract_chunks(max_chunk_chars=1500)
            humanized_chunks: list[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            all_buzzwords: list[str] = []
            grammar_repaired = False

            system_instruction = self._prepare_prompt(mode, tone, reading_level)

            for chunk in chunks:
                if not chunk.is_humanizable:
                    humanized_chunks.append(chunk.raw_text)
                    continue

                masked_content, mask_state = InlineMasker.mask(chunk.content)
                raw_output, usage = self.generator.generate_sync(
                    masked_content, system_instruction
                )
                prompt_tokens += usage.prompt_tokens
                completion_tokens += usage.completion_tokens
                total_tokens += usage.total_tokens

                clean_text, buzzwords = replace_banned_buzzwords(raw_output)
                all_buzzwords.extend(buzzwords)

                gram_res = sanitize_and_verify_grammar(clean_text)
                if not gram_res.is_valid:
                    grammar_repaired = True

                unmasked = InlineMasker.unmask(gram_res.repaired_text, mask_state)
                humanized_chunks.append(unmasked)

            reconstructed_text = doc.reconstruct(humanized_chunks)

            original_buzzwords = audit_vocabulary(text)
            for bw in original_buzzwords:
                if not re.search(r"\b" + re.escape(bw) + r"\b", reconstructed_text, re.IGNORECASE):
                    if bw not in all_buzzwords:
                        all_buzzwords.append(bw)

            readability = calculate_readability(reconstructed_text)

            return HumanizeResult(
                text=reconstructed_text,
                original_text=text,
                mode=mode,
                tone=tone,
                reading_level=reading_level,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                buzzwords_replaced=all_buzzwords,
                flesch_reading_ease=readability["flesch_reading_ease"],
                flesch_kincaid_grade=readability["flesch_kincaid_grade"],
                grammar_repaired=grammar_repaired,
                is_offline=self.mock_mode,
                engine="gemini-flash-lite (offline)" if self.mock_mode else self.model,
                api_tokens_used=0 if self.mock_mode else total_tokens,
            )

        # preserve_markdown is False: fallback to plain text execution
        system_instruction = self._prepare_prompt(mode, tone, reading_level)
        raw_output, usage = self.generator.generate_sync(text, system_instruction)
        return self._post_process(
            raw_output=raw_output,
            original_text=text,
            mode=mode,
            tone=tone,
            reading_level=reading_level,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            fences=[],
        )

    async def humanize_async(
        self,
        text: str,
        mode: Literal["budget", "deep"] = "budget",
        tone: Literal["neutral", "casual", "academic", "professional"] = "neutral",
        reading_level: Literal["middle_school", "high_school", "college", "general"] = "general",
        preserve_markdown: bool = True,
    ) -> HumanizeResult:
        """Asynchronously humanize text with quality guardrails and readability evaluation."""
        if not text or not text.strip():
            return HumanizeResult(
                text=text,
                original_text=text,
                mode=mode,
                tone=tone,
                reading_level=reading_level,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                buzzwords_replaced=[],
                flesch_reading_ease=100.0,
                flesch_kincaid_grade=0.0,
                grammar_repaired=False,
                is_offline=self.mock_mode,
                engine="gemini-flash-lite (offline)" if self.mock_mode else self.model,
                api_tokens_used=0,
            )

        if preserve_markdown:
            doc = MarkdownDocument(text)
            chunks = doc.extract_chunks(max_chunk_chars=1500)
            humanized_chunks: list[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            all_buzzwords: list[str] = []
            grammar_repaired = False

            system_instruction = self._prepare_prompt(mode, tone, reading_level)

            for chunk in chunks:
                if not chunk.is_humanizable:
                    humanized_chunks.append(chunk.raw_text)
                    continue

                masked_content, mask_state = InlineMasker.mask(chunk.content)
                raw_output, usage = await self.generator.generate_async(
                    masked_content, system_instruction
                )
                prompt_tokens += usage.prompt_tokens
                completion_tokens += usage.completion_tokens
                total_tokens += usage.total_tokens

                clean_text, buzzwords = replace_banned_buzzwords(raw_output)
                all_buzzwords.extend(buzzwords)

                gram_res = sanitize_and_verify_grammar(clean_text)
                if not gram_res.is_valid:
                    grammar_repaired = True

                unmasked = InlineMasker.unmask(gram_res.repaired_text, mask_state)
                humanized_chunks.append(unmasked)

            reconstructed_text = doc.reconstruct(humanized_chunks)

            original_buzzwords = audit_vocabulary(text)
            for bw in original_buzzwords:
                if not re.search(r"\b" + re.escape(bw) + r"\b", reconstructed_text, re.IGNORECASE):
                    if bw not in all_buzzwords:
                        all_buzzwords.append(bw)

            readability = calculate_readability(reconstructed_text)

            return HumanizeResult(
                text=reconstructed_text,
                original_text=text,
                mode=mode,
                tone=tone,
                reading_level=reading_level,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                buzzwords_replaced=all_buzzwords,
                flesch_reading_ease=readability["flesch_reading_ease"],
                flesch_kincaid_grade=readability["flesch_kincaid_grade"],
                grammar_repaired=grammar_repaired,
                is_offline=self.mock_mode,
                engine="gemini-flash-lite (offline)" if self.mock_mode else self.model,
                api_tokens_used=0 if self.mock_mode else total_tokens,
            )

        # preserve_markdown is False: fallback to plain text execution
        system_instruction = self._prepare_prompt(mode, tone, reading_level)
        raw_output, usage = await self.generator.generate_async(text, system_instruction)
        return self._post_process(
            raw_output=raw_output,
            original_text=text,
            mode=mode,
            tone=tone,
            reading_level=reading_level,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            fences=[],
        )

    async def humanize_stream(
        self,
        text: str,
        mode: Literal["budget", "deep"] = "budget",
        tone: Literal["neutral", "casual", "academic", "professional"] = "neutral",
        reading_level: Literal["middle_school", "high_school", "college", "general"] = "general",
        preserve_markdown: bool = True,
    ) -> AsyncIterator[str]:
        """Asynchronously stream humanized text chunks."""
        if not text or not text.strip():
            yield text
            return

        if preserve_markdown:
            doc = MarkdownDocument(text)
            chunks = doc.extract_chunks(max_chunk_chars=1500)
            system_instruction = self._prepare_prompt(mode, tone, reading_level)
            code_fences = [b.raw_text for b in doc.blocks if b.block_type == BlockType.CODE]

            for chunk in chunks:
                if not chunk.is_humanizable:
                    yield chunk.raw_text
                    continue

                masked_content, mask_state = InlineMasker.mask(chunk.content)
                accumulator = StreamChunkAccumulator(fences=code_fences, mask_state=mask_state)
                async for stream_token in self.generator.generate_stream_async(
                    masked_content, system_instruction
                ):
                    for clean_chunk in accumulator.feed(stream_token):
                        yield InlineMasker.unmask(clean_chunk, mask_state)
                for remaining in accumulator.flush():
                    yield InlineMasker.unmask(remaining, mask_state)
            return

        # preserve_markdown is False
        protected, fences = self._protect_code_blocks(text)
        system_instruction = self._prepare_prompt(mode, tone, reading_level)
        accumulator = StreamChunkAccumulator(fences=fences)
        async for chunk in self.generator.generate_stream_async(protected, system_instruction):
            for clean_chunk in accumulator.feed(chunk):
                yield clean_chunk
        for remaining_chunk in accumulator.flush():
            yield remaining_chunk

    def humanize_stream_sync(
        self,
        text: str,
        mode: Literal["budget", "deep"] = "budget",
        tone: Literal["neutral", "casual", "academic", "professional"] = "neutral",
        reading_level: Literal["middle_school", "high_school", "college", "general"] = "general",
        preserve_markdown: bool = True,
    ) -> Iterator[str]:
        """Synchronously stream humanized text chunks."""
        if not text or not text.strip():
            yield text
            return

        if preserve_markdown:
            doc = MarkdownDocument(text)
            chunks = doc.extract_chunks(max_chunk_chars=1500)
            system_instruction = self._prepare_prompt(mode, tone, reading_level)
            code_fences = [b.raw_text for b in doc.blocks if b.block_type == BlockType.CODE]

            for chunk in chunks:
                if not chunk.is_humanizable:
                    yield chunk.raw_text
                    continue

                masked_content, mask_state = InlineMasker.mask(chunk.content)
                accumulator = StreamChunkAccumulator(fences=code_fences, mask_state=mask_state)
                for stream_token in self.generator.generate_stream_sync(
                    masked_content, system_instruction
                ):
                    for clean_chunk in accumulator.feed(stream_token):
                        yield InlineMasker.unmask(clean_chunk, mask_state)
                for remaining in accumulator.flush():
                    yield InlineMasker.unmask(remaining, mask_state)
            return

        # preserve_markdown is False
        protected, fences = self._protect_code_blocks(text)
        system_instruction = self._prepare_prompt(mode, tone, reading_level)
        accumulator = StreamChunkAccumulator(fences=fences)
        for chunk in self.generator.generate_stream_sync(protected, system_instruction):
            for clean_chunk in accumulator.feed(chunk):
                yield clean_chunk
        for remaining_chunk in accumulator.flush():
            yield remaining_chunk

