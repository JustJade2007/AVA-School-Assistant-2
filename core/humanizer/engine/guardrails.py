"""Quality guardrails, zero-tolerance banned AI buzzwords audit, and grammar sanitizer.

Enforces zero banned AI clichés in generated or processed text through rigorous
pattern detection and case-preserving automated heuristic replacements.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import NamedTuple

# Boundaries that treat markdown formatting characters (like '_', '*', '~') as delimiters
# while preventing partial matches inside larger alphanumeric words.
_WB_LEFT = r"(?<![a-zA-Z0-9])"
_WB_RIGHT = r"(?![a-zA-Z0-9])"

# Catalog of regex patterns matching banned AI buzzwords, phrases, and clichés
BANNED_AI_TERMS: list[str] = [
    # Verbs / Verb Phrases
    rf"{_WB_LEFT}delv(?:e|es|ed|ing)(?:\s+into)?{_WB_RIGHT}",
    rf"{_WB_LEFT}showcas(?:e|es|ed|ing){_WB_RIGHT}",
    rf"{_WB_LEFT}underscor(?:e|es|ed|ing){_WB_RIGHT}",
    rf"{_WB_LEFT}harness(?:es|ed|ing)?{_WB_RIGHT}",
    rf"{_WB_LEFT}foster(?:s|ed|ing)?{_WB_RIGHT}",
    rf"{_WB_LEFT}garner(?:s|ed|ing)?{_WB_RIGHT}",
    rf"{_WB_LEFT}illuminat(?:e|es|ed|ing){_WB_RIGHT}",
    rf"{_WB_LEFT}shed(?:s)?\s+light\s+on{_WB_RIGHT}",
    rf"{_WB_LEFT}serves?\s+as\s+a\s+(?:testament|reminder|beacon)(?:\s+(?:to|of))?{_WB_RIGHT}",
    # Nouns / Metaphors
    rf"{_WB_LEFT}tapestr(?:y|ies)(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}beacon(?:s)?(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}testament(?:s)?(?:\s+to)?{_WB_RIGHT}",
    rf"{_WB_LEFT}plethora(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}myriad(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}realm(?:s)?(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}crucible{_WB_RIGHT}",
    rf"{_WB_LEFT}cornerstone{_WB_RIGHT}",
    rf"{_WB_LEFT}linchpin{_WB_RIGHT}",
    rf"{_WB_LEFT}symphon(?:y|ies)(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}interplay(?:\s+of)?{_WB_RIGHT}",
    rf"{_WB_LEFT}paradigm\s+shift{_WB_RIGHT}",
    rf"{_WB_LEFT}game[- ]changer{_WB_RIGHT}",
    # Adjectives / Adverbs
    rf"{_WB_LEFT}multi[- ]?faceted{_WB_RIGHT}",
    rf"{_WB_LEFT}nuanc(?:e|es|ed|ing){_WB_RIGHT}",
    rf"{_WB_LEFT}pivotal{_WB_RIGHT}",
    rf"{_WB_LEFT}quintessential{_WB_RIGHT}",
    rf"{_WB_LEFT}seamless(?:ly)?{_WB_RIGHT}",
    rf"{_WB_LEFT}meticulous(?:ly)?{_WB_RIGHT}",
    rf"{_WB_LEFT}bespoke{_WB_RIGHT}",
    rf"{_WB_LEFT}transformative{_WB_RIGHT}",
    rf"{_WB_LEFT}vibrant{_WB_RIGHT}",
    rf"{_WB_LEFT}bustling{_WB_RIGHT}",
    rf"{_WB_LEFT}paramount{_WB_RIGHT}",
    rf"{_WB_LEFT}invaluable{_WB_RIGHT}",
    rf"{_WB_LEFT}groundbreaking{_WB_RIGHT}",
    rf"{_WB_LEFT}nascent{_WB_RIGHT}",
    rf"{_WB_LEFT}inextricably{_WB_RIGHT}",
    # Formulaic Transitions
    rf"{_WB_LEFT}moreover{_WB_RIGHT}",
    rf"{_WB_LEFT}furthermore{_WB_RIGHT}",
    rf"{_WB_LEFT}in\s+summary{_WB_RIGHT}",
    rf"{_WB_LEFT}in\s+conclusion{_WB_RIGHT}",
    rf"{_WB_LEFT}to\s+sum\s+up{_WB_RIGHT}",
    rf"{_WB_LEFT}it\s+is\s+worth\s+noting\s+that{_WB_RIGHT}",
    rf"{_WB_LEFT}it\s+is\s+important\s+to\s+remember\s+that{_WB_RIGHT}",
    rf"{_WB_LEFT}by\s+and\s+large{_WB_RIGHT}",
]

# Replacement rules mapping specific regex patterns to human-sounding alternatives
REPLACEMENT_RULES: list[tuple[str, str]] = [
    # Multi-word phrases first (order matters: specific phrases before general words)
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+testament\s+to{_WB_RIGHT}", "shows"),
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+testament{_WB_RIGHT}", "stands as proof"),
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+beacon\s+of{_WB_RIGHT}", "represents"),
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+beacon{_WB_RIGHT}", "stands as a guide"),
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+reminder\s+of{_WB_RIGHT}", "reminds us of"),
    (rf"{_WB_LEFT}serves?\s+as\s+a\s+reminder{_WB_RIGHT}", "reminds us"),
    (rf"{_WB_LEFT}it\s+is\s+worth\s+noting\s+that{_WB_RIGHT}", "notably,"),
    (rf"{_WB_LEFT}it\s+is\s+important\s+to\s+remember\s+that{_WB_RIGHT}", "keep in mind,"),
    (rf"{_WB_LEFT}shed(?:s)?\s+light\s+on{_WB_RIGHT}", "clarifies"),
    (rf"{_WB_LEFT}paradigm\s+shift{_WB_RIGHT}", "major change"),
    (rf"{_WB_LEFT}game[- ]changer{_WB_RIGHT}", "breakthrough"),
    (rf"{_WB_LEFT}by\s+and\s+large{_WB_RIGHT}", "overall"),

    # Delve variations
    (rf"{_WB_LEFT}delving\s+into{_WB_RIGHT}", "exploring"),
    (rf"{_WB_LEFT}delves\s+into{_WB_RIGHT}", "explores"),
    (rf"{_WB_LEFT}delved\s+into{_WB_RIGHT}", "explored"),
    (rf"{_WB_LEFT}delve\s+into{_WB_RIGHT}", "explore"),
    (rf"{_WB_LEFT}delving{_WB_RIGHT}", "digging"),
    (rf"{_WB_LEFT}delves{_WB_RIGHT}", "digs"),
    (rf"{_WB_LEFT}delved{_WB_RIGHT}", "dug"),
    (rf"{_WB_LEFT}delve{_WB_RIGHT}", "dig"),

    # Tapestry variations
    (rf"{_WB_LEFT}tapestry\s+of{_WB_RIGHT}", "blend of"),
    (rf"{_WB_LEFT}tapestries\s+of{_WB_RIGHT}", "blends of"),
    (rf"{_WB_LEFT}tapestries{_WB_RIGHT}", "fabrics"),
    (rf"{_WB_LEFT}tapestry{_WB_RIGHT}", "fabric"),

    # Transitions (with and without commas)
    (rf"{_WB_LEFT}moreover,\s*{_WB_RIGHT}", "also, "),
    (rf"{_WB_LEFT}moreover{_WB_RIGHT}", "plus"),
    (rf"{_WB_LEFT}furthermore,\s*{_WB_RIGHT}", "what's more, "),
    (rf"{_WB_LEFT}furthermore{_WB_RIGHT}", "in addition"),
    (rf"{_WB_LEFT}in\s+summary,\s*{_WB_RIGHT}", "overall, "),
    (rf"{_WB_LEFT}in\s+summary{_WB_RIGHT}", "in short"),
    (rf"{_WB_LEFT}in\s+conclusion,\s*{_WB_RIGHT}", "in the end, "),
    (rf"{_WB_LEFT}in\s+conclusion{_WB_RIGHT}", "ultimately"),
    (rf"{_WB_LEFT}to\s+sum\s+up,\s*{_WB_RIGHT}", "in short, "),
    (rf"{_WB_LEFT}to\s+sum\s+up{_WB_RIGHT}", "briefly"),

    # Testament
    (rf"{_WB_LEFT}testament\s+to{_WB_RIGHT}", "proof of"),
    (rf"{_WB_LEFT}testaments\s+to{_WB_RIGHT}", "proofs of"),
    (rf"{_WB_LEFT}testament{_WB_RIGHT}", "proof"),
    (rf"{_WB_LEFT}testaments{_WB_RIGHT}", "proofs"),

    # Multifaceted & Nuanced
    (rf"{_WB_LEFT}multi[- ]?faceted{_WB_RIGHT}", "complex"),
    (rf"{_WB_LEFT}nuanced{_WB_RIGHT}", "subtle"),
    (rf"{_WB_LEFT}nuances{_WB_RIGHT}", "subtleties"),
    (rf"{_WB_LEFT}nuance{_WB_RIGHT}", "subtlety"),

    # Noun clusters
    (rf"{_WB_LEFT}plethora\s+of{_WB_RIGHT}", "wide variety of"),
    (rf"{_WB_LEFT}plethora{_WB_RIGHT}", "abundance"),
    (rf"{_WB_LEFT}myriad\s+of{_WB_RIGHT}", "wide range of"),
    (rf"{_WB_LEFT}myriad{_WB_RIGHT}", "countless"),
    (rf"{_WB_LEFT}realm\s+of{_WB_RIGHT}", "field of"),
    (rf"{_WB_LEFT}realms\s+of{_WB_RIGHT}", "fields of"),
    (rf"{_WB_LEFT}realm{_WB_RIGHT}", "field"),
    (rf"{_WB_LEFT}realms{_WB_RIGHT}", "fields"),
    (rf"{_WB_LEFT}pivotal{_WB_RIGHT}", "key"),
    (rf"{_WB_LEFT}beacon\s+of{_WB_RIGHT}", "symbol of"),
    (rf"{_WB_LEFT}beacon{_WB_RIGHT}", "guide"),
    (rf"{_WB_LEFT}beacons{_WB_RIGHT}", "guides"),
    (rf"{_WB_LEFT}crucible{_WB_RIGHT}", "severe test"),
    (rf"{_WB_LEFT}cornerstone{_WB_RIGHT}", "foundation"),
    (rf"{_WB_LEFT}linchpin{_WB_RIGHT}", "backbone"),

    # Symphony (plural and singular symmetry)
    (rf"{_WB_LEFT}symphonies\s+of{_WB_RIGHT}", "harmonies of"),
    (rf"{_WB_LEFT}symphony\s+of{_WB_RIGHT}", "harmony of"),
    (rf"{_WB_LEFT}symphonies{_WB_RIGHT}", "concerts"),
    (rf"{_WB_LEFT}symphony{_WB_RIGHT}", "concert"),

    # Stylistic descriptors
    (rf"{_WB_LEFT}interplay\s+of{_WB_RIGHT}", "interaction of"),
    (rf"{_WB_LEFT}interplay{_WB_RIGHT}", "interaction"),
    (rf"{_WB_LEFT}quintessential{_WB_RIGHT}", "classic"),
    (rf"{_WB_LEFT}seamlessly{_WB_RIGHT}", "smoothly"),
    (rf"{_WB_LEFT}seamless{_WB_RIGHT}", "smooth"),
    (rf"{_WB_LEFT}meticulously{_WB_RIGHT}", "carefully"),
    (rf"{_WB_LEFT}meticulous{_WB_RIGHT}", "careful"),
    (rf"{_WB_LEFT}bespoke{_WB_RIGHT}", "custom"),
    (rf"{_WB_LEFT}transformative{_WB_RIGHT}", "impactful"),
    (rf"{_WB_LEFT}vibrant{_WB_RIGHT}", "lively"),
    (rf"{_WB_LEFT}bustling{_WB_RIGHT}", "busy"),
    (rf"{_WB_LEFT}paramount{_WB_RIGHT}", "vital"),
    (rf"{_WB_LEFT}invaluable{_WB_RIGHT}", "helpful"),
    (rf"{_WB_LEFT}groundbreaking{_WB_RIGHT}", "innovative"),
    (rf"{_WB_LEFT}nascent{_WB_RIGHT}", "early-stage"),
    (rf"{_WB_LEFT}inextricably{_WB_RIGHT}", "closely"),

    # Verbs with exact Subject-Verb Agreement separation
    (rf"{_WB_LEFT}showcasing{_WB_RIGHT}", "displaying"),
    (rf"{_WB_LEFT}showcased{_WB_RIGHT}", "displayed"),
    (rf"{_WB_LEFT}showcases{_WB_RIGHT}", "displays"),
    (rf"{_WB_LEFT}showcase{_WB_RIGHT}", "display"),

    (rf"{_WB_LEFT}underscoring{_WB_RIGHT}", "highlighting"),
    (rf"{_WB_LEFT}underscored{_WB_RIGHT}", "highlighted"),
    (rf"{_WB_LEFT}underscores{_WB_RIGHT}", "highlights"),
    (rf"{_WB_LEFT}underscore{_WB_RIGHT}", "highlight"),

    (rf"{_WB_LEFT}harnessing{_WB_RIGHT}", "using"),
    (rf"{_WB_LEFT}harnesses{_WB_RIGHT}", "uses"),
    (rf"{_WB_LEFT}harnessed{_WB_RIGHT}", "used"),
    (rf"{_WB_LEFT}harness{_WB_RIGHT}", "use"),

    (rf"{_WB_LEFT}fostering{_WB_RIGHT}", "encouraging"),
    (rf"{_WB_LEFT}fosters{_WB_RIGHT}", "encourages"),
    (rf"{_WB_LEFT}fostered{_WB_RIGHT}", "encouraged"),
    (rf"{_WB_LEFT}foster{_WB_RIGHT}", "encourage"),

    (rf"{_WB_LEFT}garnering{_WB_RIGHT}", "gaining"),
    (rf"{_WB_LEFT}garners{_WB_RIGHT}", "gains"),
    (rf"{_WB_LEFT}garnered{_WB_RIGHT}", "gained"),
    (rf"{_WB_LEFT}garner{_WB_RIGHT}", "gain"),

    (rf"{_WB_LEFT}illuminating{_WB_RIGHT}", "clarifying"),
    (rf"{_WB_LEFT}illuminates{_WB_RIGHT}", "clarifies"),
    (rf"{_WB_LEFT}illuminated{_WB_RIGHT}", "clarified"),
    (rf"{_WB_LEFT}illuminate{_WB_RIGHT}", "clarify"),
]


def audit_vocabulary(text: str) -> list[str]:
    """Scan text and return all occurrences of banned AI buzzwords and clichés.

    Args:
        text: Input string to audit.

    Returns:
        List of matched banned terms found (empty list if 100% clean).
    """
    violations: list[str] = []
    for pattern in BANNED_AI_TERMS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            violations.extend(matches)
    return violations


def _preserve_case(original: str, replacement: str) -> str:
    """Apply original word casing (Title case, UPPERCASE, sentence-initial, lowercase)."""
    if not original or not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original.istitle():
        return replacement.capitalize()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def replace_banned_buzzwords(text: str) -> tuple[str, list[str]]:
    """Audit and replace banned AI clichés with natural human alternatives.

    Preserves capitalization of the original words.

    Args:
        text: Input string.

    Returns:
        Tuple of (sanitized_text, list_of_replaced_terms).
    """
    replaced: list[str] = []
    current_text = text

    for pattern, replacement in REPLACEMENT_RULES:
        def _sub_callback(match: re.Match[str]) -> str:
            matched_str = match.group(0)
            replaced.append(matched_str)
            return _preserve_case(matched_str, replacement)

        current_text = re.sub(pattern, _sub_callback, current_text, flags=re.IGNORECASE)

    return current_text, replaced


@dataclass
class GrammarVerificationResult:
    """Result of automated grammar and punctuation sanitization."""

    is_valid: bool
    issues: list[str]
    repaired_text: str


# Whitelist of valid English reduplications (past-perfect, demonstratives, proper nouns)
VALID_REDUPLICATIONS: frozenset[str] = frozenset({
    "had",      # Past-perfect: "had had"
    "that",     # Demonstrative/relative: "that that"
    "bora",     # Proper noun: "Bora Bora"
    "pago",     # Proper noun: "Pago Pago"
    "walla",    # Proper noun: "Walla Walla"
    "baden",    # Proper noun: "Baden-Baden" / "Baden Baden"
    "sing",     # Proper noun: "Sing Sing"
    "aye",      # Idiom: "aye aye"
    "dum",      # Idiom: "dum dum"
    "yo",       # Idiom: "yo yo"
})

# Common abbreviations ending in period that do not terminate sentences
COMMON_ABBREVIATIONS: tuple[str, ...] = (
    "e.g", "eg", "i.e", "ie", "etc", "vs", "v", "al", "ca", "cf", "fig", "no", "dept", "approx", "inc", "ltd", "dr", "mr", "mrs", "ms"
)
ABBREVIATION_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9])(?:" + "|".join(re.escape(abbr) for abbr in COMMON_ABBREVIATIONS) + r")\.$",
    re.IGNORECASE,
)


def sanitize_and_verify_grammar(text: str) -> GrammarVerificationResult:
    """Run heuristic grammar, punctuation, and syntax verification and repair.

    Checks:
        1. Code fence markdown balance (```)
        2. Unmatched double quotation marks (")
        3. Double or multiple consecutive horizontal spaces ('  ' -> ' ')
        4. Extraneous space before punctuation marks (e.g. 'word , word' -> 'word, word')
        5. Duplicate commas (e.g. ',,' -> ',')
        6. Accidental word reduplication/stutter (with valid reduplication whitelist)
        7. Sentence initial capitalization after [.!?] (with abbreviation whitelist)
        8. Document initial letter capitalization

    Args:
        text: Input text.

    Returns:
        GrammarVerificationResult with is_valid flag, issues detected, and repaired text.
    """
    if not text:
        return GrammarVerificationResult(is_valid=True, issues=[], repaired_text=text)

    issues: list[str] = []
    repaired = text

    # 1. Check markdown code fence balance
    backtick_count = repaired.count("```")
    if backtick_count % 2 != 0:
        issues.append(f"Unmatched markdown code fence: found {backtick_count} fences.")
        repaired = repaired + "\n```\n"

    # 2. Check and balance unmatched double quotation marks
    if repaired.count('"') % 2 != 0:
        issues.append('Unmatched quotation mark (") detected.')
        if repaired.endswith("\n"):
            stripped = repaired.rstrip("\r\n")
            trailing = repaired[len(stripped):]
            repaired = stripped + '"' + trailing
        else:
            repaired = repaired + '"'

    # 3. Replace em-dash ('—') with a space
    if "—" in repaired:
        issues.append("Em-dash (—) detected and replaced with space.")
        repaired = repaired.replace("—", " ")

    # 4. Collapse double and multiple horizontal spaces: 'word  word' -> 'word word' (preserve leading indentation)
    double_spaces = re.compile(r"(?<=\S)[ \t]{2,}")
    if double_spaces.search(repaired):
        issues.append("Extraneous consecutive whitespace detected.")
        repaired = double_spaces.sub(" ", repaired)

    # 4. Fix space before punctuation marks: 'word , word' -> 'word, word'
    space_punct = re.compile(r"(\w+)\s+([,.:;?!])")
    if space_punct.search(repaired):
        issues.append("Extraneous whitespace before punctuation.")
        repaired = space_punct.sub(r"\1\2", repaired)

    # 5. Fix duplicate commas: ',,' -> ','
    if ",," in repaired:
        issues.append("Duplicate commas detected.")
        repaired = re.sub(r",,+", ",", repaired)

    # 6. Fix accidental word reduplication (stutter) with whitelist and triple-stutter reduction
    redup_pattern = re.compile(r"\b([a-zA-Z]{2,})(?:\s+\1)+\b", re.IGNORECASE)
    stutter_found = False

    def _replace_reduplication(m: re.Match[str]) -> str:
        nonlocal stutter_found
        word = m.group(1)
        tokens = re.split(r"\s+", m.group(0))
        word_lower = word.lower()

        if word_lower in VALID_REDUPLICATIONS:
            if len(tokens) == 2:
                # Valid reduplication: "had had", "that that", "Bora Bora"
                return m.group(0)
            else:
                # Stutter of a valid word (3+ repetitions): reduce to 2
                stutter_found = True
                return f"{tokens[0]} {tokens[1]}"
        else:
            # Accidental stutter: reduce to 1
            stutter_found = True
            return tokens[0]

    repaired = redup_pattern.sub(_replace_reduplication, repaired)
    if stutter_found:
        issues.append("Accidental word reduplication (stutter) detected.")

    # 7. Fix sentence capitalization after [.!?]\s+ with abbreviation protection
    cap_detected = False

    def _cap_match(m: re.Match[str]) -> str:
        nonlocal cap_detected
        prefix = m.group(1)
        char = m.group(2)

        # Only period (.) can be an abbreviation, not ! or ?
        first_punct = prefix.strip()[0]
        if first_punct == ".":
            # Check if text immediately preceding the period is a known abbreviation
            preceding_text = m.string[:m.start() + 1]
            if ABBREVIATION_PATTERN.search(preceding_text):
                # Preceded by abbreviation like 'e.g.' or 'i.e.' -> leave lowercase
                return m.group(0)

        cap_detected = True
        return prefix + char.upper()

    cap_pattern = re.compile(r"([.!?]\s+)([a-z])")
    repaired = cap_pattern.sub(_cap_match, repaired)
    if cap_detected:
        issues.append("Sentence initial lowercase character detected.")

    # 8. Ensure first letter of text is capitalized if alphabetic
    first_char_match = re.match(r"^(\s*)([a-z])", repaired)
    if first_char_match:
        issues.append("Text starts with lowercase letter.")
        repaired = (
            first_char_match.group(1)
            + first_char_match.group(2).upper()
            + repaired[first_char_match.end():]
        )

    is_valid = len(issues) == 0
    return GrammarVerificationResult(
        is_valid=is_valid,
        issues=issues,
        repaired_text=repaired,
    )
