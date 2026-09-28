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

    @classmethod
    def extract_detailed_word_constraints(
        cls,
        prompt_text: str,
        item_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Extracts detailed minimum and maximum word counts and multi-question specifications
        from question prompts, syllabus rubrics, or input headers.
        Examples:
          - "50 words each for the 5 questions" -> min: 250, max: 300, per_item: 50, num_items: 5
          - "50 words per point" (with 4 criteria) -> min: 200, max: 240, per_item: 50, num_items: 4
          - "50 words each" / "50 words per question" -> min: 50, max: 60, per_item: 50
          - "Between 50 and 75 words" -> min: 50, max: 75
          - "At least 50 words" -> min: 50, max: 60 (20% over)
          - "Around 50 words" -> min: 45, max: 60
        """
        empty_res = {
            "min_words": None,
            "max_words": None,
            "target_words": None,
            "total_min_words": None,
            "max_allowed": None,
            "per_item_words": None,
            "num_items": None,
            "is_multi_part": False,
        }
        if not prompt_text:
            return empty_res

        t = prompt_text.lower()

        # Keywords for items / points / criteria
        ITEM_KWS = r"(?:question|part|item|prompt|point|bullet|criterion|criteria|section|topic)"
        ITEM_PLURALS = r"(?:questions?|parts?|items?|prompts?|points?|bullets?|criteria|criterions?|sections?|topics?)"

        # 1. Multi-part / per-item:
        # 1A: '50 words each for the 5 questions', '50 words per point', 'at least 50 words per point'
        m_each = re.search(
            rf"(?:at\s+least|minimum\s+of|minimum|min|around|approx(?:imately)?|roughly|~)?\s*(\d+)\s*words?\s*(?:each|per\s+{ITEM_KWS}|for\s+each\s+(?:{ITEM_KWS}|one))(?:\s+(?:for|of)\s+(?:the\s+)?(\d+)\s*{ITEM_PLURALS})?",
            t
        )

        # 1B: 'each point at least 50 words', 'for each point, write at least 50 words'
        m_each_first = None
        if not m_each:
            m_each_first = re.search(
                rf"(?:for\s+)?each\s+{ITEM_KWS}[^.\n]*?(?:at\s+least|minimum\s+of|minimum|min|around|approx(?:imately)?|roughly|write(?:\s+(?:a\s+)?))?\s*(\d+)\s*words?",
                t
            )

        # 1C: '5 questions, 50 words each', '4 points of 50 words each'
        m_inv = None
        if not m_each and not m_each_first:
            m_inv = re.search(
                rf"(\d+)\s*{ITEM_PLURALS}[^.\n]*?(\d+)\s*words?\s*(?:each|per|for\s+each)",
                t
            )

        if m_each or m_each_first or m_inv:
            if m_inv:
                num_q = int(m_inv.group(1))
                per_w = int(m_inv.group(2))
            elif m_each_first:
                per_w = int(m_each_first.group(1))
                num_q = None
            else:
                per_w = int(m_each.group(1))
                num_q = int(m_each.group(2)) if m_each.group(2) else None

            if not num_q:
                # If caller provided an item count (e.g. number of criteria in the rubric)
                if item_count and item_count > 1:
                    num_q = item_count
                else:
                    # Check if prompt mentions a count like "5 questions" or "4 points" anywhere in text
                    m_count = re.search(rf"(\d+)\s*(?:[a-zA-Z]+\s+)?{ITEM_PLURALS}", t)
                    if m_count and int(m_count.group(1)) > 1:
                        num_q = int(m_count.group(1))
                    else:
                        # Check if prompt explicitly enumerates questions or bullet points
                        numbered = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|[-*•])\s+", t)
                        if len(numbered) >= 2:
                            num_q = len(numbered)
                        elif item_count and item_count >= 1:
                            num_q = item_count

            if num_q and num_q > 1:
                total_min = per_w * num_q
                return {
                    "min_words": total_min,
                    "max_words": int(total_min * 1.20),
                    "target_words": int(total_min * 1.10),
                    "total_min_words": total_min,
                    "max_allowed": int(per_w * 1.20),
                    "per_item_words": per_w,
                    "num_items": num_q,
                    "is_multi_part": True,
                }

            # Per-item specified, but number of items is not yet known.
            # CRITICAL: Do NOT set total_min_words to per_w, as per_w is only for ONE point/item!
            return {
                "min_words": per_w,
                "max_words": int(per_w * 1.20),
                "target_words": int(per_w * 1.10),
                "total_min_words": None,
                "max_allowed": int(per_w * 1.20),
                "per_item_words": per_w,
                "num_items": None,
                "is_multi_part": True,
            }

        # 3. Range: 'between 50 and 75 words' or '50-75 words'
        m_range = re.search(r"(?:between\s+)?(\d+)\s*(?:-|to|and)\s*(\d+)\s*words?", t)
        if m_range:
            mn = int(m_range.group(1))
            mx = int(m_range.group(2))
            return {
                "min_words": mn,
                "max_words": mx,
                "target_words": int((mn + mx) / 2),
                "total_min_words": mn,
                "max_allowed": mx,
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 4. Explicit Minimums: 'at least 50 words', 'minimum 50 words', '50+ words'
        m_min = re.search(r"(?:at\s+least|minimum\s+of|minimum|min|no\s+less\s+than)\s*(\d+)\s*words?", t)
        if not m_min:
            m_min = re.search(r"(\d+)\s*(?:words?\s+minimum|words?\s+or\s+more|words?\s+at\s+least|\+\s*words?)", t)
        if m_min:
            mn = int(m_min.group(1))
            return {
                "min_words": mn,
                "max_words": int(mn * 1.20),
                "target_words": int(mn * 1.10),
                "total_min_words": mn,
                "max_allowed": int(mn * 1.20),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 5. Approximate / Target: 'around 50 words', 'approx 50 words', '~50 words'
        m_approx = re.search(r"(?:around|about|approx(?:imately)?|roughly|~)\s*(\d+)\s*words?", t)
        if m_approx:
            tgt = int(m_approx.group(1))
            return {
                "min_words": max(5, int(tgt * 0.90)),
                "max_words": int(tgt * 1.20),
                "target_words": tgt,
                "total_min_words": max(5, int(tgt * 0.90)),
                "max_allowed": int(tgt * 1.20),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 6. Direct command or hyphenated: 'in 50 words', 'write 50 words', '50-word response'
        m_direct = re.search(r"(?:write\s+(?:a\s+)?|in\s+)(\d+)\s*words?\b", t)
        if not m_direct:
            m_direct = re.search(r"\b(\d+)\s*-\s*words?\b", t)
        if m_direct:
            w = int(m_direct.group(1))
            return {
                "min_words": w,
                "max_words": int(w * 1.20),
                "target_words": int(w * 1.08),
                "total_min_words": w,
                "max_allowed": int(w * 1.20),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 7. Maximum limit: 'at most 100 words', 'up to 100 words', 'maximum 100 words'
        m_max = re.search(r"(?:at\s+most|maximum\s+of|maximum|max|no\s+more\s+than|up\s+to)\s*(\d+)\s*words?", t)
        if m_max:
            mx = int(m_max.group(1))
            return {
                "min_words": max(5, int(mx * 0.75)),
                "max_words": mx,
                "target_words": int(mx * 0.90),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 8. Counter: '0 / 100 words'
        m_counter = re.search(r"\b\d+\s*(?:/|of)\s*(\d+)\s*words?", t)
        if m_counter:
            mn = int(m_counter.group(1))
            return {
                "min_words": mn,
                "max_words": int(mn * 1.20),
                "target_words": int(mn * 1.10),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        # 9. Sentences
        m_sent = re.search(r"(?:at\s+least|minimum)\s*(\d+)\s*sentences?", t)
        if m_sent:
            mn = int(m_sent.group(1)) * 14
            return {
                "min_words": mn,
                "max_words": int(mn * 1.25),
                "target_words": int(mn * 1.10),
                "per_item_words": None,
                "num_items": None,
                "is_multi_part": False,
            }

        return empty_res

    @classmethod
    def extract_word_constraints(cls, prompt_text: str) -> Tuple[Optional[int], Optional[int]]:
        """Extracts (min_words, max_words) from prompt_text."""
        details = cls.extract_detailed_word_constraints(prompt_text)
        return details.get("min_words"), details.get("max_words")

    @staticmethod
    def count_words(text: str) -> int:
        """Accurately counts words in a given string."""
        if not text:
            return 0
        tokens = re.findall(r"\b[A-Za-z0-9'-]+\b", text)
        return len(tokens)

    @classmethod
    def apply_word_limits(
        cls,
        text: str,
        min_words: Optional[int],
        max_words: Optional[int] = None,
        buffer_pct: Optional[float] = None,
        max_overage: Optional[int] = None,
        per_item_words: Optional[int] = None,
        num_items: Optional[int] = None,
    ) -> str:
        """
        Enforces that the generated text stays strictly within the believable margin
        (10% to 20% buffer over minimum). Trims cleanly at sentence boundaries.
        Supports multi-question responses by trimming each question item individually.
        """
        if not text or (not min_words and not max_words):
            return text.strip() if text else ""

        effective_buffer = buffer_pct if buffer_pct is not None else 0.15

        # Check for multi-question response format (e.g. 1. ... 2. ... 3. ...)
        parts = re.split(r"\n+(?=\s*\d+[\.\)]\s+)", text.strip())
        if len(parts) >= 2 and (per_item_words or (min_words and len(parts) > 1)):
            item_min = per_item_words or (min_words // len(parts))
            item_max = int(item_min * 1.20) if item_min else None
            trimmed_parts = []
            for p in parts:
                p_trimmed = cls._trim_single_block(
                    p, min_words=item_min, max_words=item_max, buffer_pct=effective_buffer
                )
                trimmed_parts.append(p_trimmed)
            return "\n\n".join(trimmed_parts).strip()

        return cls._trim_single_block(
            text, min_words=min_words, max_words=max_words, buffer_pct=effective_buffer
        )

    @classmethod
    def _trim_single_block(
        cls,
        text: str,
        min_words: Optional[int],
        max_words: Optional[int] = None,
        buffer_pct: float = 0.15,
    ) -> str:
        """Helper to trim a single block of text at sentence boundaries."""
        if not text:
            return ""
        words = cls.count_words(text)

        # Calculate strict upper target limit (believable student voice: strictly 10%-20% error margin)
        if max_words:
            target_max = max_words
        elif min_words:
            # Strictly between 10% and 20% over minimum
            buffer_mult = 1.0 + max(0.10, min(buffer_pct, 0.20))
            target_max = int(min_words * buffer_mult)
        else:
            return text.strip()

        if words <= target_max:
            return text.strip()

        logger.info(
            f"Trimming written answer: currently {words} words, target max is {target_max} words (Min: {min_words})."
        )

        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        trimmed_sentences: List[str] = []
        current_count = 0

        for s in sentences:
            s_words = cls.count_words(s)
            if current_count + s_words <= target_max:
                trimmed_sentences.append(s)
                current_count += s_words
            elif min_words and current_count < int(min_words * 0.92):
                # Must include this sentence to satisfy requirement
                trimmed_sentences.append(s)
                current_count += s_words
                break
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
        per_question_words: Optional[int] = None,
        num_questions: Optional[int] = None,
    ) -> str:
        """
        Calls Gemini 3.8 Flash to generate an authentic student response tailored to the prompt
        and constraints. Enforces believable length (10% to 20% over minimum).
        """
        quality_instr = self._get_quality_instruction()

        if per_question_words and num_questions:
            target_words_per_q = int(per_question_words * 1.10)
            max_words_per_q = int(per_question_words * 1.20)
            total_target = int((per_question_words * num_questions) * 1.10)
            total_max = int((per_question_words * num_questions) * 1.20)
            length_instr = (
                f"MANDATORY MULTI-QUESTION LENGTH & STRUCTURE:\n"
                f"- This prompt requires answering {num_questions} questions.\n"
                f"- Answer EACH question in approximately {target_words_per_q} words (STRICT LIMIT: between {per_question_words} and {max_words_per_q} words per question).\n"
                f"- Total response length must be between {per_question_words * num_questions} and {total_max} words (target: ~{total_target} words).\n"
                f"- Format clearly with numbered items (1., 2., 3., etc.).\n"
                f"- ABSOLUTE RULE: Do NOT write an overly verbose 1000-word essay! A genuine student writes concise, focused answers (~{target_words_per_q} words each)."
            )
        elif min_words and max_words:
            target_words = int((min_words + max_words) / 2)
            length_instr = (
                f"MANDATORY LENGTH (BELIEVABILITY): Write between {min_words} and {max_words} words "
                f"(target: approx {target_words} words). A believable student response is focused and concise. "
                f"Do NOT exceed {max_words} words under any circumstances."
            )
        elif min_words:
            target_words = int(min_words * (1.0 + min(self.word_buffer_pct, 0.15)))
            max_allowed = int(min_words * 1.20)
            length_instr = (
                f"MANDATORY LENGTH (BELIEVABILITY): You MUST write between {min_words} and {max_allowed} words "
                f"(target: approximately {target_words} words, giving a 10% to 20% error buffer above minimum). "
                f"Do NOT exceed {max_allowed} words under any circumstances. Writing hundreds of words when a {min_words}-word "
                f"response is asked is completely unbelievable and looks like an AI dump."
            )
        elif max_words:
            length_instr = (
                f"MANDATORY LENGTH: Write up to {max_words} words. Do NOT exceed {max_words} words."
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
            target_words = int(min_words * 1.10)
            max_allowed = max_words if max_words else int(min_words * 1.20)
            length_instr = (
                f"DEFICIT DETECTED: The existing response only has {curr_words} words, but the prompt requires at least {min_words} words.\n"
                f"You MUST expand the response so it is between {min_words} and {max_allowed} words (target: approx {target_words} words).\n"
                f"Do NOT exceed {max_allowed} words under any circumstances."
            )
        elif max_words and curr_words > max_words:
            length_instr = (
                f"OVERAGE DETECTED: The existing response has {curr_words} words, exceeding the limit of {max_words} words.\n"
                f"Tighten and condense the response so it is strictly between {min_words or int(max_words * 0.8)} and {max_words} words."
            )
        elif min_words and max_words:
            length_instr = (
                f"MANDATORY LENGTH: Revise the text to stay strictly between {min_words} and {max_words} words."
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
            user_prompt += f"\nAdditional Refinement Instructions:\n{user_instructions}\n"

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

        return revised.strip() if revised else existing_text.strip()

    def is_placeholder_text(self, text: str) -> bool:
        """
        Determines whether the provided text is merely an empty platform UI prompt/placeholder
        (e.g., 'Type your answer here...', '0 / 150 words') rather than actual student draft work.
        """
        if not text or not text.strip():
            return True
        clean = text.strip().lower()
        placeholder_patterns = [
            r"^type\s+(?:your\s+)?(?:answer|response|text|here)",
            r"^enter\s+(?:your\s+)?(?:answer|response|text|here)",
            r"^click\s+here\s+to\s+(?:type|write|answer)",
            r"^\d+\s*/\s*\d+\s*words?",
            r"^\d+\s*words?\s*remaining",
            r"^write\s+your\s+response",
            r"^response\s+goes\s+here",
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
        override_max_words: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Complete end-to-end written response pipeline:
        1. Extract detailed word constraints and multi-question structures.
        2. Generate fresh draft or edit existing text if errors were detected.
        3. Enforce believable word limits (+10%-20% buffer over minimum).
        4. Apply Jade's AI Humanizer (sanitizes buzzwords, refines flow, adjusts reading level).
        5. Run local offline spellcheck and typo correction.
        Returns:
            Dict with final_text, word_count, min_words, humanized (bool), corrections, and status.
        """
        details = self.extract_detailed_word_constraints(prompt_text)
        detected_min = details.get("min_words")
        detected_max = details.get("max_words")
        per_item_words = details.get("per_item_words")
        num_items = details.get("num_items")

        min_words = override_min_words or detected_min
        max_words = override_max_words or detected_max
        if min_words and not max_words:
            max_words = int(min_words * 1.20)

        # 1. Generate or Edit (filter out placeholder text so it is never treated as a student draft)
        is_real_existing = existing_text and len(existing_text.strip()) > 5 and not self.is_placeholder_text(existing_text)
        if is_real_existing:
            logger.info(f"Existing text detected ({self.count_words(existing_text)} words). Editing and revising...")
            raw_text = self.edit_existing_text(
                existing_text=existing_text,
                prompt_text=prompt_text,
                error_feedback=error_feedback,
                min_words=min_words,
                max_words=max_words,
            )
        else:
            if existing_text and self.is_placeholder_text(existing_text):
                logger.info(f"Ignoring placeholder text in input box ('{existing_text[:40]}...'). Generating fresh draft.")
            logger.info(f"Generating new written draft via {self.model_name} (Min: {min_words}, Max: {max_words}, Per-Item: {per_item_words})...")
            raw_text = self.generate_draft(
                prompt_text=prompt_text,
                min_words=min_words,
                max_words=max_words,
                per_question_words=per_item_words,
                num_questions=num_items,
            )

        # 2. Enforce word limits with 10%-20% buffer
        limited_text = self.apply_word_limits(
            text=raw_text,
            min_words=min_words,
            max_words=max_words,
            per_item_words=per_item_words,
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

        # Re-check word limit strictly after humanization and spellcheck
        if min_words or max_words:
            final_text = self.apply_word_limits(
                final_text,
                min_words=min_words,
                max_words=max_words,
                per_item_words=per_item_words
            )

        final_word_count = self.count_words(final_text)

        return {
            "text": final_text,
            "raw_draft": raw_text,
            "original_draft": limited_text,
            "humanized_text": humanized_text,
            "text_changed": (limited_text.strip() != final_text.strip()),
            "word_count": final_word_count,
            "min_words": min_words,
            "max_words": max_words,
            "humanized": humanized_applied,
            "humanize_metrics": humanize_metrics,
            "corrections": corrections,
            "is_written_response": final_word_count >= 10,
        }
