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
            "and extract each distinct grading criterion into a structured JSON list.\n"
            "Respond ONLY with a JSON array where each item has:\n"
            "- 'title': Short descriptive name of the criterion (e.g. 'Thesis Statement', 'Evidence & Analysis', 'Mechanics & MLA')\n"
            "- 'description': What is required to earn full marks for this criterion\n"
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

    def generate_outline(self, project: PlaygroundProject) -> List[SectionDraft]:
        """
        Creates an ordered sequence of section drafts mapped to the project's rubric criteria,
        sources, and target word count. Accurately shapes outlines for multi-question prompts (e.g. 50 words each).
        """
        # Check for multi-part or specific word requirements in prompt, title, and rubrics
        combined_text = f"{project.title}\n{project.topic_description}\n" + "\n".join([f"{c.title} {c.description}" for c in project.rubric_criteria])
        constraints = WrittenSolver.extract_detailed_word_constraints(combined_text)

        multi_part_note = ""
        if constraints.get("is_multi_part") and constraints.get("num_items") and constraints.get("per_item_words"):
            num_q = constraints["num_items"]
            per_q = constraints["per_item_words"]
            calculated_total = per_q * num_q
            project.target_total_words = calculated_total
            multi_part_note = (
                f"\nCRITICAL MULTI-QUESTION REQUIREMENT (BELIEVABILITY):\n"
                f"- The prompt explicitly requires {num_q} questions/items with approximately {per_q} words each.\n"
                f"- You MUST create exactly {num_q} sections named 'Question 1', 'Question 2', etc. (or corresponding question titles).\n"
                f"- Each section's target_word_count MUST be exactly {per_q} words.\n"
                f"- The total document target is {calculated_total} words (NOT 1000 words!).\n"
            )
        elif constraints.get("target_words") and project.target_total_words == 1000:
            project.target_total_words = constraints["target_words"]

        system_prompt = (
            "You are an academic project architect. Given the document title, topic, target word count, "
            "and rubric criteria, create a coherent, comprehensive outline.\n"
            f"{multi_part_note}\n"
            "Respond ONLY with a JSON array where each object has:\n"
            "- 'title': Section heading (e.g. 'Question 1', 'Introduction & Thesis', 'Historical Context')\n"
            "- 'goal_summary': Detailed description of what arguments, evidence, and points this section must contain\n"
            "- 'target_word_count': Integer target word count for this specific section (must sum close to the total target)\n"
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
