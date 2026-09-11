"""Pure-Python Flesch-Kincaid Grade Level and Flesch Reading Ease calculations.

Zero external dependencies. Strips markdown fences, tables, and inline code
before computing linguistic readability scores.
"""

from __future__ import annotations

import re


def count_syllables(word: str) -> int:
    """Count syllables in an English word using phonetic heuristic rules.

    Args:
        word: A single word string.

    Returns:
        Estimated syllable count (minimum 1 for non-empty word).
    """
    clean_word = word.lower().strip()
    clean_word = re.sub(r"[^a-z]", "", clean_word)
    if not clean_word:
        return 0
    if len(clean_word) <= 3:
        return 1

    # Normalize common endings
    # Silent 'e' at end (unless 'le' preceded by consonant)
    if clean_word.endswith("e") and not clean_word.endswith("le"):
        clean_word = clean_word[:-1]

    # Trailing '-ed' usually doesn't add a syllable unless preceded by t or d (e.g., 'started', 'needed')
    if clean_word.endswith("ed") and not clean_word.endswith(("ted", "ded")):
        clean_word = clean_word[:-2]

    # Trailing '-es' usually doesn't add a syllable unless preceded by s, z, x, ch, sh
    if clean_word.endswith("es") and not clean_word.endswith(("ses", "zes", "xes", "ches", "shes")):
        clean_word = clean_word[:-2]

    if not clean_word:
        return 1

    # Treat 'y' at word start as consonant, elsewhere as vowel
    if clean_word.startswith("y"):
        clean_word = clean_word[1:]

    # Count vowel groups [aeiouy]+
    vowel_groups = re.findall(r"[aeiouy]+", clean_word)
    count = len(vowel_groups)

    return max(1, count)


def _strip_markdown_and_code(text: str) -> str:
    """Remove code blocks, inline code, URLs, and table markup for fair readability scoring."""
    # Remove triple backtick code blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Remove inline backticks
    text = re.sub(r"`[^`\n]+`", " ", text)
    # Remove markdown link URLs [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown image tags ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Remove horizontal rules
    text = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", " ", text, flags=re.MULTILINE)
    # Remove markdown table delimiter lines |---|---|
    text = re.sub(r"\|[:\-\s|]+\|", " ", text)
    # Remove table pipe characters
    text = re.sub(r"\|", " ", text)
    return text


def calculate_readability(text: str) -> dict[str, float]:
    """Calculate Flesch Reading Ease and Flesch-Kincaid Grade Level scores.

    Args:
        text: Input text string (can include markdown).

    Returns:
        Dictionary containing:
            - 'flesch_reading_ease': 0.0 to 100.0+ (higher = easier to read)
            - 'flesch_kincaid_grade': estimated U.S. school grade level (e.g. 8.2)
            - 'word_count': total words analyzed
            - 'sentence_count': total sentences analyzed
            - 'syllable_count': total syllables counted
    """
    clean_text = _strip_markdown_and_code(text)

    # Word extraction (alphabetic tokens)
    words = re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", clean_text)
    # Sentence splitting (terminal punctuation followed by whitespace or EOF, avoiding decimals)
    raw_sentences = re.split(r"(?<=[.!?])\s+", clean_text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip() and re.search(r"[a-zA-Z]", s)]

    if not words or not sentences:
        return {
            "flesch_reading_ease": 100.0,
            "flesch_kincaid_grade": 0.0,
            "word_count": 0.0,
            "sentence_count": 0.0,
            "syllable_count": 0.0,
        }

    total_words = len(words)
    total_sentences = len(sentences)
    total_syllables = sum(count_syllables(w) for w in words)

    words_per_sentence = total_words / total_sentences
    syllables_per_word = total_syllables / total_words

    # Flesch Reading Ease: 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    fre = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    # Flesch-Kincaid Grade Level: 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    fkgl = (0.39 * words_per_sentence) + (11.8 * syllables_per_word) - 15.59

    clamped_fre = max(0.0, min(100.0, round(fre, 1)))

    return {
        "flesch_reading_ease": clamped_fre,
        "flesch_kincaid_grade": max(0.0, round(fkgl, 1)),
        "word_count": float(total_words),
        "sentence_count": float(total_sentences),
        "syllable_count": float(total_syllables),
    }


def calculate_flesch_reading_ease(text: str) -> float:
    """Convenience helper returning only the Flesch Reading Ease score."""
    return calculate_readability(text)["flesch_reading_ease"]


def calculate_flesch_kincaid_grade(text: str) -> float:
    """Convenience helper returning only the Flesch-Kincaid Grade Level score."""
    return calculate_readability(text)["flesch_kincaid_grade"]
