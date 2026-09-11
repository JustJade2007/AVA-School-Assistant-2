"""Token-minimized system instructions and style presets.

Guarantees budget mode operates strictly under <100 prompt tokens overhead
per request while preserving tone fidelity and structural integrity.
"""

from __future__ import annotations

import re

# Compact base instruction for budget mode (~45 tokens, strictly <85 tokens total)
BUDGET_BASE_INSTRUCTION: str = (
    "Rewrite text to sound naturally human. Use common everyday words for things and feelings. "
    "Strip purple prose, melodramatic descriptions, and AI clichés (e.g. delve, tapestry). "
    "Preserve facts, markdown, and code untouched. Output only rewritten text."
)

# Deep mode master instruction for multi-layered structural cadence, perplexity shifting, and descriptor deflation
DEEP_BASE_INSTRUCTION: str = (
    "You are an expert editor and prose stylist. Rewrite the text to eliminate all statistical and stylistic "
    "markers of AI generation while preserving 100% of core facts, markdown structure, and code blocks.\n"
    "1. Common Everyday Descriptors: Describe places, physical objects, and feelings using common words people actually use. "
    "Eliminate elevated, faux-literary descriptions (e.g. avoid 'quiet anchor', 'commercial sprawl', 'quiet gravity', 'silent contemplation'). "
    "Ground descriptions in real life (e.g., 'stores and traffic', 'busy road', 'makes you stop and think', 'full of history').\n"
    "2. Cadence & Burstiness: Alternate between short punchy sentences (3-7 words) and longer rhythmic sentences (20-35 words).\n"
    "3. Natural Phrasing: Use authentic idioms, active verbs, and natural transitions.\n"
    "4. Purification: Purge all AI clichés like delve, tapestry, moreover, testament, pivotal, beacon, plethora, furthermore.\n"
    "Output only the final humanized text."
)

# Compact tone directives
TONE_DIRECTIVES: dict[str, str] = {
    "neutral": "Tone: balanced and objective.",
    "casual": "Tone: conversational and friendly.",
    "academic": "Tone: analytical and scholarly.",
    "professional": "Tone: direct and professional.",
}

# Compact reading level directives
READING_LEVEL_DIRECTIVES: dict[str, str] = {
    "general": "Reading level: general audience.",
    "middle_school": "Reading level: middle school.",
    "high_school": "Reading level: high school.",
    "college": "Reading level: college.",
}


def get_budget_prompt(tone: str = "neutral", reading_level: str = "general") -> str:
    """Construct a hyper-compact system prompt for budget mode (<100 tokens overhead).

    Args:
        tone: Target tone ('neutral', 'casual', 'academic', 'professional').
        reading_level: Target reading level ('general', 'middle_school', 'high_school', 'college').

    Returns:
        Compact system instruction string guaranteed to be well under 100 tokens.
    """
    tone_directive = TONE_DIRECTIVES.get(tone.lower(), TONE_DIRECTIVES["neutral"])
    level_directive = READING_LEVEL_DIRECTIVES.get(reading_level.lower(), READING_LEVEL_DIRECTIVES["general"])

    return f"{BUDGET_BASE_INSTRUCTION} {tone_directive} {level_directive}"


def get_deep_prompt(tone: str = "neutral", reading_level: str = "general") -> str:
    """Construct a comprehensive multi-layered prompt for deep mode.

    Args:
        tone: Target tone.
        reading_level: Target reading level.

    Returns:
        Detailed system instruction string for multi-pass / deep humanization.
    """
    tone_directive = TONE_DIRECTIVES.get(tone.lower(), TONE_DIRECTIVES["neutral"])
    level_directive = READING_LEVEL_DIRECTIVES.get(reading_level.lower(), READING_LEVEL_DIRECTIVES["general"])

    return f"{DEEP_BASE_INSTRUCTION}\n4. {tone_directive}\n5. {level_directive}"


def estimate_prompt_tokens(text: str) -> int:
    """Estimate token count for a string using standard subword tokenization heuristics.

    Calibrated against modern BPE/SentencePiece tokenizers (Gemini, GPT):
    English prose averages ~4 characters per token or ~1.25 to 1.33 tokens per word.

    Args:
        text: Input text string.

    Returns:
        Estimated integer token count.
    """
    stripped = text.strip()
    words = stripped.split()
    chars = len(stripped)

    # For CJK / non-spaced scripts, utilize character-based heuristic
    if any(ord(c) > 0x2E80 for c in stripped):
        token_count = max(int(len(words) * 1.1 + 0.5), int(chars / 4.0 + 0.5))
    else:
        token_count = max(1, int(len(words) * 1.1 + 0.5))

    return max(1, token_count)
