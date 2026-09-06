"""
Unit tests for supplementary reference sheet / scrolled view inspection
and enhanced auto-advance / navigation detection in AVA School Assistant 2.
"""

import unittest
from unittest.mock import MagicMock, patch, call
import json

from config import AppConfig, ConfigManager
from core.ai_client import AIClient
from core.assistant_engine import AssistantEngine, EngineState


class TestSupplementaryAndNavigation(unittest.TestCase):

    def setUp(self):
        self.config_manager = ConfigManager()
        self.config_manager.config.api_key = "test_mock_api_key_12345"
        self.config_manager.config.reading_delay_enabled = False
        self.config_manager.config.action_delay = 0.01
        self.config_manager.config.auto_next_delay = 0.01

    def test_gemini_multi_image_payload(self):
        client = AIClient(provider="gemini", api_key="mock_key", model_name="gemini-3.6-flash")
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": json.dumps({"answer": "42"})}]}}]
            }
            mock_post.return_value = mock_resp

            client._call_gemini(
                base64_image="main_img_b64",
                prompt="System prompt",
                extra_images=["ref_sheet_b64"]
            )

            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            parts = called_payload["contents"][0]["parts"]
            self.assertEqual(len(parts), 4)
            self.assertEqual(parts[0]["text"], "System prompt")
            self.assertEqual(parts[1]["inline_data"]["data"], "main_img_b64")
            self.assertIn("Supplementary image", parts[2]["text"])
            self.assertEqual(parts[3]["inline_data"]["data"], "ref_sheet_b64")

    def test_openai_multi_image_payload(self):
        client = AIClient(provider="openai", api_key="mock_key", model_name="gpt-4o")
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": json.dumps({"answer": "100"})}}]
            }
            mock_post.return_value = mock_resp

            client._call_openai(
                base64_image="main_img_b64",
                prompt="System prompt",
                extra_images=["scrolled_img_b64"]
            )

            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            user_content = called_payload["messages"][1]["content"]
            # Should have: main text, main image, extra text label, extra image
            self.assertEqual(len(user_content), 4)
            self.assertEqual(user_content[1]["image_url"]["url"], "data:image/jpeg;base64,main_img_b64")
            self.assertEqual(user_content[3]["image_url"]["url"], "data:image/jpeg;base64,scrolled_img_b64")

    def test_anthropic_multi_image_payload(self):
        client = AIClient(provider="anthropic", api_key="mock_key", model_name="claude-3-5-sonnet-latest")
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "content": [{"text": json.dumps({"answer": "B"})}]
            }
            mock_post.return_value = mock_resp

            client._call_anthropic(
                base64_image="main_img_b64",
                prompt="System prompt",
                extra_images=["ref_img_b64"]
            )

            mock_post.assert_called_once()
            called_payload = mock_post.call_args[1]["json"]
            user_content = called_payload["messages"][0]["content"]
            self.assertEqual(user_content[0]["source"]["data"], "main_img_b64")
            self.assertEqual(user_content[2]["source"]["data"], "ref_img_b64")

    def test_detect_navigation_button_success(self):
        client = AIClient(provider="gemini", api_key="mock_key")
        with patch.object(client, "_call_gemini") as mock_call:
            mock_call.return_value = json.dumps({
                "found": True,
                "next_button": {
                    "x": 880,
                    "y": 920,
                    "description": "Next Question button"
                }
            })

            btn = client.detect_navigation_button(
                base64_image="mock_screen_data",
                image_width=1000,
                image_height=1000
            )

            self.assertIsNotNone(btn)
            self.assertEqual(btn["x"], 880)
            self.assertEqual(btn["y"], 920)
            self.assertEqual(btn["screen_x"], 880)
            self.assertEqual(btn["screen_y"], 920)

    def test_reference_modal_inspection_pipeline(self):
        self.config_manager.config.autonomous_mode = False
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.capture.capture_and_encode = MagicMock(return_value=(
            "dummy_b64", 1000, 1000, 1.0, 1.0, 0, 0
        ))
        engine.executor.click = MagicMock()
        engine.executor.key_press = MagicMock()
        engine.execute_current_solution = MagicMock()

        # Solve screen call sequence:
        # First call returns needs_more_info (open_reference)
        # Second call returns resolved answer
        initial_result = {
            "status": "needs_more_info",
            "info_type": "open_reference",
            "reference_button": {"x": 200, "y": 150, "screen_x": 200, "screen_y": 150, "description": "Currency Chart"},
            "close_button": {"x": 800, "y": 120, "screen_x": 800, "screen_y": 120, "description": "Close button"},
            "question": "Convert USD to JPY",
            "answer": "Needs currency chart",
            "actions": []
        }
        final_result = {
            "status": "solved",
            "question": "Convert USD to JPY",
            "answer": "154.50 JPY",
            "actions": [{"type": "click", "x": 500, "y": 600, "screen_x": 500, "screen_y": 600}],
            "ready_to_advance": True
        }

        with patch("core.assistant_engine.AIClient") as mock_ai_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.solve_screen.side_effect = [initial_result, final_result]
            mock_ai_class.return_value = mock_ai_instance

            engine._run_solve_pipeline()

            # Verify click opened reference modal
            engine.executor.click.assert_any_call(200, 150)
            # Verify modal was closed via close button (using allow_variance=False)
            engine.executor.click.assert_any_call(800, 120, allow_variance=False)
            # Verify AI was re-called with extra image
            self.assertEqual(mock_ai_instance.solve_screen.call_count, 2)
            second_call_kwargs = mock_ai_instance.solve_screen.call_args_list[1][1]
            self.assertIn("extra_images", second_call_kwargs)
            self.assertEqual(len(second_call_kwargs["extra_images"]), 1)
            self.assertEqual(engine.last_result["answer"], "154.50 JPY")

    def test_scrolled_content_inspection_pipeline(self):
        self.config_manager.config.autonomous_mode = False
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.capture.capture_and_encode = MagicMock(return_value=(
            "dummy_b64", 1000, 1000, 1.0, 1.0, 0, 0
        ))
        engine.executor.scroll = MagicMock()
        engine.execute_current_solution = MagicMock()

        initial_result = {
            "status": "needs_more_info",
            "info_type": "scroll_down",
            "scroll_amount": 450,
            "question": "Select all correct statements",
            "answer": "Content below fold",
            "actions": []
        }
        final_result = {
            "status": "solved",
            "question": "Select all correct statements",
            "answer": "Option C and D",
            "actions": [{"type": "click", "x": 300, "y": 400, "screen_x": 300, "screen_y": 400}],
            "ready_to_advance": True
        }

        with patch("core.assistant_engine.AIClient") as mock_ai_class:
            mock_ai_instance = MagicMock()
            mock_ai_instance.solve_screen.side_effect = [initial_result, final_result]
            mock_ai_class.return_value = mock_ai_instance

            engine._run_solve_pipeline()

            # Verify scrolled down by 450px
            engine.executor.scroll.assert_any_call(-450, 500, 500)
            # Verify scrolled back UP by exact 450px to restore coordinate invariance
            engine.executor.scroll.assert_any_call(450, 500, 500)
            # Verify AI was re-called with extra image
            self.assertEqual(mock_ai_instance.solve_screen.call_count, 2)
            self.assertEqual(engine.last_result["answer"], "Option C and D")

    def test_auto_advance_in_autonomous_mode(self):
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.config.autonomous_mode = True
        engine.config_manager.config.auto_next = False  # autonomous_mode alone must trigger advancing!

        engine.last_result = {
            "ready_to_advance": True,
            "actions": [{"type": "click", "screen_x": 400, "screen_y": 500, "verified": True}],
            "next_button": {"screen_x": 880, "screen_y": 920}
        }
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine.trigger_next_button = MagicMock()
        engine.trigger_solve = MagicMock()

        engine.execute_current_solution()

        engine.trigger_next_button.assert_called_once()
        engine.trigger_solve.assert_called_once()

    def test_check_then_reveal_next_button(self):
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.config.auto_next = True

        engine.last_result = {
            "ready_to_advance": True,
            "actions": [{"type": "click", "screen_x": 300, "screen_y": 400, "verified": True}],
            "check_button": {"screen_x": 750, "screen_y": 900},
            "next_button": None  # Initially null (standard Edgenuity/IXL/DeltaMath behavior)
        }
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine.trigger_check_button = MagicMock()
        engine._discover_and_click_next_button = MagicMock(return_value=True)

        engine.execute_current_solution()

        # Must click Check button first
        engine.trigger_check_button.assert_called_once()
        # Must discover and click the newly revealed Next button
        engine._discover_and_click_next_button.assert_called_once()

    def test_manual_f10_discovers_next_button(self):
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.last_result = {
            "check_button": None,
            "next_button": None
        }
        engine._discover_and_click_next_button = MagicMock(return_value=True)

        engine.trigger_next_question()

        engine._discover_and_click_next_button.assert_called_once()

    def test_reference_modal_multi_tier_escape_recovery(self):
        """
        Tests that when an AI close button fails to dismiss a reference modal,
        the zero-token verifier detects the failure and immediately triggers
        Tier 2 (Escape key) fallback recovery until confirmed dismissed.
        """
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.click = MagicMock()
        engine.executor.key_press = MagicMock()

        baseline_img = MagicMock()
        close_btn = {"screen_x": 750, "screen_y": 120}

        # First verification (after close button): False (modal still open)
        # Second verification (after Escape key): True (modal dismissed)
        engine.capture.capture_screen = MagicMock(return_value=MagicMock())
        engine.verifier.verify_modal_dismissed = MagicMock(side_effect=[
            (False, 18.5),  # Close button failed
            (True, 1.2)     # Escape succeeded
        ])

        success = engine._dismiss_reference_modal_with_verification(
            baseline_img=baseline_img,
            close_btn=close_btn,
            region=None,
            curr_w=1000,
            curr_h=1000,
            offset_x=0,
            offset_y=0
        )

        self.assertTrue(success)
        # Verify close button was attempted first
        engine.executor.click.assert_called_with(750, 120, allow_variance=False)
        # Verify Escape was attempted as Tier 2 recovery
        engine.executor.key_press.assert_called_with("escape")

    def test_reference_modal_top_right_x_recovery(self):
        """
        Tests that when close button and Escape both fail, engine progresses to
        Tier 3 (top-right 'X' candidate) and successfully verifies dismissal.
        """
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.click = MagicMock()
        engine.executor.key_press = MagicMock()

        baseline_img = MagicMock()
        close_btn = {"screen_x": 800, "screen_y": 100}

        # Sequence of verification outcomes:
        # Tier 1 (close_btn) -> False
        # Tier 2 (escape) -> False
        # Tier 3a (top_right_modal_x) -> True
        engine.capture.capture_screen = MagicMock(return_value=MagicMock())
        engine.verifier.verify_modal_dismissed = MagicMock(side_effect=[
            (False, 15.0),
            (False, 14.8),
            (True, 1.1)
        ])

        success = engine._dismiss_reference_modal_with_verification(
            baseline_img=baseline_img,
            close_btn=close_btn,
            region=None,
            curr_w=1000,
            curr_h=1000,
            offset_x=0,
            offset_y=0
        )

        self.assertTrue(success)
        self.assertEqual(engine.executor.click.call_count, 2)
        engine.executor.key_press.assert_called_with("escape")

    def test_action_execution_verification_fields(self):
        """Verifies that execute_action sets verified and verification_reason for all action types."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.executor.drag = MagicMock()
        engine.executor.scroll = MagicMock()
        engine.executor.key_press = MagicMock()
        engine.executor.verifier.verify_drag_completion = MagicMock(return_value=(True, "drag_confirmed"))
        engine.executor.verifier.verify_action_completion = MagicMock(return_value=(True, 2.5))

        # Drag action
        drag_act = {"type": "drag", "from_x": 100, "from_y": 100, "to_x": 300, "to_y": 300}
        engine.executor.execute_action(drag_act)
        self.assertTrue(drag_act.get("verified"))
        self.assertIn("verification_reason", drag_act)
        self.assertEqual(drag_act.get("verification_reason"), "drag_confirmed")

        # Key press action
        key_act = {"type": "key_press", "key": "enter"}
        engine.executor.execute_action(key_act)
        self.assertTrue(key_act.get("verified"))
        self.assertIn("verification_reason", key_act)

        # Scroll action
        scroll_act = {"type": "scroll", "clicks": -4, "x": 400, "y": 400}
        engine.executor.execute_action(scroll_act)
        self.assertTrue(scroll_act.get("verified"))
        self.assertIn("verification_reason", scroll_act)

    def test_navigation_detector_returns_scroll_down(self):
        """Tests that navigation detector correctly parses AI detection of scrolling quizzes."""
        client = AIClient(provider="gemini", api_key="mock_key")
        with patch.object(client, "_call_gemini") as mock_call:
            mock_call.return_value = json.dumps({
                "found": True,
                "advance_action": "scroll_down",
                "scroll_amount": 500,
                "next_button": None,
                "needs_scroll": False
            })

            nav_res = client.detect_navigation_button(
                base64_image="mock_screen_data",
                image_width=1000,
                image_height=1000
            )

            self.assertIsNotNone(nav_res)
            self.assertEqual(nav_res["advance_action"], "scroll_down")
            self.assertEqual(nav_res["type"], "scroll_down")
            self.assertEqual(nav_res["scroll_amount"], 500)

    def test_scrolling_quiz_detection_and_advance(self):
        """Tests that when AI detects scrolling quiz, auto-advance scrolls down rather than looking for a Next button."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.config.autonomous_mode = True

        engine.last_result = {
            "ready_to_advance": True,
            "actions": [{"type": "click", "screen_x": 400, "screen_y": 500, "verified": True}],
            "advance_action": "scroll_down",
            "scroll_amount": 480,
            "next_button": None
        }
        engine.executor.execute_action_sequence = MagicMock(return_value={"all_verified": True})
        engine._advance_by_scrolling_down = MagicMock(return_value=True)
        engine.trigger_solve = MagicMock()

        engine.execute_current_solution()

        engine._advance_by_scrolling_down.assert_called_once_with(scroll_amt=480, override_region=None)
        engine.trigger_solve.assert_called_once()

    def test_advance_by_scrolling_down_with_verification_and_retry(self):
        """Tests that _advance_by_scrolling_down executes scroll, checks zero-token displacement, and retries on no diff."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.last_region = (100, 100, 800, 600)  # center = (500, 400)
        engine.executor.scroll = MagicMock()
        engine.executor.click = MagicMock()

        # Mock screen capture and verifier
        engine.capture.capture_screen = MagicMock(return_value=MagicMock())
        # First verification check: False (no displacement, needs focus click)
        # Second check: True (displacement confirmed)
        engine.verifier.verify_screen_scrolled = MagicMock(side_effect=[
            (False, 0.2),
            (True, 4.5)
        ])

        success = engine._advance_by_scrolling_down(scroll_amt=450)

        self.assertTrue(success)
        # Initial scroll attempt down
        engine.executor.scroll.assert_any_call(-450, 500, 400)
        # Click to focus
        engine.executor.click.assert_called_with(500, 400, allow_variance=False)
        self.assertEqual(engine.executor.scroll.call_count, 2)

    def test_manual_f10_scroll_down_advance(self):
        """Tests that manual F10 advance handles scrolling quizzes properly."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.last_result = {
            "advance_action": "scroll_down",
            "scroll_amount": 520,
            "next_button": None
        }
        engine._advance_by_scrolling_down = MagicMock(return_value=True)

        engine.trigger_next_question()

        engine._advance_by_scrolling_down.assert_called_once_with(scroll_amt=520, override_region=None)


if __name__ == "__main__":
    unittest.main()


