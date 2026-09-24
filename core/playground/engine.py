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

    def parse_rubric(self, rubric_text: str) -> List[RubricCriterion]:
        """
        Parses raw text or OCR output of a rubric into structured RubricCriterion objects.
        """
        if not rubric_text or not rubric_text.strip():
            return []

        system_prompt = (
            "You are an expert academic evaluator. Analyze the provided assignment rubric "
            "and extract each distinct grading criterion into a structured JSON list.\n\n"
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

        try:
            if self.ai_client:
                resp = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
                clean_json = re.sub(r"^```(?:json)?\s*", "", resp.strip(), flags=re.MULTILINE)
                clean_json = re.sub(r"\s*```$", "", clean_json.strip(), flags=re.MULTILINE)
                items = json.loads(clean_json)
                criteria = []
                for itm in items:
                    if isinstance(itm, dict):
                        criteria.append(
                            RubricCriterion(
                                title=itm.get("title", "Requirement"),
                                description=itm.get("description", ""),
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
                if len(clean_line) > 5:
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
