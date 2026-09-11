"""Thesaurus filtering engine for de-inflating melodramatic descriptors and purple prose.

Transforms pseudo-profound, overly-sentimental AI descriptors and purple prose
into grounded, natural human phrasing.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_WB_LEFT = r"(?<![a-zA-Z0-9])"
_WB_RIGHT = r"(?![a-zA-Z0-9])"

# Comprehensive catalog of melodramatic AI descriptors, purple prose, and inflated phrasing
# Order is critical: longer, more specific multi-word phrases appear before shorter phrases.
THESAURUS_DEFLATE_RULES: list[tuple[str, str]] = [
    # 1. Melodramatic confrontation, gravity, and history clichés
    (
        rf"{_WB_LEFT}forces?\s+a\s+confrontation\s+with\s+the\s+quiet\s+gravity\s+of\s+a\s+history\s+largely\s+paved\s+over\s+by\s+modern\s+progress{_WB_RIGHT}",
        "makes you face a history mostly lost to modern development",
    ),
    (
        rf"{_WB_LEFT}forces?\s+a\s+confrontation\s+with\s+the\s+quiet\s+gravity\s+of{_WB_RIGHT}",
        "makes you face the real weight of",
    ),
    (
        rf"{_WB_LEFT}forced\s+a\s+confrontation\s+with\s+the\s+quiet\s+gravity\s+of{_WB_RIGHT}",
        "made you face the real weight of",
    ),
    (
        rf"{_WB_LEFT}forcing\s+a\s+confrontation\s+with\s+the\s+quiet\s+gravity\s+of{_WB_RIGHT}",
        "making you face the real weight of",
    ),
    (
        rf"{_WB_LEFT}forces?\s+a\s+confrontation\s+with{_WB_RIGHT}",
        "makes you face",
    ),
    (
        rf"{_WB_LEFT}forced\s+a\s+confrontation\s+with{_WB_RIGHT}",
        "made you face",
    ),
    (
        rf"{_WB_LEFT}forcing\s+a\s+confrontation\s+with{_WB_RIGHT}",
        "making you face",
    ),
    (
        rf"{_WB_LEFT}the\s+quiet\s+gravity\s+of{_WB_RIGHT}",
        "the real weight of",
    ),
    (
        rf"{_WB_LEFT}quiet\s+gravity{_WB_RIGHT}",
        "real weight",
    ),
    (
        rf"{_WB_LEFT}largely\s+paved\s+over\s+by\s+modern\s+progress{_WB_RIGHT}",
        "mostly lost to modern development",
    ),
    (
        rf"{_WB_LEFT}paved\s+over\s+by\s+modern\s+progress{_WB_RIGHT}",
        "covered up by modern development",
    ),
    (
        rf"{_WB_LEFT}modern\s+progress{_WB_RIGHT}",
        "modern development",
    ),

    # 2. Sentimental contemplation & landscape clichés
    (
        rf"{_WB_LEFT}the\s+stoic,\s+lined\s+face\s+of\s+an\s+Indigenous\s+person{_WB_RIGHT}",
        "the weathered, lined face of an Indigenous man",
    ),
    (
        rf"{_WB_LEFT}the\s+stoic,\s+lined\s+face\s+of{_WB_RIGHT}",
        "the weathered face of",
    ),
    (
        rf"{_WB_LEFT}stoic,\s+lined\s+face{_WB_RIGHT}",
        "weathered, lined face",
    ),
    (
        rf"{_WB_LEFT}outstretched\s+wings{_WB_RIGHT}",
        "spread wings",
    ),
    (
        rf"{_WB_LEFT}my\s+mind\s+drifted\s+to\s+the\s+impermanence\s+of\s+human\s+footprints\s+on\s+the\s+landscape{_WB_RIGHT}",
        "I started thinking about how quickly what we build disappears from the land",
    ),
    (
        rf"{_WB_LEFT}my\s+mind\s+drifted\s+to\s+the\s+impermanence\s+of{_WB_RIGHT}",
        "I started thinking about how temporary",
    ),
    (
        rf"{_WB_LEFT}my\s+mind\s+drifted\s+to{_WB_RIGHT}",
        "I started thinking about",
    ),
    (
        rf"{_WB_LEFT}the\s+impermanence\s+of\s+human\s+footprints\s+on\s+the\s+landscape{_WB_RIGHT}",
        "how quickly human footprints disappear from the land",
    ),
    (
        rf"{_WB_LEFT}the\s+impermanence\s+of\s+human\s+footprints{_WB_RIGHT}",
        "how temporary human footprints are",
    ),
    (
        rf"{_WB_LEFT}impermanence\s+of\s+human\s+footprints{_WB_RIGHT}",
        "temporary nature of human traces",
    ),
    (
        rf"{_WB_LEFT}the\s+impermanence\s+of{_WB_RIGHT}",
        "how temporary",
    ),
    (
        rf"{_WB_LEFT}impermanence\s+of{_WB_RIGHT}",
        "temporary nature of",
    ),
    (
        rf"{_WB_LEFT}human\s+footprints\s+on\s+the\s+landscape{_WB_RIGHT}",
        "human traces on the land",
    ),
    (
        rf"{_WB_LEFT}human\s+footprints{_WB_RIGHT}",
        "our presence",
    ),
    (
        rf"{_WB_LEFT}found\s+in\s+metropolitan\s+plazas,\s+which\s+often\s+celebrate\s+political\s+triumph{_WB_RIGHT}",
        "in city plazas celebrating political victories",
    ),
    (
        rf"{_WB_LEFT}metropolitan\s+plazas{_WB_RIGHT}",
        "city plazas",
    ),
    (
        rf"{_WB_LEFT}political\s+triumph{_WB_RIGHT}",
        "political victories",
    ),
    (
        rf"{_WB_LEFT}burdened\s+with\s+remembrance{_WB_RIGHT}",
        "heavy with memory",
    ),
    (
        rf"{_WB_LEFT}burdened\s+with\b",
        "heavy with",
    ),

    # 3. Heritage & vulnerability clichés
    (
        rf"{_WB_LEFT}the\s+texture\s+of\s+the\s+wood,\s+showing\s+signs\s+of\s+weathering\s+and\s+aging,\s+mirrors\s+the\s+vulnerability\s+of\s+the\s+heritage\s+it\s+seeks\s+to\s+honor{_WB_RIGHT}",
        "the weathered wood shows just how fragile that history really is",
    ),
    (
        rf"{_WB_LEFT}mirrors\s+the\s+vulnerability\s+of\s+the\s+heritage\s+it\s+seeks\s+to\s+honor{_WB_RIGHT}",
        "shows how fragile that history really is",
    ),
    (
        rf"{_WB_LEFT}mirrors\s+the\s+vulnerability\s+of{_WB_RIGHT}",
        "shows how fragile",
    ),
    (
        rf"{_WB_LEFT}vulnerability\s+of\s+the\s+heritage{_WB_RIGHT}",
        "fragility of that heritage",
    ),
    (
        rf"{_WB_LEFT}the\s+heritage\s+it\s+seeks\s+to\s+honor{_WB_RIGHT}",
        "the history it honors",
    ),
    (
        rf"{_WB_LEFT}seeks\s+to\s+honor{_WB_RIGHT}",
        "aims to honor",
    ),
    (
        rf"{_WB_LEFT}noting\s+the\s+inclusion\s+of{_WB_RIGHT}",
        "mentioning",
    ),

    # 4. Dialogue and temporal link clichés
    (
        rf"{_WB_LEFT}the\s+dialogue\s+established\s+between\s+the\s+past\s+creators\s+and\s+an\s+unpredictable\s+future{_WB_RIGHT}",
        "the connection between the people who made it and whatever comes next",
    ),
    (
        rf"{_WB_LEFT}dialogue\s+established\s+between\s+the\s+past\s+creators\s+and\s+an\s+unpredictable\s+future{_WB_RIGHT}",
        "connection between past generations and the future",
    ),
    (
        rf"{_WB_LEFT}dialogue\s+established\s+between{_WB_RIGHT}",
        "connection between",
    ),
    (
        rf"{_WB_LEFT}past\s+creators\s+and\s+an\s+unpredictable\s+future{_WB_RIGHT}",
        "past generations and the future",
    ),
    (
        rf"{_WB_LEFT}past\s+creators{_WB_RIGHT}",
        "the people who made it",
    ),
    (
        rf"{_WB_LEFT}unpredictable\s+future{_WB_RIGHT}",
        "future",
    ),
    (
        rf"{_WB_LEFT}localized\s+historical\s+marker{_WB_RIGHT}",
        "local historic marker",
    ),

    # 5. Emotional anchor & commercial environment clichés
    (
        rf"{_WB_LEFT}it\s+acts\s+as\s+an\s+emotional\s+anchor\s+in\s+a\s+rapidly\s+commercialized\s+environment{_WB_RIGHT}",
        "it sits right in the middle of all the busy stores and traffic",
    ),
    (
        rf"{_WB_LEFT}acts\s+as\s+an\s+emotional\s+anchor\s+in\s+a\s+rapidly\s+commercialized\s+environment{_WB_RIGHT}",
        "sits right in the middle of all the busy stores and traffic",
    ),
    (
        rf"{_WB_LEFT}stands\s+as\s+a\s+quiet\s+anchor\s+amid\s+all\s+the\s+commercial\s+sprawl{_WB_RIGHT}",
        "sits right in the middle of all the busy stores and traffic",
    ),
    (
        rf"{_WB_LEFT}it\s+acts\s+as\s+an\s+emotional\s+anchor{_WB_RIGHT}",
        "it sits right in the middle of everything",
    ),
    (
        rf"{_WB_LEFT}acts\s+as\s+an\s+emotional\s+anchor{_WB_RIGHT}",
        "sits right in the middle of things",
    ),
    (
        rf"{_WB_LEFT}stands\s+as\s+a\s+quiet\s+anchor{_WB_RIGHT}",
        "stands right in the middle of things",
    ),
    (
        rf"{_WB_LEFT}a\s+quiet\s+anchor{_WB_RIGHT}",
        "a calm spot",
    ),
    (
        rf"{_WB_LEFT}quiet\s+anchor{_WB_RIGHT}",
        "calm spot",
    ),
    (
        rf"{_WB_LEFT}an\s+emotional\s+anchor{_WB_RIGHT}",
        "a calm spot",
    ),
    (
        rf"{_WB_LEFT}in\s+a\s+rapidly\s+commercialized\s+environment{_WB_RIGHT}",
        "surrounded by stores and traffic",
    ),
    (
        rf"{_WB_LEFT}amid\s+all\s+the\s+commercial\s+sprawl{_WB_RIGHT}",
        "surrounded by stores and traffic",
    ),
    (
        rf"{_WB_LEFT}the\s+commercial\s+sprawl{_WB_RIGHT}",
        "all the busy stores and traffic",
    ),
    (
        rf"{_WB_LEFT}commercial\s+sprawl{_WB_RIGHT}",
        "busy stores and traffic",
    ),
    (
        rf"{_WB_LEFT}rapidly\s+commercialized\s+environment{_WB_RIGHT}",
        "busy area with stores and traffic",
    ),
    (
        rf"{_WB_LEFT}commercialized\s+environment{_WB_RIGHT}",
        "busy shopping area",
    ),

    # 6. Silent contemplation & traffic contrast clichés
    (
        rf"{_WB_LEFT}the\s+way\s+the\s+surrounding\s+traffic\s+rushes\s+past\s+while\s+this\s+giant\s+stands\s+frozen\s+in\s+silent\s+contemplation\s+created\s+a\s+jarring\s+contrast,\s+emphasizing\s+how\s+easily\s+contemporary\s+society\s+ignores\s+the\s+deep\s+cultural\s+roots\s+underlying\s+its\s+geography{_WB_RIGHT}",
        "traffic rushes past while this giant stands completely still, a strange contrast that shows how easily people today overlook the history beneath our feet",
    ),
    (
        rf"{_WB_LEFT}stands\s+frozen\s+in\s+silent\s+contemplation{_WB_RIGHT}",
        "stands completely still",
    ),
    (
        rf"{_WB_LEFT}frozen\s+in\s+silent\s+contemplation{_WB_RIGHT}",
        "standing completely still",
    ),
    (
        rf"{_WB_LEFT}silent\s+contemplation{_WB_RIGHT}",
        "standing quietly",
    ),
    (
        rf"{_WB_LEFT}created\s+a\s+jarring\s+contrast{_WB_RIGHT}",
        "was a strange contrast",
    ),
    (
        rf"{_WB_LEFT}a\s+jarring\s+contrast{_WB_RIGHT}",
        "a strange contrast",
    ),
    (
        rf"{_WB_LEFT}jarring\s+contrast{_WB_RIGHT}",
        "strange contrast",
    ),

    # 7. Contemporary society & cultural geography clichés
    (
        rf"{_WB_LEFT}emphasizing\s+how\s+easily\s+contemporary\s+society\s+ignores\s+the\s+deep\s+cultural\s+roots\s+underlying\s+its\s+geography{_WB_RIGHT}",
        "showing how easily people today overlook the history beneath our feet",
    ),
    (
        rf"{_WB_LEFT}emphasizing\s+how\s+easily\s+contemporary\s+society\s+ignores{_WB_RIGHT}",
        "showing how easily we overlook",
    ),
    (
        rf"{_WB_LEFT}contemporary\s+society\s+ignores{_WB_RIGHT}",
        "people today overlook",
    ),
    (
        rf"{_WB_LEFT}contemporary\s+society{_WB_RIGHT}",
        "people today",
    ),
    (
        rf"{_WB_LEFT}the\s+deep\s+cultural\s+roots\s+underlying\s+its\s+geography{_WB_RIGHT}",
        "the history beneath our feet",
    ),
    (
        rf"{_WB_LEFT}deep\s+cultural\s+roots\s+underlying\s+its\s+geography{_WB_RIGHT}",
        "the history of this place",
    ),
    (
        rf"{_WB_LEFT}cultural\s+roots\s+underlying\s+its\s+geography{_WB_RIGHT}",
        "history of this land",
    ),
    (
        rf"{_WB_LEFT}underlying\s+its\s+geography{_WB_RIGHT}",
        "beneath our feet",
    ),

    # 8. Effigy & forest material clichés
    (
        rf"{_WB_LEFT}resurrected\s+a\s+presence\s+from\s+the\s+earth\s+itself{_WB_RIGHT}",
        "brought a presence straight out of the earth",
    ),
    (
        rf"{_WB_LEFT}resurrected\s+a\s+presence\s+from{_WB_RIGHT}",
        "brought a presence out of",
    ),
    (
        rf"{_WB_LEFT}resurrect\s+a\s+presence{_WB_RIGHT}",
        "bring a presence to life",
    ),
    (
        rf"{_WB_LEFT}utilizing\s+the\s+very\s+material\s+of\s+the\s+forest\s+that\s+once\s+sustained\s+the\s+Calusa\s+people{_WB_RIGHT}",
        "using the same forest wood that once supported the Calusa people",
    ),
    (
        rf"{_WB_LEFT}utilizing\s+the\s+very\s+material\s+of\s+the\s+forest\s+that\s+once\s+sustained{_WB_RIGHT}",
        "using the same forest wood that once supported",
    ),
    (
        rf"{_WB_LEFT}utilizing\s+the\s+very\s+material\s+of{_WB_RIGHT}",
        "using the same material as",
    ),
    (
        rf"{_WB_LEFT}utilizing\s+the\s+very{_WB_RIGHT}",
        "using the very",
    ),

    # 9. Hollows of wooden eyes & accountability clichés
    (
        rf"{_WB_LEFT}contemplating\s+the\s+hollows\s+of\s+the\s+wooden\s+eyes{_WB_RIGHT}",
        "looking into the carved wooden eyes",
    ),
    (
        rf"{_WB_LEFT}contemplating\s+the\s+hollows\s+of{_WB_RIGHT}",
        "looking into",
    ),
    (
        rf"{_WB_LEFT}hollows\s+of\s+the\s+wooden\s+eyes{_WB_RIGHT}",
        "carved wooden eyes",
    ),
    (
        rf"{_WB_LEFT}distinct\s+sense\s+of\s+accountability{_WB_RIGHT}",
        "real sense of responsibility",
    ),
    (
        rf"{_WB_LEFT}sense\s+of\s+accountability{_WB_RIGHT}",
        "sense of responsibility",
    ),
    (
        rf"{_WB_LEFT}an\s+unspoken\s+reminder\s+that\s+the\s+land\s+we\s+inhabit\s+carries\s+stories\s+demanding\s+active\s+reflection\s+rather\s+than\s+passive\s+acknowledgment{_WB_RIGHT}",
        "a quiet reminder that this land carries stories that demand more than just a passing glance",
    ),
    (
        rf"{_WB_LEFT}demanding\s+active\s+reflection\s+rather\s+than\s+passive\s+acknowledgment{_WB_RIGHT}",
        "that ask for real thought, not just a passing glance",
    ),
    (
        rf"{_WB_LEFT}demanding\s+active\s+reflection{_WB_RIGHT}",
        "that ask for real thought",
    ),
    (
        rf"{_WB_LEFT}active\s+reflection\s+rather\s+than\s+passive\s+acknowledgment{_WB_RIGHT}",
        "real thought rather than a passing glance",
    ),
    (
        rf"{_WB_LEFT}active\s+reflection{_WB_RIGHT}",
        "real thought",
    ),
    (
        rf"{_WB_LEFT}passive\s+acknowledgment{_WB_RIGHT}",
        "a passing glance",
    ),
    (
        rf"{_WB_LEFT}the\s+land\s+we\s+inhabit{_WB_RIGHT}",
        "this land",
    ),

    # 10. Additional melodramatic purple prose descriptors
    (
        rf"{_WB_LEFT}a\s+poignant\s+reminder\s+of{_WB_RIGHT}",
        "a stark reminder of",
    ),
    (
        rf"{_WB_LEFT}poignant\s+reminder{_WB_RIGHT}",
        "clear reminder",
    ),
    (
        rf"{_WB_LEFT}profound\s+significance{_WB_RIGHT}",
        "real importance",
    ),
    (
        rf"{_WB_LEFT}enduring\s+testament{_WB_RIGHT}",
        "lasting proof",
    ),
    (
        rf"{_WB_LEFT}indelible\s+mark{_WB_RIGHT}",
        "lasting mark",
    ),
    (
        rf"{_WB_LEFT}steeped\s+in\s+history{_WB_RIGHT}",
        "rich with history",
    ),
    (
        rf"{_WB_LEFT}paints?\s+a\s+vivid\s+picture{_WB_RIGHT}",
        "gives a clear picture",
    ),
    (
        rf"{_WB_LEFT}at\s+the\s+intersection\s+of{_WB_RIGHT}",
        "where ... meet",
    ),
    (
        rf"{_WB_LEFT}resonates?\s+deeply\s+with{_WB_RIGHT}",
        "really hits home with",
    ),
    (
        rf"{_WB_LEFT}a\s+beacon\s+of\s+hope{_WB_RIGHT}",
        "a sign of hope",
    ),
    (
        rf"{_WB_LEFT}breathes?\s+new\s+life\s+into{_WB_RIGHT}",
        "revives",
    ),
    (
        rf"{_WB_LEFT}breathes?\s+life\s+into{_WB_RIGHT}",
        "brings to life",
    ),
    (
        rf"{_WB_LEFT}in\s+the\s+grand\s+scheme\s+of\s+things{_WB_RIGHT}",
        "in the end",
    ),
    (
        rf"{_WB_LEFT}navigating\s+the\s+complexities\s+of{_WB_RIGHT}",
        "dealing with",
    ),
    (
        rf"{_WB_LEFT}grapples?\s+with\s+the\s+reality\s+of{_WB_RIGHT}",
        "faces the reality of",
    ),
    (
        rf"{_WB_LEFT}unravel\s+the\s+mysteries\s+of{_WB_RIGHT}",
        "figure out",
    ),
    (
        rf"{_WB_LEFT}a\s+stark\s+manifestation\s+of{_WB_RIGHT}",
        "a clear sign of",
    ),
    (
        rf"{_WB_LEFT}woven\s+into\s+the\s+fabric\s+of\s+society{_WB_RIGHT}",
        "part of our daily lives",
    ),
    (
        rf"{_WB_LEFT}etched\s+into\s+the\s+fabric\s+of{_WB_RIGHT}",
        "part of",
    ),
    (
        rf"{_WB_LEFT}plays?\s+an\s+indispensable\s+role\s+in{_WB_RIGHT}",
        "is essential to",
    ),
    (
        rf"{_WB_LEFT}plays?\s+a\s+pivotal\s+role\s+in{_WB_RIGHT}",
        "plays a key role in",
    ),
    (
        rf"{_WB_LEFT}serves?\s+to\s+highlight{_WB_RIGHT}",
        "highlights",
    ),
    (
        rf"{_WB_LEFT}serves?\s+to\s+underscore{_WB_RIGHT}",
        "underscores",
    ),
    (
        rf"{_WB_LEFT}in\s+an\s+era\s+defined\s+by{_WB_RIGHT}",
        "in a time of",
    ),
    (
        rf"{_WB_LEFT}in\s+an\s+era\s+characterized\s+by{_WB_RIGHT}",
        "in a time of",
    ),
    (
        rf"{_WB_LEFT}in\s+today's\s+fast-paced\s+world{_WB_RIGHT}",
        "today",
    ),
    (
        rf"{_WB_LEFT}in\s+the\s+fast-paced\s+world\s+of{_WB_RIGHT}",
        "in the world of",
    ),
    (
        rf"{_WB_LEFT}it\s+is\s+paramount\s+that{_WB_RIGHT}",
        "it is vital that",
    ),
    (
        rf"{_WB_LEFT}it\s+is\s+imperative\s+that{_WB_RIGHT}",
        "it is essential that",
    ),
    (
        rf"{_WB_LEFT}embarks?\s+on\s+a\s+journey{_WB_RIGHT}",
        "sets out",
    ),

    # 11. Common wording for feelings, physical objects, and environments
    (
        rf"{_WB_LEFT}did\s+not\s+just\s+carve\s+an\s+effigy{_WB_RIGHT}",
        "did not just carve a wooden figure",
    ),
    (
        rf"{_WB_LEFT}carve\s+an\s+effigy{_WB_RIGHT}",
        "carve a wooden figure",
    ),
    (
        rf"{_WB_LEFT}an\s+effigy{_WB_RIGHT}",
        "a wooden figure",
    ),
    (
        rf"{_WB_LEFT}effigy{_WB_RIGHT}",
        "wooden figure",
    ),
    (
        rf"{_WB_LEFT}anchored\s+by\s+a\s+base\s+of{_WB_RIGHT}",
        "resting on a base of",
    ),
    (
        rf"{_WB_LEFT}palpable\s+sense\s+of{_WB_RIGHT}",
        "clear feeling of",
    ),
    (
        rf"{_WB_LEFT}palpable\s+tension{_WB_RIGHT}",
        "obvious tension",
    ),
    (
        rf"{_WB_LEFT}palpable{_WB_RIGHT}",
        "clear",
    ),
    (
        rf"{_WB_LEFT}visceral\s+reaction{_WB_RIGHT}",
        "gut reaction",
    ),
    (
        rf"{_WB_LEFT}visceral{_WB_RIGHT}",
        "gut",
    ),
    (
        rf"{_WB_LEFT}imbued\s+with\s+a\s+sense\s+of{_WB_RIGHT}",
        "filled with a feeling of",
    ),
    (
        rf"{_WB_LEFT}imbued\s+with{_WB_RIGHT}",
        "filled with",
    ),
    (
        rf"{_WB_LEFT}profound\s+impact{_WB_RIGHT}",
        "major impact",
    ),
    (
        rf"{_WB_LEFT}profound\s+sadness{_WB_RIGHT}",
        "deep sadness",
    ),
    (
        rf"{_WB_LEFT}profound\s+sense\s+of{_WB_RIGHT}",
        "deep sense of",
    ),
    (
        rf"{_WB_LEFT}profound{_WB_RIGHT}",
        "deep",
    ),
    (
        rf"{_WB_LEFT}evocative{_WB_RIGHT}",
        "vivid",
    ),
    (
        rf"{_WB_LEFT}ineffable{_WB_RIGHT}",
        "hard to describe",
    ),
    (
        rf"{_WB_LEFT}surreal\s+feeling{_WB_RIGHT}",
        "strange feeling",
    ),
    (
        rf"{_WB_LEFT}surreal{_WB_RIGHT}",
        "strange",
    ),
    (
        rf"{_WB_LEFT}ephemeral{_WB_RIGHT}",
        "short-lived",
    ),
    (
        rf"{_WB_LEFT}melancholic{_WB_RIGHT}",
        "sad",
    ),
    (
        rf"{_WB_LEFT}melancholy{_WB_RIGHT}",
        "sadness",
    ),
    (
        rf"{_WB_LEFT}monumental\s+task{_WB_RIGHT}",
        "huge task",
    ),
    (
        rf"{_WB_LEFT}monumental{_WB_RIGHT}",
        "huge",
    ),
    (
        rf"{_WB_LEFT}juxtaposition\s+of{_WB_RIGHT}",
        "contrast between",
    ),
    (
        rf"{_WB_LEFT}juxtaposition{_WB_RIGHT}",
        "contrast",
    ),
    (
        rf"{_WB_LEFT}dichotomy{_WB_RIGHT}",
        "sharp divide",
    ),
    (
        rf"{_WB_LEFT}harrowing{_WB_RIGHT}",
        "terrifying",
    ),
]


def _preserve_case(original: str, replacement: str) -> str:
    """Preserve casing of original matched text."""
    if not original or not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original.istitle():
        return replacement.capitalize()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def deflate_descriptors(text: str) -> tuple[str, list[str]]:
    """Scan and de-inflate purple prose and melodramatic descriptors.

    Code blocks and inline code fences (⟦CODE_FENCE_X⟧) are protected.

    Args:
        text: Input text.

    Returns:
        Tuple of (deflated_text, list_of_deflated_phrases).
    """
    if not text:
        return text, []

    # Protect code fences or placeholders
    code_snippets: list[str] = []

    def _save_snippet(m: re.Match[str]) -> str:
        code_snippets.append(m.group(0))
        return f"⟦SNIPPET_{len(code_snippets)-1}⟧"

    protected = re.sub(
        r"```[\s\S]*?```|`[^`\n]+`|⟦(?:CODE_FENCE|CODE_BLOCK|TABLE_BLOCK|INLINE_CODE|URL|MATH)_\d+⟧",
        _save_snippet,
        text,
    )

    deflated_phrases: list[str] = []

    for pattern, replacement in THESAURUS_DEFLATE_RULES:
        def _sub_cb(m: re.Match[str]) -> str:
            matched = m.group(0)
            deflated_phrases.append(matched)
            return _preserve_case(matched, replacement)

        protected = re.sub(pattern, _sub_cb, protected, flags=re.IGNORECASE)

    # Restore code snippets
    for idx, snippet in enumerate(code_snippets):
        protected = protected.replace(f"⟦SNIPPET_{idx}⟧", snippet)

    return protected, deflated_phrases
