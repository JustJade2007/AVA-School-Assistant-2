"""
Automated unit and integration tests for AVA School Assistant 2.
"""

import unittest
import os
import tempfile
import json
from config import AppConfig, ConfigManager
from core.cloaking import is_anti_capture_supported
from core.capture import ScreenCapture
from core.prompt import get_vision_system_prompt
from core.ai_client import AIClient
from core.automation import AutomationExecutor, EmergencyStopException
from core.hotkeys import normalize_hotkey_str


class TestAVACore(unittest.TestCase):

    def test_config_defaults_and_serialization(self):
        cfg = AppConfig()
        self.assertEqual(cfg.ai_provider, "gemini")
        self.assertIn("F8", cfg.hotkeys.values())
        self.assertEqual(cfg.hotkeys["toggle_overlay"], "F6")
        self.assertEqual(cfg.hotkeys["close_app"], "Ctrl+Shift+Q")
        self.assertEqual(cfg.max_capture_dimension, 1920)
        self.assertEqual(cfg.calibration_offset_x, 0)
        self.assertEqual(cfg.calibration_offset_y, 0)
        self.assertEqual(cfg.coordinate_mode, "normalized_1000")

        d = cfg.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["model_name"], "gemini-3.6-flash")
        self.assertEqual(d["max_capture_dimension"], 1920)

        restored = AppConfig.from_dict(d)
        self.assertEqual(restored.model_name, "gemini-3.6-flash")
        self.assertEqual(restored.hotkeys["toggle_overlay"], "F6")
        self.assertEqual(restored.hotkeys["close_app"], "Ctrl+Shift+Q")
        self.assertEqual(restored.max_capture_dimension, 1920)
        self.assertEqual(restored.calibration_offset_x, 0)

    def test_hotkey_normalization(self):
        self.assertEqual(normalize_hotkey_str("F8"), "<f8>")
        self.assertEqual(normalize_hotkey_str("F12"), "<f12>")
        self.assertEqual(normalize_hotkey_str("F6"), "<f6>")
        self.assertEqual(normalize_hotkey_str("Ctrl+Shift+Q"), "<ctrl>+<shift>+q")
        self.assertEqual(normalize_hotkey_str("ctrl+shift+s"), "<ctrl>+<shift>+s")
        self.assertEqual(normalize_hotkey_str("alt+F9"), "<alt>+<f9>")

    def test_anti_capture_support(self):
        # On Windows 10/11, SetWindowDisplayAffinity should be supported
        supported = is_anti_capture_supported()
        self.assertTrue(supported, "SetWindowDisplayAffinity should be supported on Windows")

    def test_screen_capture_and_dimensions(self):
        sct = ScreenCapture()
        bounds = sct.get_screen_bounds(1)
        self.assertGreater(bounds["width"], 100)
        self.assertGreater(bounds["height"], 100)

        # In headless test environments or locked screens, BitBlt might be restricted
        try:
            img = sct.capture_screen(region=(0, 0, 100, 100))
            self.assertEqual(img.size, (100, 100))
            b64, w, h, sx, sy, ox, oy = sct.capture_and_encode(region=(0, 0, 100, 100))
            self.assertGreater(len(b64), 100)
            self.assertEqual(w, 100)
            self.assertEqual(h, 100)
        except RuntimeError as e:
            # Verified that the clear RuntimeError is raised when desktop session is restricted
            self.assertIn("Unable to capture screen", str(e))

    def test_prompt_generation(self):
        prompt = get_vision_system_prompt(1920, 1080)
        self.assertIn("1920", prompt)
        self.assertIn("1080", prompt)
        self.assertIn("actions", prompt)
        self.assertIn("check_button", prompt)
        self.assertIn("next_button", prompt)

    def test_ai_client_json_extraction_and_mapping(self):
        client = AIClient()
        sample_json_text = """
        ```json
        {
          "question": "What is 12 x 12?",
          "reasoning": "12 multiplied by 12 equals 144.",
          "answer": "144",
          "confidence": 0.99,
          "actions": [
            {
              "type": "click",
              "x": 200,
              "y": 300,
              "description": "Click Option C (144)"
            }
          ],
          "check_button": {
            "x": 400,
            "y": 500,
            "description": "Check Answer"
          },
          "next_button": {
            "x": 500,
            "y": 600,
            "description": "Next Button"
          }
        }
        ```
        """
        extracted = client._extract_json(sample_json_text)
        self.assertEqual(extracted["answer"], "144")
        self.assertEqual(len(extracted["actions"]), 1)

        # Test coordinate mapping: scale 2.0x and offset +50, +100
        client._map_coordinates(extracted, scale_x=2.0, scale_y=2.0, offset_x=50, offset_y=100)
        action = extracted["actions"][0]
        self.assertEqual(action["screen_x"], 450)  # 200 * 2.0 + 50
        self.assertEqual(action["screen_y"], 700)  # 300 * 2.0 + 100

        check_btn = extracted["check_button"]
        self.assertEqual(check_btn["screen_x"], 850) # 400 * 2.0 + 50
        self.assertEqual(check_btn["screen_y"], 1100) # 500 * 2.0 + 100

        next_btn = extracted["next_button"]
        self.assertEqual(next_btn["screen_x"], 1050) # 500 * 2.0 + 50
        self.assertEqual(next_btn["screen_y"], 1300) # 600 * 2.0 + 100

    def test_ai_client_multi_part_answer_synthesis(self):
        """Verifies that top-level answer, question, and aliases are synthesized from items."""
        client = AIClient()
        # 1. Single-part item without top-level answer
        raw_result = {
            "summary": "Photosynthesis question detected",
            "items": [
                {
                    "part_id": "Part 1",
                    "question_text": "What process converts light to chemical energy?",
                    "correct_answer": "Photosynthesis",
                    "reasoning": "Photosynthesis uses chloroplasts to produce glucose.",
                    "actions": [{"type": "click", "x": 300, "y": 400}]
                }
            ]
        }
        client._map_coordinates(raw_result, scale_x=1.0, scale_y=1.0, offset_x=0, offset_y=0)
        self.assertEqual(raw_result["answer"], "Photosynthesis")
        self.assertEqual(raw_result["question"], "What process converts light to chemical energy?")
        self.assertEqual(raw_result["items"][0]["proposed_answer"], "Photosynthesis")
        self.assertEqual(raw_result["items"][0]["question"], "What process converts light to chemical energy?")

        # 2. Multi-part items without top-level answer
        multi_result = {
            "summary": "Two-part algebra problem",
            "items": [
                {
                    "part_id": "Part A",
                    "question_text": "Find x if 2x = 10",
                    "correct_answer": "5",
                    "actions": []
                },
                {
                    "part_id": "Part B",
                    "question_text": "Find y if y + 3 = 10",
                    "proposed_answer": "7",
                    "actions": []
                }
            ]
        }
        client._map_coordinates(multi_result, scale_x=1.0, scale_y=1.0, offset_x=0, offset_y=0)
        self.assertIn("Part A: 5", multi_result["answer"])
        self.assertIn("Part B: 7", multi_result["answer"])
        self.assertEqual(multi_result["items"][0]["answer"], "5")
        self.assertEqual(multi_result["items"][1]["answer"], "7")

    def test_automation_emergency_stop(self):
        executor = AutomationExecutor()
        self.assertFalse(executor.is_stopped())

        executor.request_stop()
        self.assertTrue(executor.is_stopped())

        with self.assertRaises(EmergencyStopException):
            executor._check_stop()

        executor.reset_stop()
        self.assertFalse(executor.is_stopped())

    def test_app_hotkey_registration_includes_new_keybinds(self):
        from unittest.mock import MagicMock, patch
        from ui.app import AVASchoolAssistantApp
        with patch("customtkinter.CTk"), patch("customtkinter.set_appearance_mode"), patch("customtkinter.set_default_color_theme"), patch("ui.app.HUDOverlay"):
            app = AVASchoolAssistantApp()
            registered = app.hotkey_manager.callbacks
            self.assertIn("toggle_overlay", registered)
            self.assertIn("close_app", registered)
            self.assertEqual(registered["toggle_overlay"][0], "F6")
            self.assertEqual(registered["close_app"][0], "Ctrl+Shift+Q")
            app.hotkey_manager.stop()

    def test_hud_overlay_toggle_visibility(self):
        from unittest.mock import MagicMock, patch
        from ui.hud_overlay import HUDOverlay
        with patch.object(HUDOverlay, "__init__", lambda self, *args, **kwargs: None):
            hud = HUDOverlay(None, None)
            hud.is_hidden = False
            hud.withdraw = MagicMock()
            hud.deiconify = MagicMock()
            hud.lift = MagicMock()
            hud.attributes = MagicMock()
            hud.apply_cloak = MagicMock()
            hud.visualizer = MagicMock()

            # When viewable, toggling should hide
            hud.winfo_viewable = MagicMock(return_value=True)
            res = hud.toggle_visibility()
            self.assertFalse(res)
            self.assertTrue(hud.is_hidden)
            hud.withdraw.assert_called_once()
            hud.visualizer.clear.assert_called_once()

            # When hidden / not viewable, toggling should show
            hud.winfo_viewable = MagicMock(return_value=False)
            res2 = hud.toggle_visibility()
            self.assertTrue(res2)
            self.assertFalse(hud.is_hidden)
            hud.deiconify.assert_called_once()
            hud.lift.assert_called_once()
            hud.apply_cloak.assert_called_once()

    def test_app_quit_execution(self):
        from unittest.mock import MagicMock, patch
        from ui.app import AVASchoolAssistantApp
        with patch("customtkinter.CTk"), patch("customtkinter.set_appearance_mode"), patch("customtkinter.set_default_color_theme"), patch("ui.app.HUDOverlay"):
            app = AVASchoolAssistantApp()
            app.hotkey_manager.stop = MagicMock()
            app.engine.emergency_stop = MagicMock()
            app.root.quit = MagicMock()
            app.root.destroy = MagicMock()

            app._do_quit_app()

            app.hotkey_manager.stop.assert_called_once()
            app.engine.emergency_stop.assert_called_once()
            app.root.quit.assert_called_once()
            app.root.destroy.assert_called_once()

    def test_normalized_coordinate_mapping_and_calibration(self):
        client = AIClient(api_key="test-key")
        # Scenario: 2880x1800 screen scaled down to 1920x1200 for Gemini
        # Model returns Option B at normalized coordinates x=312, y=441
        data = {
            "actions": [
                {"type": "click", "x": 312, "y": 441, "description": "Option B"},
                {"type": "drag", "from_x": 100, "from_y": 200, "to_x": 900, "to_y": 800}
            ],
            "next_button": {"x": 880, "y": 920}
        }

        # 1. Base mapping without calibration offsets
        client._map_coordinates(
            data,
            scale_x=1.5,
            scale_y=1.5,
            offset_x=0,
            offset_y=0,
            image_width=1920,
            image_height=1200,
            calibration_offset_x=0,
            calibration_offset_y=0,
            coordinate_mode="normalized_1000"
        )
        action = data["actions"][0]
        # target_w = 1920 * 1.5 = 2880, target_h = 1200 * 1.5 = 1800
        # screen_x = int(312 / 1000 * 2880) = 898
        # screen_y = int(441 / 1000 * 1800) = 793
        self.assertEqual(action["screen_x"], 898)
        self.assertEqual(action["screen_y"], 793)

        drag_action = data["actions"][1]
        self.assertEqual(drag_action["screen_from_x"], 288)
        self.assertEqual(drag_action["screen_from_y"], 360)
        self.assertEqual(drag_action["screen_to_x"], 2592)
        self.assertEqual(drag_action["screen_to_y"], 1440)

        next_btn = data["next_button"]
        self.assertEqual(next_btn["screen_x"], 2534)
        self.assertEqual(next_btn["screen_y"], 1656)

        # 2. Mapping with manual calibration offsets (+15 px X, -10 px Y)
        client._map_coordinates(
            data,
            scale_x=1.5,
            scale_y=1.5,
            offset_x=0,
            offset_y=0,
            image_width=1920,
            image_height=1200,
            calibration_offset_x=15,
            calibration_offset_y=-10,
            coordinate_mode="normalized_1000"
        )
        self.assertEqual(data["actions"][0]["screen_x"], 898 + 15)
        self.assertEqual(data["actions"][0]["screen_y"], 793 - 10)

        # 3. Test box_2d parsing
        box_data = {
            "actions": [
                {"type": "click", "box_2d": [400, 300, 482, 324], "description": "Box Option"}
            ]
        }
        client._map_coordinates(
            box_data,
            scale_x=1.0,
            scale_y=1.0,
            offset_x=0,
            offset_y=0,
            image_width=1000,
            image_height=1000,
            coordinate_mode="normalized_1000"
        )
        # center_x = (300 + 324)/2 = 312, center_y = (400 + 482)/2 = 441
        self.assertEqual(box_data["actions"][0]["screen_x"], 312)
        self.assertEqual(box_data["actions"][0]["screen_y"], 441)

    def test_multipart_verification_and_mapping(self):
        client = AIClient(api_key="test-key")
        data = {
            "question": "Multi-Part Math Test",
            "ready_to_advance": False,
            "items": [
                {
                    "part_id": "1",
                    "label": "Part A",
                    "question": "What is 5 + 5?",
                    "current_state": "correct",
                    "proposed_answer": "10",
                    "needs_action": False,
                    "actions": [
                        {"type": "click", "x": 100, "y": 200, "description": "Option 10"}
                    ]
                },
                {
                    "part_id": "2",
                    "label": "Part B",
                    "question": "What is 10 x 10?",
                    "current_state": "wrong",
                    "proposed_answer": "100",
                    "needs_action": True,
                    "actions": [
                        {"type": "type_text", "x": 300, "y": 400, "text": "100", "clear_first": True, "description": "Type 100"}
                    ]
                }
            ],
            "next_button": {"x": 900, "y": 950}
        }

        client._map_coordinates(
            data,
            scale_x=1.0,
            scale_y=1.0,
            offset_x=0,
            offset_y=0,
            image_width=1000,
            image_height=1000,
            coordinate_mode="normalized_1000"
        )

        # items[0] should be mapped but NOT in top-level actions because needs_action is False
        # items[1] should be mapped and collected into top-level actions
        self.assertEqual(len(data["actions"]), 1)
        self.assertEqual(data["actions"][0]["text"], "100")
        self.assertTrue(data["actions"][0]["clear_first"])
        self.assertEqual(data["actions"][0]["screen_x"], 300)
        self.assertEqual(data["actions"][0]["screen_y"], 400)

        # Check that items[0] action coordinates were also mapped
        self.assertEqual(data["items"][0]["actions"][0]["screen_x"], 100)
        self.assertEqual(data["items"][0]["actions"][0]["screen_y"], 200)

    def test_auto_next_safety_guard(self):
        from unittest.mock import MagicMock, patch
        from core.assistant_engine import AssistantEngine
        from config import ConfigManager

        cm = ConfigManager()
        cm.config.auto_next = True
        cm.config.auto_next_delay = 0.0
        engine = AssistantEngine(config_manager=cm)
        engine.trigger_next_button = MagicMock()
        engine.trigger_check_button = MagicMock()
        engine.executor.execute_action_sequence = MagicMock()

        # 1. When ready_to_advance is False, neither button should be called
        engine.last_result = {
            "actions": [{"type": "click", "x": 100, "y": 100}],
            "check_button": {"x": 400, "y": 400},
            "next_button": {"x": 500, "y": 500},
            "ready_to_advance": False
        }
        engine.execute_current_solution()
        engine.trigger_check_button.assert_not_called()
        engine.trigger_next_button.assert_not_called()

        # 2. When ready_to_advance is True and both are present:
        # trigger_check_button should be called first, then trigger_next_button
        engine.last_result = {
            "actions": [{"type": "click", "x": 100, "y": 100}],
            "check_button": {"x": 400, "y": 400},
            "next_button": {"x": 500, "y": 500},
            "ready_to_advance": True
        }
        engine.execute_current_solution()
        engine.trigger_check_button.assert_called_once()
        engine.trigger_next_button.assert_called_once()

    def test_check_answer_prior_to_next_on_manual_trigger(self):
        from unittest.mock import MagicMock
        from core.assistant_engine import AssistantEngine
        from config import ConfigManager

        cm = ConfigManager()
        engine = AssistantEngine(config_manager=cm)
        engine.trigger_check_button = MagicMock()
        engine.trigger_next_button = MagicMock()

        # Case A: Only check_button is on screen (e.g. before next is revealed)
        engine.last_result = {
            "check_button": {"screen_x": 400, "screen_y": 400},
            "next_button": None
        }
        engine.trigger_next_question()
        engine.trigger_check_button.assert_called_once()
        engine.trigger_next_button.assert_not_called()

        # Case B: Both check_button and next_button are on screen
        engine.trigger_check_button.reset_mock()
        engine.trigger_next_button.reset_mock()
        engine.last_result = {
            "check_button": {"screen_x": 400, "screen_y": 400},
            "next_button": {"screen_x": 500, "screen_y": 500}
        }
        engine.trigger_next_question()
        engine.trigger_check_button.assert_called_once()
        engine.trigger_next_button.assert_called_once()

    def test_snip_solve_hotkey_registered(self):
        from unittest.mock import MagicMock, patch
        from ui.app import AVASchoolAssistantApp

        cfg = AppConfig()
        self.assertEqual(cfg.hotkeys["snip_solve"], "F4")

        with patch("customtkinter.CTk"), patch("customtkinter.set_appearance_mode"), patch("customtkinter.set_default_color_theme"), patch("ui.app.HUDOverlay"):
            app = AVASchoolAssistantApp()
            self.assertIn("snip_solve", app.hotkey_manager.callbacks)
            self.assertEqual(app.hotkey_manager.callbacks["snip_solve"][0], "F4")
            app.hotkey_manager.stop()

    def test_local_visual_verifier(self):
        from PIL import Image, ImageDraw
        from core.local_verifier import LocalVisualVerifier

        verifier = LocalVisualVerifier()

        # 1. Action completion verification
        img1 = Image.new("RGB", (70, 44), (255, 255, 255))
        img2 = Image.new("RGB", (70, 44), (255, 255, 255))
        # Identical images should NOT be confirmed (no visual response)
        confirmed, score = verifier.verify_action_completion(img1, img2, action_type="click")
        self.assertFalse(confirmed)
        self.assertEqual(score, 0.0)

        # Distinct image (e.g. radio button filled with dark dot)
        draw = ImageDraw.Draw(img2)
        draw.ellipse([30, 18, 40, 26], fill=(30, 60, 180))
        confirmed, score = verifier.verify_action_completion(img1, img2, action_type="click")
        self.assertTrue(confirmed)
        self.assertGreater(score, 1.0)

        # 2. Visual element center snapping
        roi_img = Image.new("RGB", (70, 44), (240, 240, 240))
        d_roi = ImageDraw.Draw(roi_img)
        # Draw a box shifted slightly right of center (+6px, +4px)
        d_roi.rectangle([35 + 6, 16 + 4, 47 + 6, 28 + 4], outline=(20, 20, 20), width=2)
        snapped_x, snapped_y = verifier.find_visual_element_center(roi_img, 500, 500)
        self.assertNotEqual((snapped_x, snapped_y), (500, 500))
        self.assertGreater(snapped_x, 500)

        # 3. Dynamic layout shift tracking
        band = Image.new("RGB", (260, 60), (245, 245, 245))
        template = Image.new("RGB", (30, 20), (255, 255, 255))
        d_t = ImageDraw.Draw(template)
        d_t.rectangle([0, 0, 29, 19], outline=(50, 50, 50), width=2)

        # Paste template shifted by +40px horizontally in the band
        band.paste(template, (80, 20))
        tracked = verifier.track_shifted_input_box(
            template_img=template,
            band_img=band,
            band_origin_x=100,
            band_origin_y=200,
            expected_x=100 + 40 + 15,
            expected_y=200 + 20 + 10
        )
        self.assertIsNotNone(tracked)
        tracked_x, tracked_y = tracked
        self.assertEqual(tracked_x, 100 + 80 + 15)
        self.assertEqual(tracked_y, 200 + 20 + 10)

    def test_click_variance_bounds(self):
        executor = AutomationExecutor(humanize=True, click_variance_enabled=True)
        # When enabled, Gaussian jitter applies within radius bounds
        for _ in range(50):
            vx, vy = executor.apply_click_variance(500, 500, radius_x=7, radius_y=4)
            self.assertTrue(493 <= vx <= 507)
            self.assertTrue(496 <= vy <= 504)

        # When disabled, exact coordinate is returned
        executor.click_variance_enabled = False
        vx, vy = executor.apply_click_variance(500, 500)
        self.assertEqual((vx, vy), (500, 500))

    def test_mouse_moves_directly_without_overshoot(self):
        from unittest.mock import patch
        executor = AutomationExecutor(humanize=True)
        with patch("pyautogui.position", return_value=(100, 100)), \
             patch("pyautogui.moveTo") as mock_move:
            executor.move_mouse_humanized(600, 600)
            # Must finish directly at the exact target coordinate
            mock_move.assert_called_with(600, 600)

    def test_smart_typos_math_and_numeric_protection(self):
        from core.automation import is_math_or_formula
        # Verify strict invariant: numbers, math formulas, equations, currencies must never typo
        math_strings = [
            "144",
            "-3.14159",
            "x^2 + 5x - 6 = 0",
            "$24.99",
            "(12 + 4) / 2 = 8",
            "100%",
            "2,500.00",
            "2sin(x) + cos(x) = 1"
        ]
        for s in math_strings:
            self.assertTrue(is_math_or_formula(s), f"Math string '{s}' should be protected from typos")

        # Regular english words must not match math regex
        word_strings = ["photosynthesis", "Mitochondria", "George Washington", "velocity"]
        for w in word_strings:
            self.assertFalse(is_math_or_formula(w), f"Word '{w}' should be eligible for natural typos")

    def test_reading_deliberation_skip_on_f9(self):
        from core.assistant_engine import AssistantEngine, EngineState
        from config import ConfigManager

        cm = ConfigManager()
        engine = AssistantEngine(config_manager=cm)

        # Set state to READING
        engine.set_state(EngineState.READING, "4.0s")
        self.assertFalse(engine._force_execute_after_reading)
        self.assertFalse(engine._skip_reading_event.is_set())

        # Calling confirm_and_execute() (F9) during reading should set skip flags immediately
        engine.confirm_and_execute()
        self.assertTrue(engine._force_execute_after_reading)
        self.assertTrue(engine._skip_reading_event.is_set())

    def test_multi_part_continuous_completion_chain(self):
        from unittest.mock import MagicMock
        from core.assistant_engine import AssistantEngine
        from config import ConfigManager

        cm = ConfigManager()
        cm.update(chain_multi_parts=True, auto_next=False)
        engine = AssistantEngine(config_manager=cm)
        engine.executor.execute_action_sequence = MagicMock()
        engine.trigger_check_button = MagicMock()
        engine.trigger_next_button = MagicMock()
        engine.trigger_solve = MagicMock()

        # When a multi-part question has finished its current part actions and has a next button:
        engine.last_result = {
            "actions": [{"type": "click", "x": 200, "y": 200}],
            "is_multi_part": True,
            "ready_to_advance": True,
            "next_button": {"screen_x": 500, "screen_y": 500}
        }
        engine.execute_current_solution()

        # It should advance via next_button, and automatically trigger solve for next part!
        engine.trigger_next_button.assert_called_once()
        engine.trigger_solve.assert_called_once()


if __name__ == "__main__":
    unittest.main()

