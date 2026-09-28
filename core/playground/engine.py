"""
Playground AI Engine for AVA School Assistant 2.
Coordinates rubric parsing, structured criteria checklist generation, outline formulation,
section drafting grounded in source materials and rubric requirements, and iterative refinement.
"""

import json
import re
from typing import List, Dict, Any, Optional

from core.logger import get_logger
from core.playground.project_model import (
    PlaygroundProject,
    RubricCriterion,
    SourceItem,
    SectionDraft,
)
from core.playground.humanizer_bridge import PlaygroundHumanizerBridge
from core.written_solver import WrittenSolver

logger = get_logger("playground.engine")


class PlaygroundEngine:
    """Core intelligence engine for Playground document generation and review loops."""

    def __init__(self, ai_client=None, config_manager=None):
        self.ai_client = ai_client
        self.config_manager = config_manager

    @property
    def config(self):
        return self.config_manager.config if self.config_manager else None

    @property
    def active_ai_client(self):
        """Returns the most up-to-date AIClient using fresh credentials from config_manager."""
        if self.config:
            provider = getattr(self.config, "ai_provider", "gemini")
            api_key = self.config.get_api_key_for_provider(provider)
            if api_key:
                from core.ai_client import AIClient
                return AIClient(
                    provider=provider,
                    api_key=api_key,
                    model_name=getattr(self.config, "written_model_name", "gemini-3.8-flash"),
                    custom_base_url=getattr(self.config, "custom_api_base", "https://openrouter.ai/api/v1")
                )
        return self.ai_client

    @staticmethod
    def is_administrative_criterion(title: str, description: str = "") -> bool:
        """
        Determines whether a rubric criterion or guideline specifies administrative file types
        (e.g., .pdf, .docx, file upload format), submission deadlines / turn-in timing
        (e.g., due dates, turn in by Sunday 11:59 PM, late penalties), pure point counts,
        or LMS navigation boilerplate.
        """
        clean_title = title.strip()
        t = f"{title} {description}".lower()

        # 1. Pure point/score headers (e.g. "Points 5", "5 pts", "Grade: Pass/Fail", "Score: 10")
        if re.match(r"^(?:points?\s*:?\s*\d+|\d+\s*pts?|grade:?|score:?|total:?\s*\d+)$", clean_title, re.IGNORECASE):
            return True

        # 2. LMS navigation, completion notices, or preparatory reading boilerplate
        nav_patterns = [
            r"\bmust\s+be\s+completed\s+before\s+moving\s+forward\b",
            r"\bmodule\s+overview\s+(?:page)?\b",
            r"\breview\s+the\s+module\s+learning\s+outcomes\b",
            r"\bconsult\s+the\s+overview\s+page\b",
            r"\bclick\s+next\s+to\s+proceed\b",
            r"\bcomplete\s+all\s+sections\s+before\b",
        ]
        for pat in nav_patterns:
            if re.search(pat, t):
                return True

        # 3. File type / format / upload specifications
        file_type_patterns = [
            r"\bfile\s+(?:type|format|extension|name|upload|submission)\b",
            r"\b(?:upload|submission)\s+(?:format|type|file)\b",
            r"\b(?:saved?|submitted?|uploaded?)\s+as\s+(?:a\s+)?(?:\.?(?:pdf|docx?|doc|rtf|txt|pages)|word\s+(?:doc|document)|file)\b",
            r"\bformat:\s*(?:\.?(?:pdf|docx?|doc|rtf|txt)|word)\b",
            r"\b(?:\.pdf|\.docx?|\.doc|\.rtf)\b",
            r"\b(?:pdf|docx?|word\s+document)\s+(?:only|format|file|upload|submission)\b",
            r"\b(?:upload|submit)\s+(?:a\s+)?(?:pdf|docx?|doc|word\s+document)\b",
        ]
        for pat in file_type_patterns:
            if re.search(pat, t):
                return True

        # 4. When it should be turned in, due dates, deadlines, timestamps, and late policies
        turnin_patterns = [
            r"\bdue\s+(?:date|by|on|at|before|time|midnight)\b",
            r"\bturn(?:ed)?\s*in\s+(?:by|on|at|before|date|time|late|deadline|prior|on\s+time)\b",
            r"\bwhen\s+(?:to\s+turn\s+in|it\s+should\s+be\s+turned\s+in|it\s+is\s+due|to\s+submit)\b",
            r"\bsubmit(?:ted)?\s+(?:by|on|at|before|prior\s+to)\s+(?:the\s+)?(?:due|deadline|midnight|\d{1,2}[:/]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun)",
            r"\b(?:submission\s+deadline|due\s+date|turn[- ]in\s+date|submission\s+cutoff)\b",
            r"\b(?:assignment|submission|paper|project)\s+deadline\b",
            r"\bdeadline\s+for\s+(?:submission|submitting|turning\s+in|turn[- ]in)\b",
            r"\bdeadline:\s*\w+\b",
            r"\blate\s+(?:policy|penalty|submission|submissions|work|turn[- ]in|deduction)\b",
            r"\bon[- ]time\s+submission\b",
            r"\b(?:11:59\s*(?:pm|am)?|midnight\s+deadline)\b",
            r"\btimeliness\s+of\s+submission\b",
            r"\bpunctuality\s+of\s+submission\b",
        ]
        for pat in turnin_patterns:
            if re.search(pat, t):
                return True

        return False

    @staticmethod
    def _extract_json_items(text: str) -> List[Dict[str, Any]]:
        """Safely parses JSON list of items from LLM text with resilience against markdown or wrapping."""
        cleaned = text.strip()
        # Remove markdown fences
        if "```" in cleaned:
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        # Try direct parse
        try:
            val = json.loads(cleaned)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for k in ("criteria", "rubric", "items", "rubric_criteria", "requirements"):
                    if isinstance(val.get(k), list):
                        return val[k]
                return [val]
        except Exception:
            pass

        # Try regex search for outermost array [ ... ]
        match_arr = re.search(r"\[[\s\S]*\]", text)
        if match_arr:
            try:
                val = json.loads(match_arr.group(0))
                if isinstance(val, list):
                    return val
            except Exception:
                pass

        # Try regex search for outermost object { ... }
        match_obj = re.search(r"\{[\s\S]*\}", text)
        if match_obj:
            try:
                val = json.loads(match_obj.group(0))
                if isinstance(val, dict):
                    for k in ("criteria", "rubric", "items", "rubric_criteria", "requirements"):
                        if isinstance(val.get(k), list):
                            return val[k]
                    return [val]
            except Exception:
                pass

        return []

    @staticmethod
    def _clean_target_score(score_str: Optional[str]) -> Optional[str]:
        """
        Cleans and sanitizes a target score/weight string to ensure word counts
        (e.g., '50 words min', '50 words each') are NEVER placed in the points/weight field.
        Only pure points, weights, or grading status (e.g. '5 pts (Pass/Fail)', '5 pts', 'Pass/Fail') remain.
        """
        if not score_str:
            return None
        s = str(score_str).strip()
        # Pure word limit strings -> None
        if re.match(r"^~?\d+\s*words?(?:\s*(?:min|minimum|each|max|maximum|cap))?$", s, re.IGNORECASE):
            return None
        # Strip words portion from combined strings like "50 words min (Pass/Fail)" or "5 pts (50 words each)"
        cleaned = re.sub(r"~?\d+\s*words?(?:\s*(?:min|minimum|each|max|maximum|cap))?", "", s, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(\s*\)", "", cleaned).strip()
        cleaned = re.sub(r"^[\s,\-]+|[\s,\-]+$", "", cleaned).strip()
        if not cleaned:
            return None
        # If it was left as "(Pass/Fail)", unwrap outer parens
        if cleaned.startswith("(") and cleaned.endswith(")") and cleaned.count("(") == 1:
            cleaned = cleaned[1:-1].strip()
        if cleaned.lower() == "pass/fail":
            return "Pass/Fail"
        return cleaned

    def _expand_multi_item_criteria(self, criteria: List[RubricCriterion], raw_text: str) -> List[RubricCriterion]:
        """
        If an assignment prompt asks for multiple distinct items (e.g. 'three most important points',
        '3 key concepts', '4 questions', 'identify 3 factors'), but the parser returned only 1 lumped criterion
        (e.g. 'Three Key Points to Master'), automatically decompose that criterion into distinct, individual
        checklist items (e.g. 'Point 1 to Master', 'Point 2 to Master', 'Point 3 to Master').
        """
        if len(criteria) != 1:
            return criteria

        combined = f"{criteria[0].title} {criteria[0].description} {raw_text}"
        word_to_num = {
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        m = re.search(
            r"\b(?:what\s+are\s+the|identify|explain|describe|list|provide|state|name|discuss|outline)?\s*(?:the\s+)?(two|three|four|five|six|seven|eight|nine|ten|\d+)\s*(?:most\s+important\s+|key\s+|main\s+|critical\s+|distinct\s+)?(points|concepts|questions|reasons|topics|factors|elements|items|steps|examples|goals|outcomes)\b",
            combined,
            re.IGNORECASE
        )
        if not m:
            return criteria

        num_str = m.group(1).lower()
        count = word_to_num.get(num_str) or (int(num_str) if num_str.isdigit() else None)
        if not count or count < 2 or count > 15:
            return criteria

        noun_raw = m.group(2).lower()
        sing_noun = noun_raw[:-1] if noun_raw.endswith("s") else noun_raw
        if sing_noun in ("point", "concept", "element", "factor", "topic"):
            sing_noun = "Point"
        elif sing_noun == "question":
            sing_noun = "Question"
        else:
            sing_noun = sing_noun.capitalize()

        orig = criteria[0]
        orig_target = self._clean_target_score(orig.target_score)
        orig_desc = orig.description or orig.title

        expanded = []
        ordinal_words = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth"]

        base_ctx = re.sub(r"^(?:identify\s+and\s+explain\s+)?(?:the\s+)?(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s*(?:most\s+important\s+|key\s+|main\s+|critical\s+)?(?:points|concepts|questions|reasons|topics|factors)?\s*(?:you\s+hope\s+to\s+master)?\s*(?:based\s+on\s+)?", "", orig_desc, flags=re.IGNORECASE).strip()
        if base_ctx and not base_ctx.endswith("."):
            base_ctx += "."

        is_master = "master" in combined.lower()
        for idx in range(1, count + 1):
            ord_word = ordinal_words[idx - 1] if idx <= len(ordinal_words) else f"{idx}th"
            title = f"{sing_noun} {idx} to Master" if is_master else f"{sing_noun} {idx}"
            if is_master:
                desc = f"Identify and explain the {ord_word.lower()} key point you hope to master"
                if base_ctx:
                    desc += f" based on {base_ctx}"
            else:
                desc = f"Address and explain {sing_noun.lower()} #{idx}"
                if base_ctx:
                    desc += f": {base_ctx}"

            expanded.append(
                RubricCriterion(
                    title=title,
                    description=desc,
                    target_score=orig_target,
                    fulfilled=False,
                )
            )

        logger.info(f"Decomposed lumped criterion '{orig.title}' into {len(expanded)} distinct rubric criteria cards.")
        return expanded

    def _smart_fallback_parse_rubric(self, rubric_text: str) -> List[RubricCriterion]:
        """
        Intelligent offline heuristic parser that extracts substantive assignment tasks, questions,
        and grading criteria while cleanly filtering out point headers, file types, due dates,
        and LMS navigation boilerplate.
        """
        lines = [l.strip() for l in rubric_text.splitlines() if l.strip()]
        criteria = []

        # Extract global points/grade info if present (e.g. Points 5, 10 pts, Pass/Fail)
        points_val = None
        m_pts = re.search(r"\b(?:points?\s*:?\s*(\d+)|\b(\d+)\s*pts?\b)", rubric_text, re.IGNORECASE)
        if m_pts:
            pts_num = m_pts.group(1) or m_pts.group(2)
            points_val = f"{pts_num} pts"

        pass_fail = bool(re.search(r"\bpass\s*/\s*fail\b", rubric_text, re.IGNORECASE))
        if pass_fail and points_val:
            points_val = f"{points_val} (Pass/Fail)"
        elif pass_fail:
            points_val = "Pass/Fail"

        # Check for multi-item requests (e.g. "three most important points")
        word_to_num = {
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        multi_match = re.search(
            r"\b(?:what\s+are\s+the|identify|explain|describe|list|provide|state|name|discuss|outline)?\s*(?:the\s+)?(two|three|four|five|six|seven|eight|nine|ten|\d+)\s*(?:most\s+important\s+|key\s+|main\s+|critical\s+|distinct\s+)?(points|concepts|questions|reasons|topics|factors|elements|items|steps|examples|goals|outcomes)\b",
            rubric_text,
            re.IGNORECASE
        )
        if multi_match:
            cnt = word_to_num.get(multi_match.group(1).lower()) or (int(multi_match.group(1)) if multi_match.group(1).isdigit() else None)
            if cnt and 2 <= cnt <= 15:
                noun_raw = multi_match.group(2).lower()
                sing_noun = noun_raw[:-1] if noun_raw.endswith("s") else noun_raw
                if sing_noun in ("point", "concept", "element", "factor", "topic"):
                    sing_noun = "Point"
                elif sing_noun == "question":
                    sing_noun = "Question"
                else:
                    sing_noun = sing_noun.capitalize()

                is_master = "master" in rubric_text.lower()
                ordinal_words = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]
                for i in range(1, cnt + 1):
                    ord_word = ordinal_words[i - 1] if i <= len(ordinal_words) else f"{i}th"
                    t = f"{sing_noun} {i} to Master" if is_master else f"{sing_noun} {i}"
                    d = f"Identify and explain the {ord_word.lower()} key point you hope to master." if is_master else f"Address and explain {sing_noun.lower()} #{i}."
                    criteria.append(
                        RubricCriterion(
                            title=t,
                            description=d,
                            target_score=points_val,
                            fulfilled=False,
                        )
                    )
                return criteria

        for line in lines:
            clean = re.sub(r"^[-*•\d\.\)\s]+", "", line).strip()
            if len(clean) < 4:
                continue

            # Skip administrative items (file types, turn-in dates, points headers, navigation)
            if self.is_administrative_criterion(clean, clean):
                continue

            t_low = clean.lower()
            # Ignore standalone word count/grading lines from becoming their own criterion card
            if re.search(r"\b(?:at\s+least\s+\d+\s*words?|\d+\s*words?\s*(?:each|min|minimum)?|graded\s+as)\b", t_low):
                continue

            if "?" in clean:
                q_part = clean.split("?")[0].strip()
                clean_q = re.sub(r"^(?:based\s+on\s+this\s+(?:material|reading|chapter|module|article),\s*)", "", q_part, flags=re.IGNORECASE)
                words = clean_q.split()
                if len(words) > 8:
                    title = " ".join(words[:8]) + "..."
                else:
                    title = clean_q
                if not title.endswith("?"):
                    title += "?"
                criteria.append(
                    RubricCriterion(
                        title=title[:60].strip().capitalize(),
                        description=clean,
                        target_score=points_val,
                        fulfilled=False,
                    )
                )
            else:
                words = clean.split()
                if len(words) > 6:
                    title = " ".join(words[:6]) + "..."
                else:
                    title = clean
                criteria.append(
                    RubricCriterion(
                        title=title[:60].strip(),
                        description=clean,
                        target_score=points_val if len(criteria) == 0 else None,
                        fulfilled=False,
                    )
                )

        return criteria

    def parse_rubric(self, rubric_text: str) -> List[RubricCriterion]:
        """
        Parses raw text or OCR output of a rubric into structured RubricCriterion objects.
        Explicitly uses Gemini 3.1 Flash-Lite (gemini-3.1-flash-lite) for high accuracy rubric analysis.
        Filters out administrative requirements (file types, turn-in dates) and ensures
        per-point word constraints (e.g. '50 words EACH') are explicitly specified.
        """
        if not rubric_text or not rubric_text.strip():
            return []

        system_prompt = (
            "You are an expert academic evaluator and assignment analyst. "
            "Analyze the provided assignment rubric, prompt, or question guidelines "
            "and extract each distinct grading criterion or required task into a structured JSON list.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. EXCLUDE ADMINISTRATIVE & SUBMISSION DETAILS:\n"
            "- Ignore file types or formats (e.g. '.pdf', '.docx', '.doc', 'Word document', file upload format).\n"
            "- Ignore when to turn it in, deadlines, timestamps, or late submission policies (e.g. 'due Sunday', 'due by 11:59 PM').\n"
            "- Ignore LMS navigation or completion boilerplate (e.g. 'Points: 5', 'Must be completed before moving forward', 'Module Overview page').\n\n"
            "2. BREAK DOWN MULTI-ITEM PROMPTS & QUESTIONS INTO INDIVIDUAL CRITERIA:\n"
            "- If an assignment prompt asks for multiple points, concepts, questions, reasons, or steps (for example: 'what are the three most important points you hope to master?', 'identify 3 key factors', 'answer questions 1 through 4'):\n"
            "  YOU MUST CREATE A SEPARATE CRITERION FOR EACH INDIVIDUAL ITEM (e.g., 'Point 1 to Master', 'Point 2 to Master', 'Point 3 to Master').\n"
            "  NEVER lump them into a single criterion! The student needs a distinct checklist card for each required point to verify as they write.\n\n"
            "3. POINTS & WEIGHT (target_score):\n"
            "- 'target_score' represents the GRADE POINTS or WEIGHT ONLY (e.g. '5 pts (Pass/Fail)', '5 pts', '10 pts', '15%', 'Pass/Fail').\n"
            "- NEVER put word limits, word counts, or length rules (e.g. '50 words', '50 words min', '50 words each') into 'target_score'! The word limit is a length constraint, NOT a grade point weight.\n"
            "- If points are specified globally (e.g. 'Points 5' or '5 points (Pass/Fail)'), you may assign the total or split points across criteria (e.g. 'Pass/Fail' or '5 pts total' or individual points).\n\n"
            "4. WORD REQUIREMENTS:\n"
            "- If the prompt specifies word count rules (e.g. 'at least 50 words', '50 words each'), include that requirement inside the 'description' field only (e.g. 'Explain the first concept you hope to master (at least 50 words required)'). NEVER put it in 'target_score'.\n\n"
            "Respond ONLY with a JSON array where each item has:\n"
            "- 'title': Concise, human-readable name of the requirement (e.g. 'Point 1 to Master', 'Point 2 to Master', 'Point 3 to Master', 'Thesis Statement')\n"
            "- 'description': What the student must write or demonstrate to fulfill this requirement\n"
            "- 'target_score': Grade points or weight only (e.g. '5 pts (Pass/Fail)' or 'Pass/Fail') or null. DO NOT put word counts here.\n"
            "Do NOT include any markdown code blocks or text outside the JSON array."
        )

        user_prompt = f"Rubric / assignment content to analyze:\n\n{rubric_text[:6000]}"

        ai = self.active_ai_client
        api_key = getattr(ai, "api_key", "")
        if not api_key and self.config:
            api_key = self.config.get_api_key_for_provider(getattr(self.config, "ai_provider", "gemini"))
            if api_key:
                from core.ai_client import AIClient
                ai = AIClient(
                    provider=getattr(self.config, "ai_provider", "gemini"),
                    api_key=api_key,
                    model_name="gemini-3.1-flash-lite",
                )

        parsed_criteria: List[RubricCriterion] = []
        if ai and getattr(ai, "api_key", "").strip():
            try:
                # Ensure rubric parsing specifically targets Gemini 3.1 Flash-Lite
                rubric_model = "gemini-3.1-flash-lite" if getattr(ai, "provider", "gemini") == "gemini" else None
                resp = ai.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                    model_override=rubric_model,
                    temperature=0.2,
                )
                items = self._extract_json_items(resp)
                for itm in items:
                    if isinstance(itm, dict):
                        title = str(itm.get("title", "Requirement")).strip()
                        desc = str(itm.get("description", "")).strip()
                        if self.is_administrative_criterion(title, desc):
                            continue
                        parsed_criteria.append(
                            RubricCriterion(
                                title=title,
                                description=desc,
                                target_score=self._clean_target_score(itm.get("target_score")),
                                fulfilled=False,
                            )
                        )
            except Exception as e:
                logger.warning(f"AI rubric parsing encountered error: {e}. Falling back to rule-based lines.")

        if not parsed_criteria:
            parsed_criteria = self._smart_fallback_parse_rubric(rubric_text)

        # 1. Strictly ignore and exclude rubric points with file types and when it should be turned in
        criteria = [
            c for c in parsed_criteria
            if not self.is_administrative_criterion(c.title, c.description)
        ]

        # 2. Decompose lumped multi-item criteria if model or fallback grouped them into 1
        criteria = self._expand_multi_item_criteria(criteria, rubric_text)

        # 3. Clean and sanitize all target_score fields to guarantee word limits are never in weight
        for c in criteria:
            c.target_score = self._clean_target_score(c.target_score)

        # 4. Check if the rubric states "50 words EACH" (or per question/point/bullet)
        constraints = WrittenSolver.extract_detailed_word_constraints(rubric_text)
        per_item_w = constraints.get("per_item_words")
        if not per_item_w:
            m_each = re.search(
                r"(?:at\s+least|minimum\s+of|minimum|min|around|approx(?:imately)?|roughly|~)?\s*(\d+)\s*words?\s*(?:each|per\s+(?:question|point|bullet|item|part|prompt)|for\s+each\s+(?:question|point|bullet|item|part|one)|each\s+(?:question|point|bullet|item|part))",
                rubric_text,
                re.IGNORECASE
            )
            if m_each:
                per_item_w = int(m_each.group(1))

        # Explicitly specify word requirement in each criterion's DESCRIPTION (never in target_score/weight)
        if per_item_w and criteria:
            for c in criteria:
                c_full = f"{c.title} {c.description}".lower()
                if not re.search(rf"\b{per_item_w}\s*words?\b", c_full):
                    if c.description:
                        c.description = f"{c.description.rstrip()} (Word requirement: {per_item_w} words each)"
                    else:
                        c.description = f"Word requirement: {per_item_w} words each"

        return criteria

    def generate_outline(
        self,
        project: PlaygroundProject,
        customization: Optional[Dict[str, Any]] = None,
    ) -> List[SectionDraft]:
        """
        Creates an ordered sequence of section drafts mapped to the project's rubric criteria,
        sources, and target word count. Strictly enforces rubric word counts and normalizes
        section goals to prevent AI over-estimation.
        """
        # Filter out any administrative criteria (file types, turn-in dates)
        project.rubric_criteria = [
            c for c in project.rubric_criteria
            if not self.is_administrative_criterion(c.title, c.description)
        ]

        # Deeply inspect rubric criteria and raw text for overall & per-section word limits
        rubric_text_full = "\n".join([f"{c.title}: {c.description}" for c in project.rubric_criteria])
        if getattr(project, "rubric_raw_text", ""):
            rubric_text_full += "\n" + project.rubric_raw_text

        combined_text = f"{project.title}\n{project.topic_description}\n{rubric_text_full}".strip()
        criteria_count = len(project.rubric_criteria) if project.rubric_criteria else None
        constraints = WrittenSolver.extract_detailed_word_constraints(combined_text, item_count=criteria_count)

        # Map individual criteria with specific word constraints
        criteria_word_counts = {}
        for c in project.rubric_criteria:
            c_constraint = WrittenSolver.extract_detailed_word_constraints(f"{c.title}\n{c.description}")
            if c_constraint.get("per_item_words"):
                criteria_word_counts[c.id] = c_constraint["per_item_words"]
            elif c_constraint.get("min_words"):
                criteria_word_counts[c.id] = c_constraint["min_words"]

        multi_part_note = ""
        if constraints.get("is_multi_part") and constraints.get("per_item_words"):
            per_q = constraints["per_item_words"]
            num_q = criteria_count or constraints.get("num_items") or 1
            calculated_total = per_q * num_q
            project.target_total_words = calculated_total
            multi_part_note = (
                f"\nCRITICAL 'WORDS PER POINT' / MULTI-ITEM REQUIREMENT:\n"
                f"- The rubric/prompt explicitly specifies approximately {per_q} words PER POINT/CRITERION.\n"
                f"- IMPORTANT: This means {per_q} words PER POINT, NOT {per_q} words for the total document!\n"
                f"- With {num_q} points/criteria, the total document target is {calculated_total} words ({num_q} points × {per_q} words each).\n"
                f"- You MUST create sections corresponding to these points, with each section having target_word_count of approximately {per_q} words.\n"
                f"- Total document word count target is EXACTLY {calculated_total} words.\n"
            )
        elif criteria_word_counts and len(criteria_word_counts) == len(project.rubric_criteria) and len(project.rubric_criteria) > 0:
            calculated_total = sum(criteria_word_counts.values())
            project.target_total_words = calculated_total
        elif constraints.get("total_min_words"):
            project.target_total_words = constraints["total_min_words"]
        elif constraints.get("min_words") and not constraints.get("per_item_words") and project.target_total_words in (1000, 500, 0):
            project.target_total_words = constraints["min_words"]

        # Build custom formatting and personalization guidelines if provided
        custom_notes = ""
        if customization:
            c_parts = []
            if customization.get("structure_preset") and "Auto" not in customization["structure_preset"]:
                c_parts.append(f"- Structure Preset: {customization['structure_preset']}")
            if customization.get("section_count") and "Auto" not in str(customization["section_count"]):
                c_parts.append(f"- Desired Section Count: Exactly {customization['section_count']} sections")
            if customization.get("heading_style"):
                c_parts.append(f"- Heading Style: {customization['heading_style']}")
            if customization.get("user_notes"):
                c_parts.append(f"- Student Personalization Notes: {customization['user_notes'].strip()}")
            if c_parts:
                custom_notes = "\nSTUDENT PERSONALIZATION & FORMATTING GUIDELINES:\n" + "\n".join(c_parts) + "\n"

        system_prompt = (
            "You are an academic project architect. Given the document title, topic, target word count, "
            "and rubric criteria, create a coherent, comprehensive outline.\n"
            f"{multi_part_note}\n"
            f"{custom_notes}\n"
            "STRICT WORD COUNT RULES:\n"
            f"- The project target word count is EXACTLY {project.target_total_words} words.\n"
            "- The sum of 'target_word_count' across all sections MUST NOT exceed this target.\n"
            "- 'WORDS PER POINT' RULE: When rubrics or instructions say '__ words per point', '__ words per bullet', '__ words per criterion', or '__ words each', that target applies to EACH section/point individually, NOT the entire paper. The total assignment length is (words per point) × (number of points).\n"
            "- Never make the entire paper only as long as a single point (e.g., if it says 50 words per point for 4 points, total is 200 words, NOT 50 words).\n"
            "- Do NOT inflate or overestimate word counts beyond the student's prompt and rubric!\n\n"
            "Respond ONLY with a JSON array where each object has:\n"
            "- 'title': Section heading (e.g. 'Question 1', 'Introduction & Thesis', 'Historical Context')\n"
            "- 'goal_summary': Detailed description of what arguments, evidence, and points this section must contain\n"
            "- 'target_word_count': Integer target word count for this specific section (must sum to the total target)\n"
            "- 'criteria_indices': List of 0-based integer indices of the rubric criteria this section addresses\n"
            "Do NOT include markdown formatting or commentary outside the JSON array."
        )

        rubric_summary = "\n".join(
            [f"[{i}] {c.title}: {c.description}" for i, c in enumerate(project.rubric_criteria)]
        )
        sources_summary = "\n".join(
            [f"Source: {s.name} ({s.source_type}) - {s.content[:200]}..." for s in project.sources]
        )

        user_prompt = (
            f"Project Title: {project.title}\n"
            f"Topic/Prompt: {project.topic_description}\n"
            f"Target Total Word Count: {project.target_total_words}\n"
            f"Formatting Style: {project.formatting_preset}\n\n"
            f"Rubric Criteria:\n{rubric_summary if rubric_summary else 'General high-quality academic standards.'}\n\n"
            f"Sources Summary:\n{sources_summary if sources_summary else 'Standard academic domain knowledge.'}"
        )

        try:
            if self.ai_client:
                resp = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
                data = self._extract_json_items(resp)
                sections = []
                for item in data:
                    if isinstance(item, dict):
                        # Map indices to criterion IDs
                        c_indices = item.get("criteria_indices", [])
                        c_ids = []
                        for idx in c_indices:
                            if isinstance(idx, int) and 0 <= idx < len(project.rubric_criteria):
                                c_ids.append(project.rubric_criteria[idx].id)

                        sections.append(
                            SectionDraft(
                                title=item.get("title", "Section"),
                                goal_summary=item.get("goal_summary", ""),
                                target_word_count=int(item.get("target_word_count", 250)),
                                criteria_ids=c_ids,
                            )
                        )
                if sections:
                    # Enforce rubric-aware goal counters and normalize any AI over-estimation
                    target_total = project.target_total_words

                    # 1. Check if individual sections map to criteria with specific word constraints
                    for sec in sections:
                        for cid in sec.criteria_ids:
                            if cid in criteria_word_counts:
                                sec.target_word_count = criteria_word_counts[cid]
                                break

                    # 2. Multi-part / per-item enforcement (e.g. 5 questions at 50w each)
                    if constraints.get("is_multi_part") and constraints.get("per_item_words"):
                        for sec in sections:
                            sec.target_word_count = constraints["per_item_words"]

                    # 3. Proportional normalization if sum exceeds rubric target
                    sum_words = sum(s.target_word_count for s in sections)
                    if target_total and sum_words > int(target_total * 1.15):
                        logger.info(
                            f"AI outline estimated {sum_words} words, greatly exceeding rubric target {target_total}. Normalizing section goals."
                        )
                        allocated = 0
                        for i, sec in enumerate(sections):
                            if i == len(sections) - 1:
                                sec.target_word_count = max(15, target_total - allocated)
                            else:
                                scaled = max(15, int((sec.target_word_count / sum_words) * target_total))
                                sec.target_word_count = scaled
                                allocated += scaled

                    return sections
        except Exception as e:
            logger.warning(f"AI outline formulation failed: {e}. Generating default academic outline.")

        # Fallback outline
        if constraints.get("is_multi_part") and constraints.get("num_items") and constraints.get("per_item_words"):
            num_q = constraints["num_items"]
            per_q = constraints["per_item_words"]
            fallback_sections = []
            for i in range(1, num_q + 1):
                c_ids = [project.rubric_criteria[i - 1].id] if i <= len(project.rubric_criteria) else []
                fallback_sections.append(
                    SectionDraft(
                        title=f"Question {i}",
                        goal_summary=f"Answer Question {i} concisely and completely within approximately {per_q} words.",
                        target_word_count=per_q,
                        criteria_ids=c_ids,
                    )
                )
            return fallback_sections

        # Default academic fallback outline
        total = project.target_total_words or 500
        if total <= 300:
            intro_words = int(total * 0.45)
            concl_words = total - intro_words
            return [
                SectionDraft(
                    title="Part 1: Analysis & Response",
                    goal_summary=f"Directly answer the prompt requirements regarding {project.title}.",
                    target_word_count=intro_words,
                    criteria_ids=[c.id for c in project.rubric_criteria[:2]],
                ),
                SectionDraft(
                    title="Part 2: Evidence & Synthesis",
                    goal_summary="Provide supporting evidence and summarize key takeaways.",
                    target_word_count=concl_words,
                    criteria_ids=[c.id for c in project.rubric_criteria[2:]],
                ),
            ]

        intro_words = int(total * 0.15)
        body1_words = int(total * 0.35)
        body2_words = int(total * 0.35)
        concl_words = total - (intro_words + body1_words + body2_words)

        all_crit_ids = [c.id for c in project.rubric_criteria]
        return [
            SectionDraft(
                title="Introduction & Thesis",
                goal_summary=f"Introduce {project.title}, provide background context, and state a clear central thesis.",
                target_word_count=intro_words,
                criteria_ids=all_crit_ids[:2] if all_crit_ids else [],
            ),
            SectionDraft(
                title="Analysis & Core Evidence",
                goal_summary="Examine primary evidence, analyze key components, and synthesize findings.",
                target_word_count=body1_words,
                criteria_ids=all_crit_ids[2:4] if len(all_crit_ids) > 2 else all_crit_ids,
            ),
            SectionDraft(
                title="Implications & Discussion",
                goal_summary="Discuss deeper significance, address nuances or counterarguments, and evaluate impact.",
                target_word_count=body2_words,
                criteria_ids=all_crit_ids[4:] if len(all_crit_ids) > 4 else all_crit_ids,
            ),
            SectionDraft(
                title="Conclusion",
                goal_summary="Synthesize the primary arguments, reaffirm the thesis in a new light, and offer closing perspective.",
                target_word_count=concl_words,
                criteria_ids=all_crit_ids[-1:] if all_crit_ids else [],
            ),
        ]

    def draft_section(
        self,
        project: PlaygroundProject,
        section: SectionDraft,
        humanizer_bridge: PlaygroundHumanizerBridge,
        auto_humanize: bool = True,
    ) -> SectionDraft:
        """
        Drafts a full section tailored to rubric requirements and source materials.
        Strictly enforces believable student length (+10% to 20% margin over minimum)
        and automatically passes through Jade's AI Humanizer.
        """
        # Collect criteria details for this section
        mapped_criteria = [
            c for c in project.rubric_criteria if c.id in section.criteria_ids
        ]
        crit_text = "\n".join([f"- {c.title}: {c.description}" for c in mapped_criteria])
        if not crit_text:
            crit_text = "Adhere to rigorous academic rigor, clarity, and logical organization."

        # Prior sections summary for context continuity
        prior_context = []
        for prev in project.sections:
            if prev.id == section.id:
                break
            prev_txt = prev.get_active_text().strip()
            if prev_txt:
                prior_context.append(f"Previous Section '{prev.title}': {prev_txt[:300]}...")

        # Sources context
        sources_text = "\n\n".join(
            [f"--- Source: {s.name} ---\n{s.content[:1500]}" for s in project.sources]
        )

        min_words = section.target_word_count
        target_words = int(min_words * 1.10)
        max_allowed = int(min_words * 1.20)

        system_prompt = (
            "You are an expert student academic writer drafting a section of a school assignment.\n"
            "RULES:\n"
            f"1. Target Length: Approximately {target_words} words.\n"
            f"2. Strict Acceptable Range: {min_words} to {max_allowed} words (10% to 20% over minimum error margin).\n"
            f"3. ABSOLUTE LIMIT: Do NOT exceed {max_allowed} words under any circumstances! A believable student response is focused and concise. Writing hundreds of words when {section.target_word_count} words are requested is an instant failure.\n"
            "4. Tone: Academic, rigorous, insightful, and natural. Avoid formulaic AI clichés.\n"
            "5. Ground your analysis thoroughly in the provided sources and address the specified rubric criteria.\n"
            "6. Return ONLY the drafted paragraphs. Do NOT include section title headers, meta-commentary, or notes."
        )

        user_prompt = (
            f"Paper Title: {project.title}\n"
            f"Overall Topic: {project.topic_description}\n"
            f"Current Section to Write: {section.title}\n"
            f"Section Objective: {section.goal_summary}\n\n"
            f"Rubric Criteria for this section:\n{crit_text}\n\n"
        )
        if prior_context:
            user_prompt += f"Preceding Sections Context:\n" + "\n".join(prior_context) + "\n\n"
        if sources_text:
            user_prompt += f"Source Materials:\n{sources_text[:4000]}\n\n"

        user_prompt += "Write the complete draft for this section now."

        raw_text = ""
        if self.ai_client:
            try:
                raw_text = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
            except Exception as e:
                logger.error(f"Failed to generate section draft: {e}")
                raw_text = (
                    f"In analyzing {section.title.lower()}, evidence demonstrates significant "
                    f"interdependence among core variables. Further examination reveals essential insights."
                )
        else:
            raw_text = f"Draft for {section.title} regarding {project.topic_description}."

        # Enforce believable word limit (+10% to 20% buffer) on raw draft
        solver = WrittenSolver()
        raw_text = solver.apply_word_limits(
            raw_text,
            min_words=min_words,
            max_words=max_allowed,
            buffer_pct=0.15,
        )
        section.raw_ai_text = raw_text.strip()

        # Humanize if requested
        if auto_humanize and humanizer_bridge:
            h_res = humanizer_bridge.humanize_text(
                text=section.raw_ai_text,
                tone=self.config.humanizer_tone if self.config else "academic",
                level=self.config.humanizer_reading_level if self.config else "college",
                mode=self.config.humanizer_mode if self.config else "budget",
            )
            h_text = h_res.get("humanized_text", section.raw_ai_text).strip()
            # Re-enforce believable word limit on humanized text
            section.humanized_text = solver.apply_word_limits(
                h_text,
                min_words=min_words,
                max_words=max_allowed,
                buffer_pct=0.15,
            ).strip()
            section.final_text = section.humanized_text
        else:
            section.humanized_text = ""
            section.final_text = section.raw_ai_text

        return section

    def refine_section(
        self,
        project: PlaygroundProject,
        section: SectionDraft,
        user_instructions: str,
        humanizer_bridge: PlaygroundHumanizerBridge,
        auto_humanize: bool = True,
    ) -> SectionDraft:
        """
        Revises the active draft of a section based on specific user feedback and prompts,
        strictly keeping within believable word constraints (+10% to 20% margin).
        """
        current_text = section.get_active_text()
        min_words = section.target_word_count
        target_words = int(min_words * 1.10)
        max_allowed = int(min_words * 1.20)

        system_prompt = (
            "You are an academic editor refining a draft section according to the author's instructions.\n"
            "RULES:\n"
            "1. Revise the provided text faithfully applying the user's specific feedback.\n"
            f"2. Strict Word Limit: Target {target_words} words (acceptable range: {min_words} to {max_allowed} words). Do NOT exceed {max_allowed} words.\n"
            "3. Preserve factual accuracy and academic substance while enhancing style and structure.\n"
            "4. Return ONLY the revised draft text without conversational intros or quotes."
        )

        user_prompt = (
            f"Paper Title: {project.title}\n"
            f"Section: {section.title}\n"
            f"Target Word Count: ~{section.target_word_count} words (Limit: {min_words} to {max_allowed} words)\n\n"
            f"Current Text:\n{current_text}\n\n"
            f"Author Refinement Instructions:\n{user_instructions}\n\n"
            "Provide the revised section text:"
        )

        revised_raw = ""
        if self.ai_client:
            try:
                revised_raw = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
            except Exception as e:
                logger.error(f"Refinement generation failed: {e}")
                revised_raw = current_text
        else:
            revised_raw = current_text

        solver = WrittenSolver()
        revised_raw = solver.apply_word_limits(
            revised_raw,
            min_words=min_words,
            max_words=max_allowed,
            buffer_pct=0.15,
        )
        section.refinement_history.append(user_instructions)
        section.raw_ai_text = revised_raw.strip()

        if auto_humanize and humanizer_bridge:
            h_res = humanizer_bridge.humanize_text(
                text=section.raw_ai_text,
                tone=self.config.humanizer_tone if self.config else "academic",
                level=self.config.humanizer_reading_level if self.config else "college",
                mode=self.config.humanizer_mode if self.config else "budget",
            )
            h_text = h_res.get("humanized_text", section.raw_ai_text).strip()
            section.humanized_text = solver.apply_word_limits(
                h_text,
                min_words=min_words,
                max_words=max_allowed,
                buffer_pct=0.15,
            ).strip()
            section.final_text = section.humanized_text
        else:
            section.humanized_text = ""
            section.final_text = section.raw_ai_text

        return section
