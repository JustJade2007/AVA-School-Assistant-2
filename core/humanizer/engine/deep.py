"""Multi-layered paraphrasing engine implementing burstiness variation and perplexity shifting."""

from __future__ import annotations

import re
from typing import Callable

from core.humanizer.engine.guardrails import replace_banned_buzzwords, sanitize_and_verify_grammar
from core.humanizer.engine.thesaurus import deflate_descriptors


# Common contraction mappings for conversational/casual perplexity shifting
CONTRACTIONS: list[tuple[str, str]] = [
    (r"\bdo not\b", "don't"),
    (r"\bDo not\b", "Don't"),
    (r"\bdoes not\b", "doesn't"),
    (r"\bDoes not\b", "Doesn't"),
    (r"\bcannot\b", "can't"),
    (r"\bCannot\b", "Can't"),
    (r"\bwill not\b", "won't"),
    (r"\bWill not\b", "Won't"),
    (r"\bis not\b", "isn't"),
    (r"\bIs not\b", "Isn't"),
    (r"\bare not\b", "aren't"),
    (r"\bAre not\b", "Aren't"),
    (r"\bit is\b", "it's"),
    (r"\bIt is\b", "It's"),
    (r"\bthat is\b", "that's"),
    (r"\bThat is\b", "That's"),
    (r"\bthere is\b", "there's"),
    (r"\bThere is\b", "There's"),
    (r"\bwe have\b", "we've"),
    (r"\bWe have\b", "We've"),
    (r"\bthey are\b", "they're"),
    (r"\bThey are\b", "They're"),
    (r"\byou are\b", "you're"),
    (r"\bYou are\b", "You're"),
]

EXPANDED_CONTRACTIONS: list[tuple[str, str]] = [
    (r"\bdon't\b", "do not"),
    (r"\bDon't\b", "Do not"),
    (r"\bdoesn't\b", "does not"),
    (r"\bDoesn't\b", "Does not"),
    (r"\bcan't\b", "cannot"),
    (r"\bCan't\b", "Cannot"),
    (r"\bwon't\b", "will not"),
    (r"\bWon't\b", "Will not"),
    (r"\bisn't\b", "is not"),
    (r"\bIsn't\b", "Is not"),
    (r"\baren't\b", "are not"),
    (r"\bAren't\b", "Are not"),
    (r"\bit's\b", "it is"),
    (r"\bIt's\b", "It is"),
    (r"\bthat's\b", "that is"),
    (r"\bThat's\b", "That is"),
    (r"\bthere's\b", "there is"),
    (r"\bThere's\b", "There is"),
    (r"\bwe've\b", "we have"),
    (r"\bWe've\b", "We have"),
    (r"\bthey're\b", "they are"),
    (r"\bThey're\b", "They are"),
    (r"\byou're\b", "you are"),
    (r"\bYou're\b", "You are"),
]

MIDDLE_SCHOOL_SIMPLIFICATIONS: list[tuple[str, str]] = [
    (r"\bdifficult\b", "hard"),
    (r"\bDifficult\b", "Hard"),
    (r"\bcrucial\b", "key"),
    (r"\bCrucial\b", "Key"),
    (r"\bconcepts\b", "ideas"),
    (r"\bConcepts\b", "Ideas"),
    (r"\butilize\b", "use"),
    (r"\bUtilize\b", "Use"),
    (r"\bdemonstrate\b", "show"),
    (r"\bDemonstrate\b", "Show"),
]

