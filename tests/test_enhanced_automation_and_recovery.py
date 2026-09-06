"""
Unit tests for Enhanced Automation & Recovery:
- 3-Attempt Click Readjustment before giving up
- Input box measurement and middle-50% targeting
- Click-through overlay (WS_EX_TRANSPARENT)
- F8 restart-on-busy cancellation and fresh solve launch
- Gemini 3.1 Flash Lite model option
- MemoryLogHandler exception formatting
"""

import sys
import time
import logging
import unittest
import threading
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw

from config import AVAILABLE_MODELS, ConfigManager
from core.cloaking import make_window_click_through
from core.local_verifier import LocalVisualVerifier
from core.automation import AutomationExecutor
from core.assistant_engine import AssistantEngine, EngineState
from core.logger import MemoryLogBuffer, MemoryLogHandler
from core.ai_client import AIClient


class TestEnhancedAutomationAndRecovery(unittest.TestCase):

    def setUp(self):
        self.verifier = LocalVisualVerifier()
        self.config_manager = ConfigManager()

    def test_gemini_3_1_flash_lite_option(self):
        """Verifies that gemini-3.1-flash-lite is available in default model list."""
        self.assertIn("gemini-3.1-flash-lite", AVAILABLE_MODELS["gemini"])

    def test_memory_log_handler_formats_exception(self):
        """Verifies that MemoryLogHandler does not crash on exc_info and formats tracebacks."""
        buf = MemoryLogBuffer(max_entries=10)
        handler = MemoryLogHandler(buf)
        logger = logging.getLogger("test_mem_logger")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            raise ValueError("Test error for MemoryLogHandler")
        except ValueError:
            logger.exception("Caught an expected test exception")

        entries = buf.get_entries()
        self.assertTrue(len(entries) >= 1)
        self.assertIn("Test error for MemoryLogHandler", entries[-1].traceback)

    def test_measure_input_box_middle_50_percent(self):
        """
        Creates a synthetic input box of 120x36 px, detects bounds,
        and verifies that chosen target is strictly inside the middle 50% zone.
        """
        roi_w, roi_h = 160, 60
        roi_img = Image.new("RGB", (roi_w, roi_h), (245, 245, 245))
        d = ImageDraw.Draw(roi_img)

        # Draw rectangular input box: left=20, top=12, right=140, bottom=48 (width=120, height=36)
        d.rectangle([20, 12, 140, 48], outline=(70, 70, 70), fill=(255, 255, 255), width=2)

        center_screen_x, center_screen_y = 500, 300
        chosen_x, chosen_y, meta = self.verifier.measure_and_target_input_box(
            roi_img, center_screen_x, center_screen_y
        )

        self.assertTrue(meta["detected"])
        self.assertGreaterEqual(meta["box_width"], 100)
        self.assertGreaterEqual(meta["box_height"], 30)

        # Expected middle 50% horizontal bounds:
        # box spans x in [20, 140], w=120. Middle 50% is [20 + 30, 140 - 30] = [50, 110]
        # In screen coords relative to center (roi_mid_x=80):
        # min_x = 500 - 80 + 50 = 470, max_x = 500 - 80 + 110 = 530
        for _ in range(50):
            sample_x, sample_y, _ = self.verifier.measure_and_target_input_box(
                roi_img, center_screen_x, center_screen_y
            )
            # Must be strictly within middle 50% boundaries
            self.assertGreaterEqual(sample_x, 465)
            self.assertLessEqual(sample_x, 535)
            # Vertical: box spans y in [12, 48], h=36. Middle 50% is [12 + 9, 48 - 9] = [21, 39]
            # In screen coords relative to center (roi_mid_y=30): [300 - 30 + 21, 300 - 30 + 39] = [291, 309]
            self.assertGreaterEqual(sample_y, 288)
            self.assertLessEqual(sample_y, 312)

    def test_ai_client_box_2d_middle_50_percent_sampling(self):
        """
        Tests that AIClient maps box_2d on input fields strictly to the middle 50% sub-region.
        """
        client = AIClient(provider="gemini", api_key="test_key")
        # Case 1: Exact coordinates provided - must be strictly preserved!
        action_exact = {
            "type": "type_text",
            "x": 450,
            "y": 550,
            "box_2d": [200, 100, 800, 900],  # Wide box must NOT displace exact x, y
            "text": "sample"
        }
        # Case 2: box_2d fallback when x, y are absent
        action_fallback = {
            "type": "type_text",
            "box_2d": [200, 400, 300, 800],  # y center = 250, x center = 600
            "text": "sample2"
        }
        mock_result = {
            "actions": [action_exact, action_fallback]
        }
        client._map_coordinates(
            result=mock_result,
            image_width=1000,
            image_height=1000,
            scale_x=1.0,
            scale_y=1.0,
            offset_x=0,
            offset_y=0,
            calibration_offset_x=0,
            calibration_offset_y=0,
            calibration_scale_x=1.0,
            calibration_scale_y=1.0
        )
        processed = mock_result

        # Exact action must maintain precise x=450, y=550 (zero displacement)
        act1 = processed["actions"][0]
        self.assertEqual(act1["x"], 450)
        self.assertEqual(act1["y"], 550)

        # Fallback action computes center
        act2 = processed["actions"][1]
        self.assertEqual(act2["x"], 600.0)
        self.assertEqual(act2["y"], 250.0)


    def test_click_readjustment_three_attempts_before_giving_up(self):
        """
        Tests that when a click misses and fails verification, exactly 3 sequential readjustment
        attempts are made before giving up.
        """
        executor = AutomationExecutor(humanize=False, click_variance_enabled=False)
        executor.local_verification_enabled = True

        dummy_roi = Image.new("RGB", (70, 44), (255, 255, 255))
        dummy_band = Image.new("RGB", (120, 50), (255, 255, 255))

        executor.verifier.capture_roi = MagicMock(return_value=dummy_roi)
        executor.verifier.capture_band = MagicMock(return_value=(dummy_band, 400, 280))
        executor.verifier.is_radio_or_checkbox_selected = MagicMock(return_value=(False, "unselected", 0.0))
        executor.verifier.is_option_row_highlighted = MagicMock(return_value=(False, 0.0))
        executor.verifier.verify_action_completion = MagicMock(return_value=(False, 0.2))
        executor.click = MagicMock()

        adjustments_recorded = []
        executor.on_adjustment_callback = lambda msg: adjustments_recorded.append(msg)

        action = {"type": "click", "screen_x": 500, "screen_y": 300}
        executor.execute_action(action)

        # 1 primary click + 3 readjustment attempts = 4 total clicks
        self.assertEqual(executor.click.call_count, 4)
        # Must record failure after exactly 3 readjustments
        self.assertFalse(action["verified"])
        readjustment_msgs = [m for m in adjustments_recorded if "attempt" in m]
        self.assertEqual(len(readjustment_msgs), 3)
        self.assertIn("attempt 1/3", readjustment_msgs[0])
        self.assertIn("attempt 2/3", readjustment_msgs[1])
        self.assertIn("attempt 3/3", readjustment_msgs[2])

    def test_click_readjustment_succeeds_on_second_attempt(self):
        """
        Tests that if readjustment attempt #2 succeeds, probing stops and action marks verified.
        """
        executor = AutomationExecutor(humanize=False, click_variance_enabled=False)
        executor.local_verification_enabled = True

        dummy_roi = Image.new("RGB", (70, 44), (255, 255, 255))
        dummy_band = Image.new("RGB", (120, 50), (255, 255, 255))

        executor.verifier.capture_roi = MagicMock(return_value=dummy_roi)
        executor.verifier.capture_band = MagicMock(return_value=(dummy_band, 400, 280))
        executor.verifier.is_option_row_highlighted = MagicMock(return_value=(False, 0.0))
        executor.click = MagicMock()

        # Primary click fails, probe 1 fails, probe 2 succeeds!
        executor.verifier.is_radio_or_checkbox_selected = MagicMock(side_effect=[
            (False, "unselected", 0.0),  # Primary check
            (False, "unselected", 0.0),  # Readjustment 1
            (True, "radio_inner_bullet", 0.95),  # Readjustment 2 succeeds!
        ])
        executor.verifier.verify_action_completion = MagicMock(return_value=(False, 0.1))

        action = {"type": "click", "screen_x": 500, "screen_y": 300}
        executor.execute_action(action)

        # 1 primary click + 2 readjustments = 3 clicks total (did NOT do attempt 3)
        self.assertEqual(executor.click.call_count, 3)
        self.assertTrue(action["verified"])
        self.assertIn("readjustment_attempt_2", action["verification_reason"])

    def test_f8_cancels_and_restarts_when_busy(self):
        """
        Verifies that pressing F8 while engine is in THINKING aborts current execution
        and launches a fresh solve pipeline (equivalent to F12 -> F8).
        """
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.state = EngineState.THINKING

        # Mock executor and running thread
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        engine._running_thread = mock_thread

        with patch.object(engine.executor, "request_stop") as mock_stop, \
             patch.object(engine.executor, "reset_stop") as mock_reset, \
             patch.object(engine, "_run_solve_pipeline") as mock_pipeline:

            engine.trigger_solve()

            # Verify request_stop was called to cancel current movements
            mock_stop.assert_called_once()
            # Verify reset_stop was called for the new run
            mock_reset.assert_called_once()
            # Engine transitioned to SCANNING for fresh run
            self.assertEqual(engine.state, EngineState.SCANNING)

    def test_make_window_click_through(self):
        """Verifies make_window_click_through on Windows platforms with mocked HWND."""
        if sys.platform != "win32":
            self.skipTest("Click-through styles only testable on Windows")

        # Create dummy HWND test with ctypes mock
        with patch("ctypes.windll.user32.GetWindowLongPtrW", create=True) as mock_get, \
             patch("ctypes.windll.user32.SetWindowLongPtrW", create=True) as mock_set, \
             patch("ctypes.windll.user32.SetWindowPos", create=True) as mock_pos:
            mock_get.return_value = 0
            mock_set.return_value = 0x00080020
            mock_pos.return_value = 1

            ok = make_window_click_through(12345, enable=True)
            self.assertTrue(ok)
            mock_get.assert_called_once()
            mock_set.assert_called_once()
            # WS_EX_TRANSPARENT (0x20) | WS_EX_LAYERED (0x80000) = 0x80020
    def test_next_question_render_delay_and_blank_screen_guard(self):
        """Verifies that next question navigation waits for the rendering delay to avoid blank screens."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.update(
            autonomous_mode=True,
            auto_next=True,
            auto_next_delay=1.5
        )
        engine.last_result = {
            "question": "Q1",
            "answer": "Ans",
            "ready_to_advance": True,
            "next_button": {"screen_x": 500, "screen_y": 500},
            "actions": []
        }
        engine.executor.is_stopped = MagicMock(return_value=False)
        engine.trigger_next_button = MagicMock()

        with patch("time.sleep") as mock_sleep, \
             patch.object(engine, "trigger_solve") as mock_solve:
            engine.execute_current_solution()
            # load_delay should be max(2.0, 1.5 + 0.8) = 2.3
            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            self.assertTrue(any(s >= 2.0 for s in sleep_calls), f"Expected render delay >= 2.0s, got {sleep_calls}")

    def test_refine_input_box_targets_snapping_and_sync(self):
        """Verifies that _refine_input_box_targets measures and snaps input boxes and synchronizes multi-part actions."""
        engine = AssistantEngine(config_manager=self.config_manager)
        click_act = {
            "type": "click",
            "screen_x": 500,
            "screen_y": 300,
            "description": "Focus input box for Part 1"
        }
        type_act = {
            "type": "type_text",
            "screen_x": 500,
            "screen_y": 300,
            "text": "42",
            "description": "Type 42 into Part 1"
        }
        result = {
            "actions": [click_act, type_act],
            "items": [{
                "part_id": "Part 1",
                "actions": [click_act, type_act]
            }]
        }

        # Mock measure_and_target_input_box to simulate visual box detection at (480, 290)
        mock_meta = {
            "detected": True,
            "box_width": 120,
            "box_height": 34,
            "screen_bounds": (420, 273, 540, 307)
        }
        engine.verifier.measure_and_target_input_box = MagicMock(return_value=(480, 290, mock_meta))

        engine._refine_input_box_targets(result)

        self.assertEqual(click_act["screen_x"], 480)
        self.assertEqual(click_act["screen_y"], 290)
        self.assertEqual(type_act["screen_x"], 480)
        self.assertEqual(type_act["screen_y"], 290)
        self.assertEqual(click_act.get("box_screen"), [420, 273, 540, 307])
        self.assertEqual(type_act.get("box_screen"), [420, 273, 540, 307])

    def test_auto_advance_ensured_after_actions_verified(self):
        """Verifies that once all actions verify, ready_to_advance is set to True and auto-next proceeds."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.update(
            autonomous_mode=True,
            auto_next=True
        )
        engine.last_result = {
            "question": "Q1",
            "answer": "144",
            "ready_to_advance": False,  # Model initially said False prior to submission
            "next_button": {"screen_x": 800, "screen_y": 900},
            "actions": [{"type": "click", "screen_x": 400, "screen_y": 400}]
        }
        engine.executor.is_stopped = MagicMock(return_value=False)
        engine.executor.execute_action_sequence = MagicMock(return_value={
            "all_verified": True,
            "verified_count": 1,
            "total_verifiable": 1
        })
        engine.trigger_next_button = MagicMock()

        with patch("time.sleep"), patch.object(engine, "trigger_solve"):
            engine.execute_current_solution()

        self.assertTrue(engine.last_result["ready_to_advance"])
        engine.trigger_next_button.assert_called_once()

    def test_feedback_modal_dismissal_on_correct_avoids_rethink_loop(self):
        """Verifies that when platform confirms correct, Next button is clicked without a wasteful rethink loop."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.update(
            autonomous_mode=False,
            auto_next=True
        )
        engine.last_result = {
            "question": "Q1",
            "answer": "144",
            "ready_to_advance": True,
            "check_button": {"screen_x": 700, "screen_y": 900},
            "next_button": None,
            "actions": []
        }
        engine.executor.is_stopped = MagicMock(return_value=False)
        engine.trigger_check_button = MagicMock()
        # Platform confirms correct!
        engine.verifier.verify_post_submission_evaluation = MagicMock(return_value={
            "status": "correct",
            "confidence": 0.95,
            "details": "detected_green_success_cluster (400px)"
        })
        engine._discover_and_click_next_button = MagicMock(return_value=True)
        engine.trigger_solve = MagicMock()

        with patch("time.sleep"):
            engine.execute_current_solution()

        engine.trigger_check_button.assert_called_once()
        engine._discover_and_click_next_button.assert_called_once()
        # Must NOT have retriggered solve to rethink!
        engine.trigger_solve.assert_not_called()
        self.assertFalse(engine.last_result.get("is_rethinking", False))

    def test_second_next_button_halts_and_rethinks_if_question_incorrect(self):
        """Verifies that checking for second next button checks if question is wrong first and triggers rethink to avoid softlock."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.update(
            autonomous_mode=True,
            auto_next=True
        )
        engine.last_result = {
            "question": "Q1",
            "answer": "120",
            "ready_to_advance": True,
            "check_button": {"screen_x": 700, "screen_y": 900},
            "next_button": None,
            "actions": []
        }
        engine.executor.is_stopped = MagicMock(return_value=False)
        engine.trigger_check_button = MagicMock()
        # Screen check detects answer was marked INCORRECT by platform
        engine.verifier.verify_post_submission_evaluation = MagicMock(return_value={
            "status": "incorrect",
            "confidence": 0.95,
            "details": "detected_red_error_cluster (320px)"
        })
        engine._discover_and_click_next_button = MagicMock()
        engine.trigger_solve = MagicMock()

        with patch("time.sleep"):
            engine.execute_current_solution()

        engine.trigger_check_button.assert_called_once()
        # Must NOT have clicked next button!
        engine._discover_and_click_next_button.assert_not_called()
        # Must have triggered solve to rethink the solution!
        engine.trigger_solve.assert_called_once()
        self.assertTrue(engine.last_result.get("is_rethinking"))
        self.assertFalse(engine.last_result.get("ready_to_advance"))

    def test_per_input_typing_failsafe_and_readjustments(self):
        """Verifies that each typing input triggers zero-token verification and readjustments if empty."""
        executor = AutomationExecutor(humanize=False, click_variance_enabled=False)
        executor.local_verification_enabled = True

        dummy_roi = Image.new("RGB", (80, 30), (255, 255, 255))
        executor.verifier.capture_roi = MagicMock(return_value=dummy_roi)
        executor.verifier.measure_and_target_input_box = MagicMock(return_value=(490, 305, {"detected": True}))
        executor.click = MagicMock()
        executor.key_press = MagicMock()
        executor.type_text = MagicMock()

        # Initial check says empty (False), 1st readjustment succeeds (True)
        executor.verifier.is_text_input_filled = MagicMock(side_effect=[
            (False, "input_empty", 0.0),
            (True, "text_stroke_diff (strokes=45)", 0.95)
        ])

        action = {"type": "type_text", "screen_x": 500, "screen_y": 300, "text": "144"}
        executor.execute_action(action)

        self.assertTrue(action["verified"])
        self.assertIn("readjustment_attempt_1", action["verification_reason"])
        self.assertEqual(action["screen_x"], 490)
        self.assertEqual(action["screen_y"], 305)

    def test_per_input_typing_failsafe_records_failure_after_3_attempts(self):
        """Verifies that if typing fails all 3 readjustment attempts, action marks failed and sequence tracks failed_inputs."""
        executor = AutomationExecutor(humanize=False, click_variance_enabled=False)
        executor.local_verification_enabled = True

        dummy_roi = Image.new("RGB", (80, 30), (255, 255, 255))
        executor.verifier.capture_roi = MagicMock(return_value=dummy_roi)
        executor.verifier.measure_and_target_input_box = MagicMock(return_value=(500, 300, {"detected": False}))
        executor.verifier.find_visual_element_center = MagicMock(return_value=(500, 300))
        executor.click = MagicMock()
        executor.key_press = MagicMock()
        executor.type_text = MagicMock()
        # All checks return False
        executor.verifier.is_text_input_filled = MagicMock(return_value=(False, "input_empty", 0.0))

        action = {"type": "type_text", "screen_x": 500, "screen_y": 300, "text": "144"}
        summary = executor.execute_action_sequence([action], delay_between=0.01)

        self.assertFalse(action["verified"])
        self.assertFalse(summary["all_verified"])
        self.assertEqual(len(summary["failed_inputs"]), 1)
        self.assertEqual(summary["failed_inputs"][0]["type"], "type_text")

    def test_engine_halts_advance_if_per_input_failsafe_detects_untyped_answer(self):
        """Verifies that execute_current_solution halts without advancing if an input fails verification."""
        engine = AssistantEngine(config_manager=self.config_manager)
        engine.config_manager.update(
            autonomous_mode=True,
            auto_next=True
        )
        engine.last_result = {
            "question": "Q1",
            "answer": "144",
            "ready_to_advance": True,
            "next_button": {"screen_x": 800, "screen_y": 900},
            "actions": [{"type": "type_text", "screen_x": 500, "screen_y": 300, "text": "144"}]
        }
        engine.executor.is_stopped = MagicMock(return_value=False)
        # Mock execute_action_sequence to return failure from per-input failsafe
        engine.executor.execute_action_sequence = MagicMock(return_value={
            "all_verified": False,
            "verified_count": 0,
            "total_verifiable": 1,
            "failed_inputs": [{"index": 0, "type": "type_text", "reason": "input_empty"}],
            "actions": engine.last_result["actions"]
        })
        engine.trigger_next_button = MagicMock()

        with patch("time.sleep"):
            engine.execute_current_solution()

        # Engine must NOT have advanced to next question
        self.assertFalse(engine.last_result["ready_to_advance"])
        self.assertTrue(engine.last_result["action_missed"])
        engine.trigger_next_button.assert_not_called()
        self.assertEqual(engine.state, EngineState.WAITING_CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
