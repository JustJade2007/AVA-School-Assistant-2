"""
Written Questions Solver Orchestrator for AVA 2.0.
Specialized engine for detecting word constraints, generating answers via Gemini 3.8 Flash,
polishing text using Jade's AI Humanizer, executing offline spellcheck, enforcing word limits,
and revising/editing existing text when errors are detected.
"""

import re
from typing import Optional, Tuple, Dict, Any, List
from core.logger import get_logger
from core.spellcheck import Spellchecker
from core.humanizer import (
    Humanizer,
    ModePreset,
    ReadingLevelPreset,
    TonePreset,
    HumanizeResult,
)

logger = get_logger("written_solver")


class WrittenSolver:
    """Orchestrates written response generation, constraint enforcement, and humanization."""

    def __init__(
        self,
        ai_client=None,
        api_key: str = "",
        model_name: str = "gemini-3.8-flash",
        quality_preset: str = "a_grade",
        word_buffer_pct: float = 0.15,
        max_word_overage: int = 20,
        humanizer_enabled: bool = True,
        humanizer_mode: str = "budget",
        humanizer_tone: str = "academic",
        humanizer_reading_level: str = "high_school",
        spellcheck_enabled: bool = True,
    ):
        self.ai_client = ai_client
        self.api_key = api_key
        self.model_name = model_name
        self.quality_preset = quality_preset
        self.word_buffer_pct = word_buffer_pct
        self.max_word_overage = max_word_overage
        self.humanizer_enabled = humanizer_enabled
        self.humanizer_mode = humanizer_mode
        self.humanizer_tone = humanizer_tone
        self.humanizer_reading_level = humanizer_reading_level
        self.spellcheck = Spellchecker(enabled=spellcheck_enabled)

        # Initialize Jade's AI Humanizer
        h_model = self.model_name if "gemini" in self.model_name.lower() else "gemini-2.5-flash"
        try:
            self.humanizer = Humanizer(
                api_key=self.api_key,
                model=h_model,
                fallback_model="gemini-2.0-flash",
                mock_mode=not bool(self.api_key),
            )
        except Exception as e:
            logger.warning(f"Could not init live Humanizer: {e}. Falling back to offline mock mode.")
            self.humanizer = Humanizer(mock_mode=True)

    @staticmethod
    def extract_word_constraints(prompt_text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extracts minimum and maximum word counts specified in question prompts or input headers.
        Examples:
          - "Write at least 50 words..." -> (50, None)
          - "Minimum 100 words" -> (100, None)
          - "Between 75 and 100 words" -> (75, 100)
          - "50-100 words" -> (50, 100)
          - "0 / 150 words" -> (150, None)
          - "In 3 to 5 sentences" -> (45, 75) [approx 15 words/sentence]
        """
        if not prompt_text:
            return None, None

        text = prompt_text.lower()

        # Range pattern: e.g. "between 50 and 100 words", "50-100 words", "100-150 word"
        m_range = re.search(r"(?:between\s+)?(\d+)\s*(?:-|to|and)\s*(\d+)\s*words?", text)
        if m_range:
            min_w = int(m_range.group(1))
            max_w = int(m_range.group(2))
            return min_w, max_w

        # Minimum pattern: e.g. "at least 50 words", "minimum 50 words", "min 50 words", "50+ words", "minimum of 25 words"
        m_min = re.search(r"(?:at\s+least|minimum\s+of|minimum|min|no\s+less\s+than)\s*(\d+)\s*words?", text)
        if m_min:
            return int(m_min.group(1)), None

        m_plus = re.search(r"(\d+)\+\s*words?", text)
        if m_plus:
            return int(m_plus.group(1)), None

        # Counter indicator pattern: e.g. "0 / 100 words" or "0 of 50 words"
        m_counter = re.search(r"\b\d+\s*(?:/|of)\s*(\d+)\s*words?", text)
        if m_counter:
            return int(m_counter.group(1)), None

        # Hyphenated word count pattern: e.g. "100-word essay" -> (100, None)
        m_hyphen = re.search(r"\b(\d+)\s*-\s*words?\b", text)
        if m_hyphen:
            return int(m_hyphen.group(1)), None

        # Sentence count pattern: e.g. "in at least 3 sentences" -> ~45 words
        m_sentences = re.search(r"(?:at\s+least|minimum)\s*(\d+)\s*sentences?", text)
        if m_sentences:
            return int(m_sentences.group(1)) * 15, None

        # "In 3-5 sentences"
        m_sent_range = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*sentences?", text)
        if m_sent_range:
            return int(m_sent_range.group(1)) * 14, int(m_sent_range.group(2)) * 18

        return None, None

    @staticmethod
    def count_words(text: str) -> int:
        """Accurately counts words in a given string."""
        if not text:
            return 0
        tokens = re.findall(r"\b[A-Za-z0-9'-]+\b", text)
        return len(tokens)

    def apply_word_limits(
        self,
        text: str,
        min_words: Optional[int],
        max_words: Optional[int] = None,
        buffer_pct: Optional[float] = None,
        max_overage: Optional[int] = None,
    ) -> str:
        """
        Enforces that the generated text does not exceed the word minimum by more than
        the configured percentage buffer (10-20%) or max word overage (e.g. +15-25 words).
        Trims smoothly at sentence boundaries.
        """
        if not text or not min_words or min_words < 5:
            return text.strip()

        effective_buffer = buffer_pct if buffer_pct is not None else self.word_buffer_pct
        effective_overage = max_overage if max_overage is not None else self.max_word_overage

        words = self.count_words(text)

        # Calculate upper target limit
        buffer_allowed = int(min_words * effective_buffer)
        allowed_overage = min(buffer_allowed, effective_overage)
        target_max = min_words + allowed_overage

        if max_words:
            target_max = min(target_max, max_words)

        if words <= target_max:
            return text.strip()

        logger.info(
            f"Trimming written answer: currently {words} words, target max is {target_max} words (Min: {min_words})."
        )

        # Split into sentences preserving punctuation
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        trimmed_sentences: List[str] = []
        current_count = 0

        for s in sentences:
            s_words = self.count_words(s)
            # If adding this sentence keeps us under or close to target_max, or if we haven't hit min_words yet
            if (current_count + s_words <= target_max) or (current_count < min_words):
                trimmed_sentences.append(s)
                current_count += s_words
            else:
                break

        if trimmed_sentences:
            return " ".join(trimmed_sentences).strip()

        return text.strip()

    enforce_word_limits = apply_word_limits

    def _get_quality_instruction(self) -> str:
        """Returns prompt styling instructions tailored to the chosen quality preset."""
        preset = (self.quality_preset or "a_grade").lower()
        if preset in ["b_grade", "realistic", "b"]:
            return (
                "STYLE GUIDELINE: Write like an authentic B-grade student. "
                "Keep sentences direct and clear. Sound genuine and natural rather than overly academic. "
                "Do not use pretentious adjectives, grandiose metaphors, or AI buzzwords."
            )
        elif preset in ["honors_ap", "honors", "ap", "college"]:
            return (
                "STYLE GUIDELINE: Write like an Honors or Advanced Placement student. "
                "Provide thoughtful analytical insight, rich contextual depth, and structured argumentation. "
                "Use precise subject-matter terminology while maintaining a genuine human voice."
            )
        else:  # a_grade default
            return (
                "STYLE GUIDELINE: Write like a strong A-grade student. "
                "Clear, concise, insightful, well-structured sentences with natural transitions. "
                "Avoid fluff and avoid formulaic AI clichés."
            )

    def generate_draft(
        self,
        prompt_text: str,
        min_words: Optional[int] = None,
        max_words: Optional[int] = None,
        context_notes: str = "",
    ) -> str:
        """
        Calls Gemini 3.8 Flash to generate an authentic student response tailored to the prompt
        and constraints.
        """
        quality_instr = self._get_quality_instruction()

        length_instr = ""
        if min_words and max_words:
            length_instr = f"MANDATORY LENGTH: Write between {min_words} and {max_words} words."
        elif min_words:
            target_words = int(min_words * (1.0 + min(self.word_buffer_pct, 0.15)))
            length_instr = (
                f"MANDATORY LENGTH: You MUST write at least {min_words} words. "
                f"Target approximately {target_words} words. Do NOT exceed {min_words + self.max_word_overage} words."
            )
        else:
            length_instr = "LENGTH: Provide a complete 2 to 4 sentence explanation (approx 35 to 65 words)."

        system_instruction = (
            "You are an expert student academic writer assisting with schoolwork. "
            "Your response must directly and thoroughly answer the prompt with academic accuracy. "
            f"{quality_instr}\n"
            f"{length_instr}\n"
            "RULES:\n"
            "1. Do NOT include markdown titles, intros like 'Here is my answer:', or surrounding quotes.\n"
            "2. Output the exact final text ready to be typed into the schoolwork response box.\n"
            "3. Never mention that you are an AI or language model."
        )

        user_content = f"Question/Prompt:\n{prompt_text}"
        if context_notes:
            user_content += f"\n\nContext/Reference Information:\n{context_notes}"

        # Execute query via ai_client or Gemini REST
        draft = ""
        if self.ai_client:
            try:
                # Use Gemini 3.8 Flash
                draft = self.ai_client.generate_text_response(
                    prompt=user_content,
                    system_instruction=system_instruction,
                    model_override=self.model_name,
                )
            except Exception as e:
                logger.error(f"Failed to query AI Client for written draft: {e}")

        # Fallback if empty or AIClient not available
        if not draft:
            clean_q = re.sub(r"^(?:please\s+)?(?:explain|describe|what is|how does|why did|discuss)\s+", "", prompt_text.strip(), flags=re.IGNORECASE).rstrip("?.")
            draft = (
                f"Regarding {clean_q}, key factors interact directly to produce the observed outcome. "
                f"The evidence shows that these mechanisms function together consistently, supporting the core concept."
            )

        return draft.strip()

    def edit_existing_text(
        self,
        existing_text: str,
        prompt_text: str = "",
        error_feedback: str = "",
        min_words: Optional[int] = None,
        max_words: Optional[int] = None,
        user_instructions: str = "",
    ) -> str:
        """
        Surgically edits, expands, and corrects existing text when errors, word count deficits,
        or platform rejection hints are detected.
        """
        quality_instr = self._get_quality_instruction()
        curr_words = self.count_words(existing_text)

        length_instr = ""
        if min_words and curr_words < min_words:
            length_instr = (
                f"DEFICIT DETECTED: The existing response only has {curr_words} words, but the prompt requires at least {min_words} words. "
                f"You MUST expand the response to at least {min_words} words by providing more detail, analysis, and supporting examples."
            )

        system_instruction = (
            "You are an expert academic tutor and editor revising a student's existing written response. "
            "Your task is to fix any factual errors, grammatical issues, spelling slips, or word-count deficiencies "
            "while maintaining the original student perspective and core intent.\n"
            f"{quality_instr}\n"
            f"{length_instr}\n"
            "RULES:\n"
            "1. Fix any flagged platform errors, miscalculations, or phrasing problems.\n"
            "2. Output ONLY the revised, ready-to-type paragraph without meta-commentary or explanations."
        )

        user_prompt = (
            f"Original Prompt/Question:\n{prompt_text or 'Revise and improve the existing student text.'}\n\n"
            f"Existing Student Text to Revise:\n{existing_text}\n"
        )
        if error_feedback:
            user_prompt += f"\nDetected Errors / Platform Feedback:\n{error_feedback}\n"
        if user_instructions:
            user_prompt += f"\nUser Edit Instructions:\n{user_instructions}\n"

        revised = ""
        if self.ai_client:
            try:
                revised = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_instruction,
                    model_override=self.model_name,
                )
            except Exception as e:
                logger.error(f"Failed to query AI Client for text editing: {e}")

        if not revised:
            # Local fallback: run spellcheck & grammar pass
            revised, _ = self.spellcheck.check_and_correct(existing_text)

        return revised.strip()

    @staticmethod
    def is_placeholder_text(text: Optional[str]) -> bool:
        """
        Determines whether a string is placeholder/guidance text rather than actual student input.
        Examples: 'Type your answer here...', 'Enter response', 'Write here', 'Click to add text', 'Your answer'
        """
        if not text:
            return True
        clean = text.strip().lower()
        if len(clean) < 3:
            return True

        # Common placeholder patterns
        placeholder_patterns = [
            r"^(?:type|enter|write|input|put)\s+(?:(?:your|an?)\s+)?(?:answer|response|essay|text|paragraph|notes?|solution|work|explanation|here|something)",
            r"^(?:type|write|enter)\s+(?:here|something)",
            r"^click\s+(?:here\s+)?to\s+(?:add|enter|type|write|respond|edit)",
            r"^(?:your\s+)?(?:answer|response|work|explanation)\s*(?:here)?\.{0,3}$",
            r"^e\.?g\.?[\s:]",
            r"^select\s+(?:an?\s+)?(?:option|answer|choice)",
            r"^choose\s+(?:an?\s+)?(?:option|answer|choice)",
            r"^please\s+(?:enter|type|write|select)",
            r"^start\s+typing",
            r"^write\s+your\s+response",
            r"^add\s+(?:a\s+)?(?:comment|response|text)",
            r"^(?:optional|required)(?:\s+response|\s+answer|\s+text)?\.{0,3}$",
            r"^[_\.\-]{3,}$",
        ]
        for pat in placeholder_patterns:
            if re.search(pat, clean):
                return True
        return False

    def process_solution(
        self,
        prompt_text: str,
        existing_text: Optional[str] = None,
        error_feedback: str = "",
        override_min_words: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Complete end-to-end written response pipeline:
        1. Extract word constraints.
        2. Generate fresh draft or edit existing text if errors were detected.
        3. Enforce word limits (+10%-20% buffer over minimum).
        4. Apply Jade's AI Humanizer (sanitizes buzzwords, refines flow, adjusts reading level).
        5. Run local offline spellcheck and typo correction.
        Returns:
            Dict with final_text, word_count, min_words, humanized (bool), corrections, and status.
        """
        detected_min, detected_max = self.extract_word_constraints(prompt_text)
        min_words = override_min_words or detected_min

        # 1. Generate or Edit (filter out placeholder text so it is never treated as a student draft)
        is_real_existing = existing_text and len(existing_text.strip()) > 5 and not self.is_placeholder_text(existing_text)
        if is_real_existing:
            logger.info(f"Existing text detected ({self.count_words(existing_text)} words). Editing and revising...")
            raw_text = self.edit_existing_text(
                existing_text=existing_text,
                prompt_text=prompt_text,
                error_feedback=error_feedback,
                min_words=min_words,
                max_words=detected_max,
            )
        else:
            if existing_text and self.is_placeholder_text(existing_text):
                logger.info(f"Ignoring placeholder text in input box ('{existing_text[:40]}...'). Generating fresh draft.")
            logger.info(f"Generating new written draft via {self.model_name} (Min words: {min_words})...")
            raw_text = self.generate_draft(
                prompt_text=prompt_text,
                min_words=min_words,
                max_words=detected_max,
            )

        # 2. Enforce word limits
        limited_text = self.apply_word_limits(
            text=raw_text,
            min_words=min_words,
            max_words=detected_max,
        )

        # 3. Apply Jade's AI Humanizer
        humanized_text = limited_text
        humanized_applied = False
        humanize_metrics = {}

        if self.humanizer_enabled:
            try:
                res: HumanizeResult = self.humanizer.humanize(
                    limited_text,
                    mode=self.humanizer_mode,
                    tone=self.humanizer_tone,
                    reading_level=self.humanizer_reading_level,
                )
                humanized_text = res.text
                humanized_applied = True
                text_changed = (limited_text.strip() != humanized_text.strip())
                humanize_metrics = {
                    "flesch_reading_ease": res.flesch_reading_ease,
                    "flesch_kincaid_grade": res.flesch_kincaid_grade,
                    "buzzwords_replaced": len(res.buzzwords_replaced),
                    "is_offline": res.is_offline,
                    "text_changed": text_changed,
                    "engine": getattr(res, "engine", "gemini"),
                }
                logger.info(
                    f"Jade's AI Humanizer applied ({self.humanizer_mode} / {self.humanizer_tone}): "
                    f"is_offline={res.is_offline}, text_changed={text_changed}, "
                    f"Grade {res.flesch_kincaid_grade:.1f}, Ease {res.flesch_reading_ease:.1f}, "
                    f"buzzwords replaced={len(res.buzzwords_replaced)}"
                )
            except Exception as e:
                logger.warning(f"Jade's AI Humanizer encountered error: {e}. Keeping base draft.")

        # 4. Spellcheck and typo cleanup
        final_text, corrections = self.spellcheck.check_and_correct(humanized_text)

        # Re-check word limit after humanization and spellcheck
        if min_words:
            final_text = self.apply_word_limits(final_text, min_words, detected_max)

        final_word_count = self.count_words(final_text)

        return {
            "text": final_text,
            "raw_draft": raw_text,
            "original_draft": limited_text,
            "humanized_text": humanized_text,
            "text_changed": (limited_text.strip() != final_text.strip()),
            "word_count": final_word_count,
            "min_words": min_words,
            "max_words": detected_max,
            "humanized": humanized_applied,
            "humanize_metrics": humanize_metrics,
            "corrections": corrections,
            "is_written_response": final_word_count >= 10,
        }
