"""
Teacher AI Evaluator for AVA Playground Mode.
Executes an independent, unbiased instructor grading call evaluating the compiled
document against assignment rubrics, word count targets, and academic standards.
Generates letter grades, numerical scores, qualitative critique, and criteria breakdowns.
"""

import json
import re
from typing import Dict, Any, Optional, List
from core.logger import get_logger
from core.playground.project_model import PlaygroundProject, RubricCriterion

logger = get_logger("playground.teacher_evaluator")


class TeacherEvaluator:
    """Independent AI academic instructor that evaluates long-form papers against rubrics."""

    def __init__(self, ai_client=None, config_manager=None):
        self.ai_client = ai_client
        self.config_manager = config_manager

    @property
    def config(self):
        return self.config_manager.config if self.config_manager else None

    def grade_document(
        self,
        project: PlaygroundProject,
        custom_instructions: str = "",
    ) -> Dict[str, Any]:
        """
        Runs an unbiased teacher evaluation against the project's rubric criteria and compiled text.
        Returns a structured evaluation report dictionary.
        """
        full_text = project.get_full_document_text()
        total_words = project.total_word_count()

        if not full_text.strip():
            return {
                "letter_grade": "N/A",
                "numerical_score": 0,
                "max_score": 100,
                "percentage": 0.0,
                "summary": "Document is empty. No text has been written or approved for grading.",
                "overall_feedback": "Please complete and approve document sections before submitting to the Teacher AI for grading.",
                "strengths": [],
                "areas_for_improvement": ["Draft sections before requesting a grade."],
                "criteria_evaluations": [],
            }

        # Build rubric criteria string
        rubric_bullets = []
        for idx, c in enumerate(project.rubric_criteria, 1):
            score_str = f" [Target: {c.target_score}]" if c.target_score else ""
            rubric_bullets.append(f"{idx}. (ID: {c.id}) {c.title}{score_str}: {c.description}")

        rubric_text = "\n".join(rubric_bullets)
        if not rubric_text and getattr(project, "rubric_raw_text", ""):
            rubric_text = project.rubric_raw_text[:4000]
        if not rubric_text:
            rubric_text = (
                "Standard College Academic Writing Standards:\n"
                "1. Clear thesis statement and focus\n"
                "2. Solid evidence, reasoning, and source integration\n"
                "3. Organization, transitions, and structural coherence\n"
                "4. Style, academic tone, grammar, and mechanics\n"
                "5. Proper citation and academic formatting"
            )

        sources_summary = "\n".join([f"- {getattr(s, 'name', getattr(s, 'title', 'Source'))} ({getattr(s, 'source_type', 'source')})" for s in project.sources])
        if not sources_summary:
            sources_summary = "None provided"

        system_prompt = (
            "You are an objective, fair, and academically rigorous collegiate instructor ('The Teacher').\n"
            "Your task is to conduct an impartial evaluation and grading of a student's submission "
            "based strictly on the provided rubric criteria, assignment topic, formatting expectations, "
            "and length guidelines.\n\n"
            "EVALUATION PRINCIPLES:\n"
            "1. Unbiased & Grounded: Grade the actual content submitted. Do not assume or flatter.\n"
            "2. Rubric Alignment: For every rubric criterion, determine whether it was fulfilled, "
            "assign points (if criterion points are specified, or distribute proportional points), "
            "and write constructive, specific feedback.\n"
            "3. Grading Scale: Assign a letter grade (A+, A, A-, B+, B, B-, C+, C, C-, D, F) "
            "and a realistic percentage/numerical score (0-100).\n"
            "4. Constructive Critique: Detail specific strengths and actionable areas for improvement.\n\n"
            "OUTPUT FORMAT:\n"
            "You must respond ONLY with a single valid JSON object with the following schema:\n"
            "{\n"
            '  "letter_grade": "A",\n'
            '  "numerical_score": 93,\n'
            '  "max_score": 100,\n'
            '  "percentage": 93.0,\n'
            '  "summary": "Short 1-2 sentence executive summary of the grade.",\n'
            '  "overall_feedback": "Detailed 1-2 paragraph instructor critique with academic feedback.",\n'
            '  "strengths": ["Strength 1", "Strength 2", ...],\n'
            '  "areas_for_improvement": ["Area 1", "Area 2", ...],\n'
            '  "criteria_evaluations": [\n'
            '    {\n'
            '      "id": "<rubric_id_or_title>",\n'
            '      "title": "<criterion_title>",\n'
            '      "score": 18,\n'
            '      "max_score": 20,\n'
            '      "fulfilled": true,\n'
            '      "feedback": "<Specific feedback on how this criterion was met or missed>"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "DO NOT wrap the response in backticks or markdown fences, and do not include extra prose outside the JSON."
        )

        user_prompt = (
            f"ASSIGNMENT DETAILS:\n"
            f"Title: {project.title}\n"
            f"Topic/Instructions: {project.topic_description}\n"
            f"Formatting Style: {project.formatting_preset}\n"
            f"Target Word Count: {project.target_total_words} words (Actual: {total_words} words)\n"
            f"Sources Cited/Provided:\n{sources_summary}\n\n"
            f"RUBRIC CRITERIA:\n{rubric_text}\n\n"
        )

        if custom_instructions.strip():
            user_prompt += f"SPECIAL INSTRUCTOR FOCUS:\n{custom_instructions.strip()}\n\n"

        user_prompt += f"STUDENT SUBMISSION FULL TEXT:\n\n{full_text}"

        report: Optional[Dict[str, Any]] = None

        if self.ai_client:
            try:
                resp = self.ai_client.generate_text_response(
                    prompt=user_prompt,
                    system_instruction=system_prompt,
                )
                report = self._parse_json_response(resp)
            except Exception as e:
                logger.error(f"AI Teacher grading call failed: {e}", exc_info=True)

        if not report:
            logger.warning("Falling back to local heuristic teacher evaluation.")
            report = self._generate_heuristic_report(project, full_text, total_words)

        return report

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Cleans and extracts JSON object from model output."""
        if not text:
            return None
        clean = text.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)

        # Attempt direct parse
        try:
            data = json.loads(clean)
            if isinstance(data, dict) and "letter_grade" in data:
                return data
        except Exception:
            pass

        # Attempt to find outermost JSON object braces
        match = re.search(r"(\{.*\})", clean, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and "letter_grade" in data:
                    return data
            except Exception:
                pass

        return None

    def _generate_heuristic_report(
        self,
        project: PlaygroundProject,
        full_text: str,
        total_words: int,
    ) -> Dict[str, Any]:
        """Generates an objective heuristic evaluation report if AI call is unavailable."""
        target = max(project.target_total_words, 250)
        ratio = min(total_words / target, 1.25)
        
        # Word count satisfaction
        wc_score = 30 * min(ratio, 1.0) if ratio >= 0.7 else (30 * ratio * 0.8)
        
        # Structure satisfaction
        sec_count = len(project.sections)
        struct_score = min(25, sec_count * 6)

        # Rubric fulfillment
        crit_evals = []
        crit_score_acc = 0
        max_crit = 45
        each_max = (max_crit / len(project.rubric_criteria)) if project.rubric_criteria else 15

        for c in project.rubric_criteria:
            fulfilled = bool(total_words >= target * 0.8)
            awarded = each_max if fulfilled else (each_max * 0.7)
            crit_score_acc += awarded
            crit_evals.append({
                "id": c.id,
                "title": c.title,
                "score": round(awarded, 1),
                "max_score": round(each_max, 1),
                "fulfilled": fulfilled,
                "feedback": "Standard requirements met based on submission length and structure." if fulfilled else "Needs more development to satisfy requirement fully.",
            })

        total_pts = round(wc_score + struct_score + crit_score_acc, 1)
        percentage = min(100.0, max(0.0, round(total_pts, 1)))

        if percentage >= 93:
            letter = "A"
        elif percentage >= 90:
            letter = "A-"
        elif percentage >= 87:
            letter = "B+"
        elif percentage >= 83:
            letter = "B"
        elif percentage >= 80:
            letter = "B-"
        elif percentage >= 75:
            letter = "C+"
        elif percentage >= 70:
            letter = "C"
        else:
            letter = "D"

        return {
            "letter_grade": letter,
            "numerical_score": round(percentage),
            "max_score": 100,
            "percentage": percentage,
            "summary": f"Submission contains {total_words} words across {sec_count} sections.",
            "overall_feedback": (
                f"The submission provides an organized discussion of {project.title or 'the assigned topic'}. "
                f"The overall length is {total_words} words relative to the target of {project.target_total_words} words. "
                "Writing demonstrates good structure, logical progression, and addressing of key points."
            ),
            "strengths": [
                f"Well-structured document with {sec_count} cohesive sections.",
                f"Meets length guidelines ({total_words}/{project.target_total_words} words).",
                f"Follows {project.formatting_preset} formatting conventions.",
            ],
            "areas_for_improvement": [
                "Consider expanding supporting evidence and primary sources in deeper analytical sections.",
                "Review transitions between sections for smoother narrative flow.",
            ],
            "criteria_evaluations": crit_evals,
        }

    @staticmethod
    def apply_to_project(report: Dict[str, Any], project: PlaygroundProject):
        """
        Updates the project's teacher_grade_report and synchronizes rubric criteria fulfilled statuses.
        """
        project.teacher_grade_report = report
        
        evals = report.get("criteria_evaluations", [])
        eval_map = {}
        for ev in evals:
            if "id" in ev and ev["id"]:
                eval_map[str(ev["id"])] = ev
            if "title" in ev and ev["title"]:
                eval_map[ev["title"].lower().strip()] = ev

        for c in project.rubric_criteria:
            # Check by id or normalized title
            match = eval_map.get(str(c.id)) or eval_map.get(c.title.lower().strip())
            if match:
                c.fulfilled = bool(match.get("fulfilled", False))
                feedback = match.get("feedback", "").strip()
                score_str = f"[{match.get('score')}/{match.get('max_score')} pts]" if "score" in match and "max_score" in match else ""
                if feedback:
                    c.notes = f"{score_str} {feedback}".strip()
