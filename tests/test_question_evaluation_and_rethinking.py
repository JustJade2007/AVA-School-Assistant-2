"""
Unit and integration tests for Question Evaluation Status & Rethinking System.
Verifies that:
1. Platform evaluation status ('correct', 'incorrect', 'unsubmitted') is accurately parsed and normalized.
2. An answer marked 'incorrect' strictly forces is_rethinking=True, ready_to_advance=False, and is_answered=False.
3. Multi-part questions aggregate evaluation status (any incorrect -> whole question incorrect & rethinking).
4. LocalVisualVerifier accurately detects red error vs green success clusters.
5. Post-submission evaluation check halts auto-advance if the platform rejects the submitted answer.
6. AssistantEngine correctly enforces question evaluation status before considering a question answered.
"""

import unittest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw

from core.ai_client import AIClient
from core.local_verifier import LocalVisualVerifier
from core.assistant_engine import AssistantEngine, EngineState
from config import AppConfig, ConfigManager


class TestQuestionEvaluationAndRethinking(unittest.TestCase):
    """Tests for platform evaluation status detection and answer rethinking logic."""

    def setUp(self):
        self.verifier = LocalVisualVerifier()
        self.config_manager = ConfigManager()
        self.engine = AssistantEngine(config_manager=self.config_manager)

    def test_ai_client_normalization_single_part_incorrect(self):
        """Verifies that an incorrect single-part question forces is_rethinking=True and ready_to_advance=False."""
        client = AIClient.__new__(AIClient)
        raw_result = {
            "question": "Solve for x: 2x + 4 = 10",
            "answer": "x = 3",
            "evaluation_status": "incorrect",
            "platform_feedback": "Incorrect. Try again.",
            "ready_to_advance": True,  # Model mistakenly claimed ready to advance
            "rethink_reasoning": "Previous attempt entered '3' without simplification; recheck steps.",
            "actions": [{"type": "click", "x": 500, "y": 500}]
        }

        # Map coordinates / normalize
        client._map_coordinates(raw_result, 1000, 1000, 1.0, 1.0, 0, 0, 1.0, 1.0, 0, 0, "normalized")

        self.assertEqual(raw_result["evaluation_status"], "incorrect")
        self.assertTrue(raw_result["is_rethinking"])
        # Critical invariant: must NOT advance if incorrect
        self.assertFalse(raw_result["ready_to_advance"])
        self.assertIn("Previous attempt", raw_result["rethink_reasoning"])

    def test_ai_client_normalization_multipart_propagation(self):
        """Verifies that if any part of a multi-part question is incorrect, the entire question rethinks."""
        client = AIClient.__new__(AIClient)
        raw_result = {
            "summary": "Multi-part quiz question",
            "ready_to_advance": True,
            "items": [
                {
                    "part_id": "1",
                    "evaluation_status": "correct",
                    "current_state": "answered_correct",
                    "needs_action": False,
                    "correct_answer": "42"
                },
                {
                    "part_id": "2",
                    "evaluation_status": "wrong",  # Synonym for incorrect
                    "current_state": "wrong",
                    "needs_action": True,
                    "correct_answer": "3/4",
                    "rethink_reasoning": "Platform requires reduced fraction rather than 0.75 decimal."
                }
            ]
        }

        client._map_coordinates(raw_result, 1000, 1000, 1.0, 1.0, 0, 0, 1.0, 1.0, 0, 0, "normalized")

        # Top-level should be marked incorrect
        self.assertEqual(raw_result["evaluation_status"], "incorrect")
        self.assertTrue(raw_result["is_rethinking"])
        self.assertFalse(raw_result["ready_to_advance"])
        self.assertIn("reduced fraction", raw_result["rethink_reasoning"])
        self.assertEqual(raw_result["items"][0]["evaluation_status"], "correct")
        self.assertEqual(raw_result["items"][1]["evaluation_status"], "incorrect")

    def test_ai_client_all_correct_status(self):
        """Verifies that when all parts are correct, top-level evaluation_status is correct."""
        client = AIClient.__new__(AIClient)
        raw_result = {
            "summary": "All parts completed",
            "items": [
                {
                    "part_id": "A",
                    "evaluation_status": "graded_correct",
                    "needs_action": False,
                    "correct_answer": "Paris"
                },
                {
                    "part_id": "B",
                    "evaluation_status": "passed",
                    "needs_action": False,
                    "correct_answer": "Berlin"
                }
            ]
        }

        client._map_coordinates(raw_result, 1000, 1000, 1.0, 1.0, 0, 0, 1.0, 1.0, 0, 0, "normalized")

        self.assertEqual(raw_result["evaluation_status"], "correct")
        self.assertFalse(raw_result["is_rethinking"])

    def test_local_verifier_platform_marker_detection_incorrect(self):
        """Verifies detection of red platform error markers and banners."""
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        d = ImageDraw.Draw(img)
        # Draw prominent red error badge / text cluster (RGB ~ (220, 38, 38))
        d.rectangle([20, 20, 120, 50], fill=(220, 38, 38))
        d.text((30, 25), "Incorrect. Try again.", fill=(255, 255, 255))

        res = self.verifier.detect_platform_evaluation_markers(img)
        self.assertEqual(res["status"], "incorrect")
        self.assertTrue(res["is_incorrect"])
        self.assertGreater(res["confidence"], 0.5)

    def test_local_verifier_platform_marker_detection_correct(self):
        """Verifies detection of green platform success checkmarks / banners."""
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        d = ImageDraw.Draw(img)
        # Draw prominent green success badge / banner (RGB ~ (22, 163, 74))
        d.rectangle([20, 20, 120, 50], fill=(22, 163, 74))
        d.text((30, 25), "Correct! Well done.", fill=(255, 255, 255))

        res = self.verifier.detect_platform_evaluation_markers(img)
        self.assertEqual(res["status"], "correct")
        self.assertTrue(res["is_correct"])
        self.assertGreater(res["confidence"], 0.5)

    def test_local_verifier_platform_marker_detection_neutral(self):
        """Verifies unsubmitted status when no red/green evaluation markers exist."""
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        d = ImageDraw.Draw(img)
        # Ordinary black text on white background
        d.text((20, 20), "What is the capital of France?", fill=(30, 30, 30))
        d.rectangle([20, 50, 180, 80], outline=(180, 180, 180), width=1)

        res = self.verifier.detect_platform_evaluation_markers(img)
        self.assertEqual(res["status"], "unsubmitted")
        self.assertFalse(res["is_incorrect"])
        self.assertFalse(res["is_correct"])

    def test_verify_post_submission_evaluation_detects_error(self):
        """Verifies that post-submission check detects red error banner appearing after submission."""
        before_img = Image.new("RGB", (200, 200), (255, 255, 255))
        after_img = before_img.copy()
        d = ImageDraw.Draw(after_img)
        # Red error badge introduced in after_img
        d.rectangle([20, 20, 140, 50], fill=(239, 68, 68))
        d.text((25, 25), "Incorrect answer.", fill=(255, 255, 255))

        res = self.verifier.verify_post_submission_evaluation(before_img, after_img)
        self.assertTrue(res["is_incorrect"])
        self.assertEqual(res["status"], "incorrect")

    def test_engine_check_question_evaluation_status_rules(self):
        """Verifies engine.check_question_evaluation_status rules for correct, incorrect, and unsubmitted."""
        # 1. Incorrect solution: NEVER considered answered, NEVER ready to advance
        bad_sol = {
            "evaluation_status": "incorrect",
            "is_rethinking": True,
            "rethink_reasoning": "Rethinking calculation error",
            "actions": [{"type": "click", "screen_x": 100, "screen_y": 100}]
        }
        res_bad = self.engine.check_question_evaluation_status(bad_sol)
        self.assertFalse(res_bad["is_answered"])
        self.assertFalse(res_bad["ready_to_advance"])
        self.assertTrue(res_bad["is_incorrect"])
        self.assertTrue(res_bad["is_rethinking"])

        # 2. Correct solution: Answered and ready to advance
        good_sol = {
            "evaluation_status": "correct",
            "actions": []
        }
        res_good = self.engine.check_question_evaluation_status(good_sol)
        self.assertTrue(res_good["is_answered"])
        self.assertTrue(res_good["ready_to_advance"])
        self.assertFalse(res_good["is_incorrect"])

        # 3. Unsubmitted solution with remaining actions: not answered yet
        unsub_sol = {
            "evaluation_status": "unsubmitted",
            "actions": [{"type": "type_text", "text": "42"}]
        }
        res_unsub = self.engine.check_question_evaluation_status(unsub_sol)
        self.assertFalse(res_good_unsub := res_unsub["is_answered"])
        self.assertFalse(res_unsub["ready_to_advance"])

    def test_engine_skips_actions_if_already_verified_correct(self):
        """Verifies that an already-correct question does not execute redundant actions."""
        self.engine.current_solution = {
            "evaluation_status": "correct",
            "answer": "Option A",
            "actions": [{"type": "click", "screen_x": 200, "screen_y": 200}],
            "next_button": {"screen_x": 500, "screen_y": 500}
        }
        self.engine.state = EngineState.WAITING_CONFIRMATION

        with patch.object(self.engine, "trigger_next_question") as mock_next:
            self.engine.confirm_and_execute()
            # In manual mode, it should recognize already correct and prompt next
            self.assertIn("already marked CORRECT", self.engine.last_verification_detail)

    def test_engine_advances_after_correcting_incorrect_answer(self):
        """
        CRITICAL BUG REPRODUCTION & FIX VERIFICATION:
        When a question was marked 'incorrect' on platform, ready_to_advance was initially False.
        After AI rethinks and enters the corrected answer (zero-token verified),
        the engine MUST reset ready_to_advance to True and press the Next button, NOT give up!
        """
        self.engine.config_manager.config.autonomous_mode = True
        self.engine.config_manager.config.auto_next = True

        # Solution entering the rethought answer (initially ready_to_advance is False due to incorrect status)
        self.engine.last_result = {
            "evaluation_status": "incorrect",
            "is_rethinking": True,
            "rethink_reasoning": "Platform rejected earlier answer 12. Corrected to 24.",
            "ready_to_advance": False,  # Forced False during rethink analysis
            "actions": [{"type": "type_text", "text": "24", "screen_x": 450, "screen_y": 550, "verified": True}],
            "next_button": {"screen_x": 900, "screen_y": 950}
        }

        self.engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        self.engine.trigger_next_button = MagicMock()
        self.engine.trigger_solve = MagicMock()

        self.engine.execute_current_solution()

        # Invariant 1: ready_to_advance MUST be restored to True
        self.assertTrue(self.engine.last_result["ready_to_advance"])
        # Invariant 2: is_rethinking MUST be cleared
        self.assertFalse(self.engine.last_result["is_rethinking"])
        # Invariant 3: Next button MUST be pressed (never aborted or given up!)
        self.engine.trigger_next_button.assert_called_once()
        # Invariant 4: Autonomous loop MUST continue
        self.engine.trigger_solve.assert_called_once()

    def test_engine_advances_after_retrying_missed_action(self):
        """
        Verifies that if a click missed initially (causing ready_to_advance=False),
        upon successfully executing and confirming the corrected action, ready_to_advance is True
        and auto-advance clicks Next.
        """
        self.engine.config_manager.config.autonomous_mode = True
        self.engine.config_manager.config.auto_next = True

        # Simulation: previous attempt failed zero-token verification, setting ready_to_advance=False and action_missed=True
        self.engine.last_result = {
            "evaluation_status": "unsubmitted",
            "action_missed": True,
            "ready_to_advance": False,  # from previous missed action
            "actions": [{"type": "click", "screen_x": 500, "screen_y": 500, "verified": True}],
            "next_button": {"screen_x": 800, "screen_y": 900}
        }

        self.engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        self.engine.trigger_next_button = MagicMock()
        self.engine.trigger_solve = MagicMock()

        self.engine.execute_current_solution()

        self.assertTrue(self.engine.last_result["ready_to_advance"])
        self.engine.trigger_next_button.assert_called_once()
        self.engine.trigger_solve.assert_called_once()

    def test_next_button_transition_fallback_to_discovery(self):
        """
        Verifies that if clicking next_button does not transition the screen,
        the engine immediately falls back to dynamic navigation button discovery.
        """
        self.engine.config_manager.config.autonomous_mode = False
        self.engine.config_manager.config.auto_next = True
        self.engine.config_manager.config.local_verification_enabled = True

        self.engine.last_result = {
            "ready_to_advance": True,
            "actions": [{"type": "click", "screen_x": 500, "screen_y": 500, "verified": True}],
            "next_button": {"screen_x": 800, "screen_y": 900}
        }

        dummy_img = Image.new("RGB", (100, 100), (255, 255, 255))
        self.engine.capture.capture_screen = MagicMock(return_value=dummy_img)
        self.engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        self.engine.trigger_next_button = MagicMock()
        # Mock transition failure (e.g. diff was zero, page stayed identical)
        self.engine.verifier.verify_screen_transition = MagicMock(return_value={"transitioned": False, "details": "no change"})
        self.engine._discover_and_click_next_button = MagicMock(return_value=True)

        self.engine.execute_current_solution()

        self.engine.trigger_next_button.assert_called_once()
        # Must fall back to discover_and_click_next_button!
        self.engine._discover_and_click_next_button.assert_called_once()


if __name__ == "__main__":
    unittest.main()
