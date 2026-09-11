"""
High-Speed Local Offline Spellchecker and Typo Corrector for AVA 2.0.
Operates completely offline with zero extra API latency.
Validates spelling, fixes common student typos, repairs broken contractions,
and cleans up accidental repeated tokens or punctuation anomalies.
"""

import re
from typing import List, Tuple, Dict, Set, Optional
from core.logger import get_logger

logger = get_logger("spellcheck")

# Common student typos & corrections mapping for O(1) instant resolution
COMMON_TYPOS: Dict[str, str] = {
    "teh": "the",
    "taht": "that",
    "thier": "their",
    "studnet": "student",
    "recieve": "receive",
    "recieved": "received",
    "seperate": "separate",
    "seperated": "separated",
    "untill": "until",
    "definately": "definitely",
    "occured": "occurred",
    "occuring": "occurring",
    "goverment": "government",
    "enviroment": "environment",
    "accommodate": "accommodate",
    "accomodate": "accommodate",
    "reccomend": "recommend",
    "neccessary": "necessary",
    "tommorrow": "tomorrow",
    "wich": "which",
    "becuase": "because",
    "beacuse": "because",
    "alot": "a lot",
    "alright": "all right",
    "beleive": "believe",
    "beleived": "believed",
    "freind": "friend",
    "freinds": "friends",
    "peice": "piece",
    "peices": "pieces",
    "wierd": "weird",
    "truely": "truly",
    "writting": "writing",
    "grammer": "grammar",
    "succesful": "successful",
    "arguement": "argument",
    "persue": "pursue",
    "intresting": "interesting",
    "experiance": "experience",
    "existance": "existence",
    "maintainance": "maintenance",
    "privilege": "privilege",
    "privelege": "privilege",
    "embarass": "embarrass",
    "noticable": "noticeable",
    "judgement": "judgment",
    "consistancy": "consistency",
    "refering": "referring",
    "transfered": "transferred",
    "dissapear": "disappear",
    "disapear": "disappear",
    "disapoint": "disappoint",
    "independant": "independent",
    "occurrance": "occurrence",
    "tendancy": "tendency",
    "persistant": "persistent",
    "comittee": "committee",
    "fourty": "forty",
    "nineth": "ninth",
    "relavent": "relevant",
    "heighth": "height",
    "athiest": "atheist",
    "guarentee": "guarantee",
    "hypocrasy": "hypocrisy",
    "questionaire": "questionnaire",
}

# Missing apostrophes in common contractions
COMMON_CONTRACTIONS: Dict[str, str] = {
    "dont": "don't",
    "doesnt": "doesn't",
    "didnt": "didn't",
    "cant": "can't",
    "wont": "won't",
    "wouldnt": "wouldn't",
    "shouldnt": "shouldn't",
    "couldnt": "couldn't",
    "isnt": "isn't",
    "arent": "aren't",
    "wasnt": "wasn't",
    "werent": "weren't",
    "hasnt": "hasn't",
    "havent": "haven't",
    "hadnt": "hadn't",
    "thats": "that's",
    "whats": "what's",
    "wheres": "where's",
    "hows": "how's",
    "theres": "there's",
    "theyre": "they're",
    "youre": "you're",
    "weve": "we've",
    "theyve": "they've",
    "youve": "you've",
    "ive": "I've",
    "im": "I'm",
    "ill": "I'll",
    "youll": "you'll",
    "theyll": "they'll",
    "itll": "it'll",
}

# Common academic lexicon words to ensure no false positives on curriculum terminology
ACADEMIC_LEXICON: Set[str] = {
    "photosynthesis", "mitochondria", "hypothesis", "variable", "independent",
    "dependent", "constant", "ecosystem", "biodiversity", "cellular", "respiration",
    "chromosome", "genetics", "phenotype", "genotype", "acceleration", "velocity",
    "momentum", "kinetic", "potential", "friction", "gravitational", "electromagnetic",
    "thermodynamics", "endothermic", "exothermic", "stoichiometry", "equilibrium",
    "derivative", "integral", "polynomial", "quadratic", "asymptote", "logarithm",
    "exponential", "coefficient", "numerator", "denominator", "pythagorean",
    "constitution", "amendment", "democracy", "republic", "authoritarian", "monarchy",
    "sovereignty", "jurisdiction", "ratification", "renaissance", "reformation",
    "industrialization", "imperialism", "nationalism", "metaphor", "simile",
    "personification", "alliteration", "hyperbole", "onomatopoeia", "allegory",
    "protagonist", "antagonist", "dramatis", "foreshadowing", "soliloquy",
    "juxtaposition", "oxymoron", "allusion", "symbolism", "theme", "tone",
    "mood", "syntax", "diction", "connotation", "denotation", "rhetoric", "ethos",
    "pathos", "logos", "satire", "irony", "perspective", "inference", "correlation",
    "causation", "qualitative", "quantitative", "methodology", "empirical",
    "synthesize", "differentiate", "evaluate", "illustrate", "demonstrate",
}


class Spellchecker:
    """Offline spellchecker and text sanitization utility."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._typo_lookup = {k.lower(): v for k, v in COMMON_TYPOS.items()}
        self._contraction_lookup = {k.lower(): v for k, v in COMMON_CONTRACTIONS.items()}

    def check_and_correct(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Scans text, corrects typos and missing apostrophes, removes repeated words,
        and fixes spacing around punctuation.
        Returns:
            (corrected_text, list_of_corrections)
        """
        if not self.enabled or not text:
            return text, []

        corrections: List[Dict[str, str]] = []
        result = text

        # 1. Deduplicate accidental double words (e.g. "the the" -> "the")
        def dedupe_match(m):
            w1 = m.group(1)
            corrections.append({"original": f"{w1} {w1}", "corrected": w1, "type": "duplicate_word"})
            return w1

        result = re.sub(r"\b([A-Za-z]+)\s+\1\b", dedupe_match, result, flags=re.IGNORECASE)

        # 2. Token-by-token typo & contraction resolution
        def replace_word(m):
            raw_word = m.group(0)
            low_word = raw_word.lower()

            # Check direct typo table
            if low_word in self._typo_lookup:
                target = self._typo_lookup[low_word]
                # Match title case or lowercase
                if raw_word.istitle():
                    target = target.title()
                elif raw_word.isupper():
                    target = target.upper()
                corrections.append({"original": raw_word, "corrected": target, "type": "typo"})
                return target

            # Check contraction table
            if low_word in self._contraction_lookup:
                target = self._contraction_lookup[low_word]
                if raw_word.istitle():
                    target = target.capitalize()
                elif raw_word.isupper():
                    target = target.upper()
                corrections.append({"original": raw_word, "corrected": target, "type": "contraction"})
                return target

            return raw_word

        # Replace words while preserving punctuation
        result = re.sub(r"\b[A-Za-z']+\b", replace_word, result)

        # 3. Fix punctuation spacing (e.g., "word , another" -> "word, another")
        result = re.sub(r"\s+([,.:;!?])", r"\1", result)
        # Fix missing space after punctuation if followed immediately by a letter
        result = re.sub(r"([,;:!?])([A-Za-z])", r"\1 \2", result)
        # Fix periods followed by letters (e.g. "end.Next" -> "end. Next", avoid decimals like 3.14)
        result = re.sub(r"([a-z])\.([A-Z])", r"\1. \2", result)

        # 4. Collapse multiple consecutive spaces
        result = re.sub(r"[ \t]{2,}", " ", result)

        if corrections:
            logger.info(f"Spellcheck performed {len(corrections)} correction(s): {corrections}")

        return result, corrections


SpellChecker = Spellchecker

