"""
Unit tests for AI Visual Double-Check of question and selected answers
before advancing or submitting in AVA School Assistant 2.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
from PIL import Image

from config import ConfigManager
from core.ai_client import AIClient
from core.assistant_engine import AssistantEngine, EngineState


class TestDoubleCheck(unittest.TestCase):

    def setUp(self):
        self.config_manager = ConfigManager()
        self.config_manager.config.api_key = "mock_api_key_test_12345"
        self.config_manager.config.reading_delay_enabled = False
        self.config_manager.config.action_delay = 0.01
        self.config_manager.config.auto_next_delay = 0.01
        self.config_manager.config.autonomous_mode = True
        self.config_manager.config.double_check_enabled = True
        self.config_manager.config.max_double_check_retries = 2

    def test_ai_client_double_check_passed(self):
        """Verifies AIClient.double_check_solution with a clean match."""
        client = AIClient(provider="gemini", api_key="mock_key")
        with patch.object(client, "_call_gemini") as mock_call:
            mock_call.return_value = json.dumps({
                "double_check_passed": True,
                "messed_up": False,
                "issue_type": "none",
                "currently_selected_summary": "Option C is checked.",
                "details": "Selection matches correct answer.",
                "corrective_actions": []
            })
            res = client.double_check_solution(
                base64_image="mock_b64",
                question="What is 2+2?",
                intended_answer="4",
                intended_actions=[{"type": "click", "x": 500, "y": 500}]
            )
            self.assertTrue(res["double_check_passed"])
            self.assertFalse(res["messed_up"])
            self.assertEqual(res["issue_type"], "none")
            self.assertEqual(len(res["corrective_actions"]), 0)

    def test_ai_client_double_check_wrong_option_mapping(self):
        """Verifies AIClient.double_check_solution correctly maps corrective actions."""
        client = AIClient(provider="gemini", api_key="mock_key")
        with patch.object(client, "_call_gemini") as mock_call:
            mock_call.return_value = json.dumps({
                "double_check_passed": False,
                "messed_up": True,
                "issue_type": "wrong_option",
                "currently_selected_summary": "Option B is checked instead of C.",
                "details": "Clicked wrong option.",
                "corrective_actions": [
                    {"type": "click", "x": 500, "y": 600, "description": "Click Option C"}
                ]
            })
            res = client.double_check_solution(
                base64_image="mock_b64",
                question="What is 2+2?",
                intended_answer="4",
                intended_actions=[{"type": "click", "x": 500, "y": 400}],
                image_width=1000,
                image_height=1000,
                scale_x=1.0,
                scale_y=1.0
            )
            self.assertFalse(res["double_check_passed"])
            self.assertTrue(res["messed_up"])
            self.assertEqual(res["issue_type"], "wrong_option")
            self.assertEqual(len(res["corrective_actions"]), 1)
            # Coordinates mapped
            self.assertEqual(res["corrective_actions"][0]["screen_x"], 500)
            self.assertEqual(res["corrective_actions"][0]["screen_y"], 600)

    def test_engine_double_check_clean_pass_proceeds_to_advance(self):
        """Verifies that when double-check passes cleanly, auto-advance proceeds."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.click = MagicMock()
        engine.executor.ensure_scrolled_view = MagicMock()
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine.capture.capture_and_encode = MagicMock(return_value=("b64", 1000, 1000, 1.0, 1.0, 0, 0))

        mock_ai = MagicMock()
        mock_ai.double_check_solution.return_value = {
            "double_check_passed": True,
            "messed_up": False,
            "issue_type": "none",
            "currently_selected_summary": "Option B is selected.",
            "details": "Match verified.",
            "corrective_actions": []
        }
        engine._custom_ai_client = mock_ai

        engine.last_result = {
            "question": "Sample Question",
            "answer": "B",
            "actions": [{"type": "click", "x": 400, "y": 400, "screen_x": 400, "screen_y": 400}],
            "next_button": {"x": 800, "y": 900, "screen_x": 800, "screen_y": 900, "in_scrolled_view": False},
            "advance_action": "click_button",
            "evaluation_status": "unsubmitted"
        }

        with patch.object(engine, "trigger_next_button") as mock_next:
            engine.execute_current_solution()
            mock_ai.double_check_solution.assert_called_once()
            self.assertTrue(engine.last_result.get("ready_to_advance"))
            mock_next.assert_called_once()

    def test_engine_double_check_detects_wrong_option_and_corrects(self):
        """Verifies that when double-check detects a wrong option, corrective actions are executed."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.click = MagicMock()
        engine.executor.ensure_scrolled_view = MagicMock()
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine.capture.capture_and_encode = MagicMock(return_value=("b64", 1000, 1000, 1.0, 1.0, 0, 0))

        mock_ai = MagicMock()
        # First double-check call flags wrong option; second double-check call passes
        mock_ai.double_check_solution.side_effect = [
            {
                "double_check_passed": False,
                "messed_up": True,
                "issue_type": "wrong_option",
                "currently_selected_summary": "Option A selected instead of C",
                "details": "Bot clicked Option A.",
                "corrective_actions": [
                    {"type": "click", "x": 500, "y": 600, "screen_x": 500, "screen_y": 600}
                ]
            },
            {
                "double_check_passed": True,
                "messed_up": False,
                "issue_type": "none",
                "currently_selected_summary": "Option C selected.",
                "details": "Correction confirmed.",
                "corrective_actions": []
            }
        ]
        engine._custom_ai_client = mock_ai

        engine.last_result = {
            "question": "Sample Question",
            "answer": "C",
            "actions": [{"type": "click", "x": 500, "y": 300, "screen_x": 500, "screen_y": 300}],
            "next_button": {"x": 800, "y": 900, "screen_x": 800, "screen_y": 900, "in_scrolled_view": False},
            "advance_action": "click_button",
            "evaluation_status": "unsubmitted"
        }

        with patch.object(engine, "trigger_next_button") as mock_next:
            engine.execute_current_solution()
            self.assertEqual(mock_ai.double_check_solution.call_count, 2)
            self.assertTrue(engine.last_result.get("ready_to_advance"))
            mock_next.assert_called_once()

    def test_engine_double_check_detects_unclicked_option_and_corrects(self):
        """Verifies that when double-check detects an unclicked option, corrective click is performed."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.click = MagicMock()
        engine.executor.ensure_scrolled_view = MagicMock()
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine.capture.capture_and_encode = MagicMock(return_value=("b64", 1000, 1000, 1.0, 1.0, 0, 0))

        mock_ai = MagicMock()
        mock_ai.double_check_solution.side_effect = [
            {
                "double_check_passed": False,
                "messed_up": True,
                "issue_type": "unclicked_option",
                "currently_selected_summary": "No options currently selected",
                "details": "Click missed radio button.",
                "corrective_actions": [
                    {"type": "click", "x": 450, "y": 550, "screen_x": 450, "screen_y": 550}
                ]
            },
            {
                "double_check_passed": True,
                "messed_up": False,
                "issue_type": "none",
                "currently_selected_summary": "Option selected successfully.",
                "details": "Confirmed.",
                "corrective_actions": []
            }
        ]
        engine._custom_ai_client = mock_ai

        engine.last_result = {
            "question": "Sample Question",
            "answer": "B",
            "actions": [{"type": "click", "x": 450, "y": 550, "screen_x": 450, "screen_y": 550}],
            "next_button": {"x": 800, "y": 900, "screen_x": 800, "screen_y": 900, "in_scrolled_view": False},
            "advance_action": "click_button",
            "evaluation_status": "unsubmitted"
        }

        with patch.object(engine, "trigger_next_button") as mock_next:
            engine.execute_current_solution()
            self.assertEqual(mock_ai.double_check_solution.call_count, 2)
            mock_next.assert_called_once()

    def test_double_check_disabled_by_config(self):
        """Verifies that if double_check_enabled is False, no AI double-check call occurs."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config.double_check_enabled = False
        mock_ai = MagicMock()
        engine._custom_ai_client = mock_ai

        actions = [{"type": "click", "x": 500, "y": 500}]
        engine.last_result = {"question": "Q", "answer": "A", "actions": actions}

        result = engine._double_check_answers_on_screen(actions)
        self.assertTrue(result)
        mock_ai.double_check_solution.assert_not_called()


if __name__ == "__main__":
    unittest.main()
