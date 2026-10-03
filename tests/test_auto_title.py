"""Focused regression tests for rubric-based project title auto-generation."""

import unittest
from unittest.mock import MagicMock

from core.playground.engine import PlaygroundEngine
from core.playground.project_model import PlaygroundProject, RubricCriterion


class TestAutoTitleGeneration(unittest.TestCase):

    def make_project(self, topic="", criteria=None, rubric_raw_text=""):
        project = PlaygroundProject()
        project.topic_description = topic
        project.rubric_criteria = criteria or []
        project.rubric_raw_text = rubric_raw_text
        return project

    def test_returns_empty_when_no_context_available(self):
        engine = PlaygroundEngine(ai_client=None)
        project = self.make_project()

        title = engine.generate_project_title(project)

        self.assertEqual(title, "")

    def test_uses_ai_generated_title_when_available(self):
        ai_client = MagicMock()
        ai_client.api_key = "fake-key"
        ai_client.generate_text_response.return_value = "The Causes of the French Revolution"
        engine = PlaygroundEngine(ai_client=ai_client)
        project = self.make_project(
            topic="Discuss the causes of the French Revolution.",
            criteria=[RubricCriterion(title="Thesis Statement", description="Clear thesis required.")],
        )

        title = engine.generate_project_title(project)

        self.assertEqual(title, "The Causes of the French Revolution")
        ai_client.generate_text_response.assert_called_once()

    def test_strips_quotes_and_code_fences_from_ai_response(self):
        ai_client = MagicMock()
        ai_client.api_key = "fake-key"
        ai_client.generate_text_response.return_value = '```\n"Renewable Energy Transitions"\n```'
        engine = PlaygroundEngine(ai_client=ai_client)
        project = self.make_project(topic="Renewable energy sources and their impact.")

        title = engine.generate_project_title(project)

        self.assertEqual(title, "Renewable Energy Transitions")

    def test_falls_back_to_topic_description_when_ai_unavailable(self):
        engine = PlaygroundEngine(ai_client=None)
        project = self.make_project(
            topic="Climate change impacts on coastal ecosystems. Additional context follows.",
        )

        title = engine.generate_project_title(project)

        self.assertEqual(title, "Climate change impacts on coastal ecosystems")

    def test_falls_back_to_rubric_criteria_when_no_topic(self):
        engine = PlaygroundEngine(ai_client=None)
        project = self.make_project(
            criteria=[
                RubricCriterion(title="Thesis Statement", description="..."),
                RubricCriterion(title="Evidence & Analysis", description="..."),
            ],
        )

        title = engine.generate_project_title(project)

        self.assertEqual(title, "Project on Thesis Statement, Evidence & Analysis")

    def test_excludes_administrative_criteria_from_fallback(self):
        engine = PlaygroundEngine(ai_client=None)
        project = self.make_project(
            criteria=[
                RubricCriterion(title="Due Date", description="Submit by 11:59 PM."),
                RubricCriterion(title="Thesis Statement", description="..."),
            ],
        )

        title = engine.generate_project_title(project)

        self.assertEqual(title, "Project on Thesis Statement")

    def test_falls_back_to_ai_exception_handling(self):
        ai_client = MagicMock()
        ai_client.api_key = "fake-key"
        ai_client.generate_text_response.side_effect = RuntimeError("network error")
        engine = PlaygroundEngine(ai_client=ai_client)
        project = self.make_project(topic="A study of ocean acidification.")

        title = engine.generate_project_title(project)

        self.assertEqual(title, "A study of ocean acidification")


if __name__ == "__main__":
    unittest.main()