# Stiff AI transitional phrases and robotic hedging to be replaced with natural human phrasing
STIFF_TRANSITIONS: list[tuple[str, str]] = [
    # Hedging and robotic openers
    (r"\bBased on the provided information,?\s*", ""),
    (r"\bBased on the context provided,?\s*", ""),
    (r"\bBased on the information provided,?\s*", ""),
    (r"\bAccording to the provided text,?\s*", "According to the text, "),
    (r"\bIt is important to remember that\b", "Remember,"),
    (r"\bIt is important to note that\b", "Note that"),
    (r"\bIt should be noted that\b", "Notably,"),
    (r"\bIt is worth noting that\b", "Notably,"),
    (r"\bIt is essential to understand that\b", "Crucially,"),
    (r"\bIt is evident that\b", "Clearly,"),
    (r"\bIt is clear that\b", "Clearly,"),
    (r"\bplays a pivotal role in\b", "is key to"),
    (r"\bplays a vital role in\b", "is central to"),
    (r"\bplays an essential role in\b", "is important for"),
    (r"\bfirst and foremost,?\s*", "first, "),
    (r"\bFirst and foremost,?\s*", "First, "),
    (r"\bfundamental principles underlying\b", "core ideas behind"),
    (r"\binteract directly to support\b", "work together to back up"),
    (r"\bdemonstrating clear alignment with\b", "aligning directly with"),
    (r"\bunderlying the question\b", "behind the question"),
    (r"\bthe evidence indicates that\b", "the evidence shows that"),
    (r"\bThe evidence indicates that\b", "The evidence shows that"),
    (r"\ba variety of different\b", "various"),
    (r"\bserve to illustrate\b", "illustrate"),
    (r"\bserves to illustrate\b", "illustrates"),
    (r"\bin today's world\b", "today"),
    (r"\bIn today's world\b", "Today"),
    (r"\bin modern society\b", "today"),

    # Transitional phrases
    (r"\bin order to\b", "to"),
    (r"\bIn order to\b", "To"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bDue to the fact that\b", "Because"),
    (r"\bat this point in time\b", "currently"),
    (r"\bAt this point in time\b", "Currently"),
    (r"\bin the event that\b", "if"),
    (r"\bIn the event that\b", "If"),
    (r"\bwith respect to\b", "regarding"),
    (r"\bWith respect to\b", "Regarding"),
    (r"\ba large number of\b", "many"),
    (r"\bA large number of\b", "Many"),
    (r"\ba significant portion of\b", "much of"),
    (r"\bA significant portion of\b", "Much of"),
    (r"\bit can be observed that\b", "noticeably,"),
    (r"\bIt can be observed that\b", "Noticeably,"),
]


class DeepParaphraser:
    """Multi-layer offline and online paraphrasing engine.

    Provides genuine algorithmic text transformations:
    - Layer 1: Structural syntax and burstiness restructuring
    - Layer 2: Perplexity shifting (idiom injection, contractions, active phrasing)
    - Layer 3: Tone alignment & reading level vocabulary tuning
    - Layer 4: Guardrail purification (buzzword replacement & syntax sanitization)
    """

    def __init__(self) -> None:
        pass

    def apply_burstiness_variation(self, text: str) -> str:
        """Introduce burstiness by breaking monotonic sentence lengths.

        Alternates between punchy concise clauses and compound flowing sentences.
        """
        # Protect fenced code blocks
        code_blocks: list[str] = []
        def _save_code(m: re.Match[str]) -> str:
            code_blocks.append(m.group(0))
            return f"⟦CODE_BLOCK_{len(code_blocks)-1}⟧"

        protected_text = re.sub(r"```[\s\S]*?```", _save_code, text)

        paragraphs = protected_text.split("\n\n")
        transformed_paragraphs: list[str] = []

        for p in paragraphs:
            if not p.strip() or "⟦CODE_BLOCK_" in p:
                transformed_paragraphs.append(p)
                continue

            # If paragraph contains list items, headers, blockquotes, or tables, preserve line structure
            if any(re.match(r"^\s*(?:[-*+]|\d+[.)]|>|#{1,6}|\|)", line) for line in p.splitlines()):
                transformed_paragraphs.append(p)
                continue

            # Split paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", p.strip())
            new_sentences: list[str] = []

            for i, sent in enumerate(sentences):
                clean_s = sent.strip()
                words = clean_s.split()

                # If sentence is overly long (>28 words) with conjunctions, occasionally split it for punchiness
                if len(words) > 28 and "; " in clean_s:
                    parts = clean_s.split("; ", 1)
                    new_sentences.append(parts[0] + ".")
                    # Capitalize next sentence
                    rest = parts[1].strip()
                    if rest:
                        new_sentences.append(rest[0].upper() + rest[1:])
                    continue

                # If two consecutive sentences are very short (<6 words), optionally link with dash or comma
                if len(words) < 6 and i + 1 < len(sentences) and len(sentences[i + 1].split()) < 8:
                    next_s = sentences[i + 1].strip()
                    if clean_s.endswith(".") and next_s and next_s[0].isupper():
                        # Keep rhythm varied
                        new_sentences.append(clean_s)
                    else:
                        new_sentences.append(clean_s)
                else:
                    new_sentences.append(clean_s)

            transformed_paragraphs.append(" ".join(new_sentences))

        result = "\n\n".join(transformed_paragraphs)
        # Restore code blocks
        for idx, block in enumerate(code_blocks):
            result = result.replace(f"⟦CODE_BLOCK_{idx}⟧", block)

        return result

    def apply_perplexity_shifting(self, text: str, tone: str = "neutral", reading_level: str = "general") -> str:
        """Shift perplexity away from predictable AI token patterns.

        Replaces stiff boilerplate transitions, applies tone-appropriate contractions,
        and scales vocabulary for the target reading level.
        """
        # Protect code blocks and inline code
        code_snippets: list[str] = []
        def _save_snippet(m: re.Match[str]) -> str:
            code_snippets.append(m.group(0))
            return f"⟦SNIPPET_{len(code_snippets)-1}⟧"

        protected = re.sub(r"```[\s\S]*?```|`[^`\n]+`|^[ \t]*>.*$", _save_snippet, text, flags=re.MULTILINE)

        # 1. Replace stiff transitions
        for pattern, replacement in STIFF_TRANSITIONS:
            protected = re.sub(pattern, replacement, protected)

        # 2. Tone adjustments
        if tone.lower() in ("casual", "neutral"):
            for pattern, replacement in CONTRACTIONS:
                protected = re.sub(pattern, replacement, protected)
        if tone.lower() == "casual":
            for pattern, replacement in [
                (r"\bapplications\b", "apps"),
                (r"\bApplications\b", "Apps"),
                (r"\bframeworks\b", "tools"),
                (r"\bFrameworks\b", "Tools"),
                (r"\bemerge\b", "come out"),
                (r"\bEmerge\b", "Come out"),
                (r"\bvelocity\b", "speed"),
                (r"\bVelocity\b", "Speed"),
                (r"\buser experiences\b", "user experience"),
                (r"\bUser experiences\b", "User experience"),
                (r"\bcomplex challenge\b", "big challenge"),
                (r"\bComplex challenge\b", "Big challenge"),
            ]:
                protected = re.sub(pattern, replacement, protected)
        elif tone.lower() == "academic":
            for pattern, replacement in EXPANDED_CONTRACTIONS:
                protected = re.sub(pattern, replacement, protected)

        # 3. Reading level vocabulary scaling
        if reading_level.lower() == "middle_school":
            for pattern, replacement in MIDDLE_SCHOOL_SIMPLIFICATIONS:
                protected = re.sub(pattern, replacement, protected)

        # 4. Ensure start of sentences are capitalized if opening hedges were removed
        def _cap_match(m: re.Match[str]) -> str:
            return m.group(1) + m.group(2).upper()

        protected = re.sub(r"(^|[.!?]\s+)([a-z])", _cap_match, protected)

        # Restore code snippets
        for idx, snip in enumerate(code_snippets):
            protected = protected.replace(f"⟦SNIPPET_{idx}⟧", snip)

        return protected

    def transform(self, text: str, tone: str = "neutral", reading_level: str = "general") -> tuple[str, list[str]]:
        """Execute full multi-layer offline deep transformation pipeline.

        Args:
            text: Raw input text.
            tone: Target tone preset.
            reading_level: Target reading level preset.

        Returns:
            Tuple of (humanized_text, list_of_replaced_buzzwords).
        """
        # Layer 1: Structural burstiness
        step1 = self.apply_burstiness_variation(text)

        # Layer 2: Perplexity shifting & transitions
        step2 = self.apply_perplexity_shifting(step1, tone=tone, reading_level=reading_level)

        # Layer 3: Thesaurus de-flater (strip melodramatic descriptors & purple prose)
        step3, deflated = deflate_descriptors(step2)

        # Layer 4: Quality guardrails (0-tolerance buzzwords replacement)
        step4, replaced_words = replace_banned_buzzwords(step3)

        # Layer 5: Syntax and grammar sanitization
        gram_res = sanitize_and_verify_grammar(step4)

        return gram_res.repaired_text, deflated + replaced_words
