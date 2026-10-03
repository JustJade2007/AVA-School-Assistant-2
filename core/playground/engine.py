"""
Playground AI Engine for AVA School Assistant 2.
Coordinates rubric parsing, structured criteria checklist generation, outline formulation,
section drafting grounded in source materials and rubric requirements, and iterative refinement.
"""

import json
import re
import time
from typing import List, Dict, Any, Optional, Callable

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
        """Returns the current AI client, or dynamically instantiates one from config if needed."""
        if self.ai_client and getattr(self.ai_client, "api_key", "").strip():
            return self.ai_client

        if self.config:
            provider = getattr(self.config, "ai_provider", "gemini")
            api_key = self.config.get_api_key_for_provider(provider) if hasattr(self.config, "get_api_key_for_provider") else (getattr(self.config, "gemini_api_key", "") or getattr(self.config, "api_key", ""))
            if api_key:
                from core.ai_client import AIClient
                ai = AIClient(
                    provider=provider,
                    api_key=api_key,
                )
                self.ai_client = ai
                return ai
        return self.ai_client

    @staticmethod
    def is_administrative_criterion(title: str, description: str = "") -> bool:
        """
        Determines whether a rubric criterion specifies administrative file types
        (e.g., .docx, .pdf, Word document, file format requirements) or when the
        assignment is supposed to be turned in by (e.g., due dates, deadlines,
        turn-in times, late policies).
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

        # 3. File type / format the assignment is required to be written in or submitted as
        file_type_patterns = [
            r"\bfile\s+(?:type|format|extension|name|upload|submission|requirement)s?\b",
            r"\b(?:upload|submission)\s+(?:format|type|file)\b",
            r"\b(?:written|typed|saved?|submitted?|uploaded?)\s+(?:in|as)\s+(?:a\s+)?(?:\.?(?:pdf|docx?|doc|rtf|txt|pages)|word(?:\s+(?:doc|document))?|google\s+docs?|file)\b",
            r"\bformat:\s*(?:\.?(?:pdf|docx?|doc|rtf|txt)|word|google\s+docs?)\b",
            r"\b(?:\.pdf|\.docx?|\.doc|\.rtf|\.pages|\.txt)\b",
            r"\b(?:pdf|docx?|word\s+document|google\s+docs?)\s+(?:only|format|file|upload|submission|type)\b",
            r"\b(?:upload|submit)\s+(?:a\s+)?(?:pdf|docx?|doc|word\s+document)\b",
            r"\b(?:accepted|required)\s+file\s+(?:types?|formats?)\b",
        ]
        for pat in file_type_patterns:
            if re.search(pat, t):
                return True

        # 4. Date the assignment is supposed to be turned in by, due dates, deadlines, late policies
        turnin_patterns = [
            r"\bdue\s+(?:date|by|on|at|before|time|midnight)\b",
            r"\bturn(?:ed)?\s*[- ]?in\s+(?:by|on|at|before|date|time|late|deadline|prior|on\s+time)\b",
            r"\bwhen\s+(?:to\s+turn\s+in|it\s+should\s+be\s+turned\s+in|it\s+is\s+due|to\s+submit)\b",
            r"\b(?:to|supposed\s+to)\s+be\s+turned\s+in\s+by\b",
            r"\bsubmit(?:ted)?\s+(?:by|on|at|before|prior\s+to)\s+(?:the\s+)?(?:due|deadline|midnight|\d{1,2}[:/]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun|\b\w+\b)",
            r"\b(?:submission\s+deadline|due\s+date|turn[- ]in\s+date|submission\s+cutoff|submission\s+time)\b",
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

        # Check titles specifically for due date or file format keywords
        title_lower = clean_title.lower()
        if re.search(r"^(?:due\s+date|submission\s+date|turn[- ]in\s+date|deadline|late\s+policy|file\s+format|file\s+type)$", title_lower):
            return True

        return False

    def parse_rubric(self, rubric_text: str) -> List[RubricCriterion]:
        """
        Parses raw text or OCR output of a rubric into structured RubricCriterion objects.
        Strictly excludes administrative criteria including file types and turn-in dates.
        """
        if not rubric_text or not rubric_text.strip():
            return []

        system_prompt = (
            "You are an expert academic evaluator. Analyze the provided assignment rubric "
            "and extract each distinct grading criterion into a structured JSON list.\n\n"
            "CRITICAL EXCLUSIONS - ADMINISTRATIVE & SUBMISSION DETAILS:\n"
            "- NEVER include criteria specifying the FILE TYPE or format the assignment is required to be written in or submitted as (e.g. '.pdf', '.docx', '.doc', 'Word document', file upload format, file type requirements).\n"
            "- NEVER include criteria specifying WHEN THE ASSIGNMENT IS SUPPOSED TO BE TURNED IN or due dates (e.g. 'due date', 'due by', 'due on', 'turn in by', 'turn-in date', 'deadline', 'submitted by 11:59 PM', 'late policy', 'submission time').\n"
            "- Only extract substantive academic, intellectual, analytical, content, structural, formatting style (e.g. MLA/APA citations), or grading criteria for the work itself.\n\n"
            "CRITICAL WORD COUNT & 'WORDS PER POINT' INSTRUCTION:\n"
            "- Pay careful attention to word limits: rubrics often state '__ words per point', '__ words per bullet', '__ words per question', or '__ words each'.\n"
            "- Understand that this is a PER-POINT requirement for that specific item, NOT the total word count for the entire assignment!\n"
            "- Explicitly include any per-point word requirements in the criterion's 'description' (e.g. 'Must provide at least 50 words for this point').\n"
            "- Never confuse a per-point word requirement with the overall paper length.\n\n"
            "Respond ONLY with a JSON array where each item has:\n"
            "- 'title': Short descriptive name of the criterion (e.g. 'Thesis Statement', 'Evidence & Analysis', 'Mechanics & MLA')\n"
            "- 'description': What is required to earn full marks for this criterion (including any per-point word count constraints)\n"
            "- 'target_score': Points or percentage if stated (e.g. '25 pts', 'Exemplary', '20%') or null\n"
            "Do NOT include any markdown code blocks or text outside the JSON array."
        )

        user_prompt = f"Rubric content to analyze:\n\n{rubric_text[:6000]}"

        ai = self.active_ai_client or self.ai_client
        try:
            if ai:
                resp = ai.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
                clean_json = re.sub(r"^```(?:json)?\s*", "", resp.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json.strip(), flags=re.MULTILINE).strip()
                try:
                    items = json.loads(clean_json)
                except Exception:
                    match_arr = re.search(r"\[[\s\S]*\]", resp)
                    items = json.loads(match_arr.group(0)) if match_arr else []
                criteria = []
                for itm in items:
                    if isinstance(itm, dict):
                        title = str(itm.get("title", "Requirement")).strip()
                        desc = str(itm.get("description", "")).strip()
                        if self.is_administrative_criterion(title, desc):
                            continue
                        criteria.append(
                            RubricCriterion(
                                title=title,
                                description=desc,
                                target_score=itm.get("target_score"),
                                fulfilled=False,
                            )
                        )
                if criteria:
                    return criteria
        except Exception as e:
            logger.warning(f"AI rubric parsing encountered error: {e}. Falling back to rule-based lines.")

        # Rule-based fallback: split lines with bullet points or numbers
        criteria = []
        for line in rubric_text.splitlines():
            line = line.strip()
            if line and (line.startswith(("-", "*", "•")) or re.match(r"^\d+[\.\)]", line)):
                clean_line = re.sub(r"^[-*•\d\.\)\s]+", "", line).strip()
                if len(clean_line) > 5 and not self.is_administrative_criterion(clean_line, clean_line):
                    criteria.append(
                        RubricCriterion(
                            title=clean_line[:40],
                            description=clean_line,
                            fulfilled=False,
                        )
                    )
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
            num_q = constraints.get("num_items") or criteria_count or 1
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
                clean_json = re.sub(r"^```(?:json)?\s*", "", resp.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json.strip(), flags=re.MULTILINE)
                data = json.loads(clean_json)
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

    def get_sections_needing_improvement(
        self,
        project: PlaygroundProject,
        teacher_report: Dict[str, Any],
    ) -> List[SectionDraft]:
        """
        Identifies which sections are linked to unfulfilled rubric criteria,
        lost points, or specific areas for improvement.
        Falls back to all sections if general feedback applies or none specifically mapped.
        """
        crit_evals = teacher_report.get("criteria_evaluations", [])
        unfulfilled_crit_ids = set()
        for ev in crit_evals:
            is_fulfilled = ev.get("fulfilled", True)
            score = ev.get("score")
            max_s = ev.get("max_score")
            has_lost_points = (score is not None and max_s is not None and max_s > 0 and (score / max_s) < 0.9)
            if not is_fulfilled or has_lost_points:
                if "id" in ev and ev["id"]:
                    unfulfilled_crit_ids.add(str(ev["id"]))
                if "title" in ev and ev["title"]:
                    unfulfilled_crit_ids.add(ev["title"].lower().strip())

        improvements = teacher_report.get("areas_for_improvement", [])
        improvements_text = " ".join(improvements).lower()

        targeted: List[SectionDraft] = []
        for sec in project.sections:
            matched = False
            for cid in sec.criteria_ids:
                if str(cid) in unfulfilled_crit_ids:
                    matched = True
                    break

            if not matched:
                sec_crit_titles = [c.title.lower().strip() for c in project.rubric_criteria if c.id in sec.criteria_ids]
                for ct in sec_crit_titles:
                    if ct in unfulfilled_crit_ids:
                        matched = True
                        break

            if not matched and improvements_text:
                if sec.title.lower() in improvements_text:
                    matched = True

            if matched:
                targeted.append(sec)

        # Fallback: If no specific section matched, but score is not perfect (or improvements listed),
        # target all sections so the paper genuinely improves!
        if not targeted and (improvements or teacher_report.get("numerical_score", 100) < 95):
            targeted = list(project.sections)

        return targeted

    def rewrite_and_humanize_sections_with_feedback(
        self,
        project: PlaygroundProject,
        teacher_report: Dict[str, Any],
        humanizer_bridge: PlaygroundHumanizerBridge,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> List[SectionDraft]:
        """
        Executes a targeted rewrite and humanization pass across sections needing improvement
        based on Teacher AI feedback and rubric evaluation.
        Reports progress via progress_callback(status_text, fractional_progress 0.0-1.0).
        """
        targeted = self.get_sections_needing_improvement(project, teacher_report)
        if not targeted:
            return project.sections

        crit_evals = teacher_report.get("criteria_evaluations", [])
        crit_map = {}
        for ev in crit_evals:
            if "id" in ev and ev["id"]:
                crit_map[str(ev["id"])] = ev
            if "title" in ev and ev["title"]:
                crit_map[ev["title"].lower().strip()] = ev

        overall_fb = teacher_report.get("overall_feedback", "") or teacher_report.get("summary", "")
        improvements = teacher_report.get("areas_for_improvement", [])
        imp_bullets = "\n".join(f"- {imp}" for imp in improvements) if improvements else "Address instructor feedback."

        total_targeted = len(targeted)
        solver = WrittenSolver()

        # Step 1: Rewrite Targeted Sections
        for idx, sec in enumerate(targeted):
            if progress_callback:
                frac = (idx / total_targeted) * 0.45  # 0% to 45%
                progress_callback(f"Revising section '{sec.title}' ({idx + 1}/{total_targeted})...", frac)

            sec_crit_fb = []
            for cid in sec.criteria_ids:
                ev = crit_map.get(str(cid))
                if ev:
                    fb = ev.get("feedback", "").strip()
                    title = ev.get("title", "")
                    sec_crit_fb.append(f"Rubric Requirement '{title}': {fb}")

            sec_crit_text = "\n".join(sec_crit_fb) if sec_crit_fb else "Ensure high academic rigor and rubric compliance."

            min_words = sec.target_word_count
            target_words = int(min_words * 1.10)
            max_allowed = int(min_words * 1.20)
            current_text = sec.get_active_text()

            system_prompt = (
                "You are an expert student academic writer revising a paper section strictly based on instructor feedback.\n"
                "RULES:\n"
                f"1. Target Length: Approximately {target_words} words (strict range: {min_words} to {max_allowed} words). Do NOT exceed {max_allowed} words.\n"
                "2. Faithfully incorporate the instructor's critiques, rubric requirements, and improvement suggestions.\n"
                "3. Elevate analytical depth, clarity, transitions, and evidence while retaining factual accuracy.\n"
                "4. Return ONLY the revised section text without markdown fences, headers, or conversational intros."
            )

            user_prompt = (
                f"PAPER DETAILS:\n"
                f"Title: {project.title}\n"
                f"Section: {sec.title}\n"
                f"Goal: {sec.goal_summary}\n"
                f"Target Words: ~{sec.target_word_count} words (Acceptable range: {min_words} - {max_allowed})\n\n"
                f"CURRENT SECTION DRAFT:\n{current_text}\n\n"
                f"INSTRUCTOR CRITIQUE & GENERAL FEEDBACK:\n{overall_fb}\n\n"
                f"KEY AREAS FOR IMPROVEMENT:\n{imp_bullets}\n\n"
                f"RUBRIC CRITERIA FEEDBACK FOR THIS SECTION:\n{sec_crit_text}\n\n"
                "Provide the complete revised section text:"
            )

            revised_raw = ""
            client = self.active_ai_client
            if client:
                try:
                    revised_raw = client.generate_text_response(
                        prompt=user_prompt,
                        system_instruction=system_prompt,
                    )
                except Exception as e:
                    logger.error(f"Teacher feedback rewrite failed for section '{sec.title}': {e}")
                    revised_raw = current_text
            else:
                revised_raw = current_text

            revised_raw = solver.apply_word_limits(
                revised_raw,
                min_words=min_words,
                max_words=max_allowed,
                buffer_pct=0.15,
            )
            sec.raw_ai_text = revised_raw.strip()
            sec.refinement_history.append(f"Teacher Feedback Revision ({time.strftime('%H:%M:%S')})")

        # Step 2: Humanize Targeted Sections
        for idx, sec in enumerate(targeted):
            if progress_callback:
                frac = 0.45 + (idx / total_targeted) * 0.40  # 45% to 85%
                progress_callback(f"Humanizing section '{sec.title}' ({idx + 1}/{total_targeted})...", frac)

            min_words = sec.target_word_count
            max_allowed = int(min_words * 1.20)

            if humanizer_bridge:
                try:
                    h_res = humanizer_bridge.humanize_text(
                        text=sec.raw_ai_text,
                        tone=self.config.humanizer_tone if self.config else "academic",
                        level=self.config.humanizer_reading_level if self.config else "college",
                        mode=self.config.humanizer_mode if self.config else "budget",
                    )
                    h_text = h_res.get("humanized_text", sec.raw_ai_text).strip()
                    sec.humanized_text = solver.apply_word_limits(
                        h_text,
                        min_words=min_words,
                        max_words=max_allowed,
                        buffer_pct=0.15,
                    ).strip()
                    sec.final_text = sec.humanized_text
                except Exception as e:
                    logger.error(f"Humanizing failed for section '{sec.title}': {e}")
                    sec.final_text = sec.raw_ai_text
            else:
                sec.final_text = sec.raw_ai_text

        return targeted
