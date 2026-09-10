"""
Unit and integration tests for the Zero-Token Answer Verification & Recovery System.
Tests radio/checkbox detection, input fill verification, option band scanning,
and engine prevention of premature IDLE state on missed actions.
"""

import unittest
from PIL import Image, ImageDraw

from core.local_verifier import LocalVisualVerifier
from core.assistant_engine import AssistantEngine, EngineState
from config import AppConfig, ConfigManager


class TestZeroTokenVerification(unittest.TestCase):
    """Tests for zero-token verification heuristics and engine invariants."""

    def setUp(self):
        self.verifier = LocalVisualVerifier()

    def test_radio_button_selected_vs_unselected_detection(self):
        """Verifies that unselected and selected radio buttons are accurately identified."""
        # 1. Light theme unselected radio button (white background, gray ring, hollow center)
        unsel_img = Image.new("RGB", (40, 40), (255, 255, 255))
        d1 = ImageDraw.Draw(unsel_img)
        d1.ellipse([10, 10, 30, 30], outline=(160, 160, 160), width=2)
        is_sel, reason, conf = self.verifier.is_radio_or_checkbox_selected(unsel_img)
        self.assertFalse(is_sel, f"Expected unselected, got {reason}")

        # 2. Light theme selected radio button (with inner bullet dot)
        sel_img = Image.new("RGB", (40, 40), (255, 255, 255))
        d2 = ImageDraw.Draw(sel_img)
        d2.ellipse([10, 10, 30, 30], outline=(37, 99, 235), width=2)
        d2.ellipse([16, 16, 24, 24], fill=(37, 99, 235))
        is_sel2, reason2, conf2 = self.verifier.is_radio_or_checkbox_selected(sel_img)
        self.assertTrue(is_sel2, f"Expected selected, got {reason2}")
        self.assertGreater(conf2, 0.6)

        # 3. Dark theme unselected radio button
        dark_unsel = Image.new("RGB", (40, 40), (24, 24, 27))
        d3 = ImageDraw.Draw(dark_unsel)
        d3.ellipse([10, 10, 30, 30], outline=(100, 100, 100), width=2)
        is_sel3, reason3, conf3 = self.verifier.is_radio_or_checkbox_selected(dark_unsel)
        self.assertFalse(is_sel3, f"Expected dark unselected, got {reason3}")

        # 4. Dark theme selected radio button (bright blue active dot)
        dark_sel = Image.new("RGB", (40, 40), (24, 24, 27))
        d4 = ImageDraw.Draw(dark_sel)
        d4.ellipse([10, 10, 30, 30], outline=(59, 130, 246), width=2)
        d4.ellipse([16, 16, 24, 24], fill=(96, 165, 250))
        is_sel4, reason4, conf4 = self.verifier.is_radio_or_checkbox_selected(dark_sel)
        self.assertTrue(is_sel4, f"Expected dark selected, got {reason4}")

    def test_checkbox_checked_vs_unchecked_detection(self):
        """Verifies checkbox checked detection via inner high-contrast checkmark."""
        # Unchecked checkbox
        uncheck_img = Image.new("RGB", (40, 40), (255, 255, 255))
        d1 = ImageDraw.Draw(uncheck_img)
        d1.rectangle([10, 10, 30, 30], outline=(150, 150, 150), width=2)
        is_chk, reason, conf = self.verifier.is_radio_or_checkbox_selected(uncheck_img)
        self.assertFalse(is_chk, f"Expected unchecked, got {reason}")

        # Checked checkbox (with checkmark strokes inside)
        check_img = Image.new("RGB", (40, 40), (255, 255, 255))
        d2 = ImageDraw.Draw(check_img)
        d2.rectangle([10, 10, 30, 30], outline=(37, 99, 235), width=2)
        d2.line([14, 20, 19, 26], fill=(37, 99, 235), width=3)
        d2.line([19, 26, 27, 14], fill=(37, 99, 235), width=3)
        is_chk2, reason2, conf2 = self.verifier.is_radio_or_checkbox_selected(check_img)
        self.assertTrue(is_chk2, f"Expected checked, got {reason2}")

    def test_text_input_fill_detection(self):
        """Verifies that empty text inputs and filled text inputs are distinguished."""
        empty_img = Image.new("RGB", (60, 30), (255, 255, 255))
        d1 = ImageDraw.Draw(empty_img)
        d1.rectangle([2, 2, 58, 28], outline=(200, 200, 200), width=1)

        filled_img = Image.new("RGB", (60, 30), (255, 255, 255))
        d2 = ImageDraw.Draw(filled_img)
        d2.rectangle([2, 2, 58, 28], outline=(59, 130, 246), width=1)
        # Add simulated text glyphs
        d2.line([10, 8, 10, 22], fill=(0, 0, 0), width=2)
        d2.line([18, 8, 18, 16], fill=(0, 0, 0), width=2)
        d2.line([14, 16, 22, 16], fill=(0, 0, 0), width=2)
        d2.line([22, 8, 22, 22], fill=(0, 0, 0), width=2)

        is_filled1, reason1, conf1 = self.verifier.is_text_input_filled(empty_img)
        self.assertFalse(is_filled1, f"Expected empty input, got {reason1}")

        is_filled2, reason2, conf2 = self.verifier.is_text_input_filled(filled_img, before_roi=empty_img)
        self.assertTrue(is_filled2, f"Expected filled input, got {reason2}")

    def test_leftward_radio_discovery_in_band(self):
        """Tests that a circular control placed 35px to the left of the click coordinate is located."""
        band_w, band_h = 160, 40
        band_img = Image.new("RGB", (band_w, band_h), (255, 255, 255))
        d = ImageDraw.Draw(band_img)

        # Radio button centered at (45, 20), radius 10
        d.ellipse([35, 10, 55, 30], outline=(100, 100, 100), width=2)
        # Option text at (80, 20)
        d.line([80, 20, 140, 20], fill=(0, 0, 0), width=2)

        # AI clicked on text at screen_x = 580, screen_y = 300
        # band origin at screen_x = 500, screen_y = 280
        # click in band is at (80, 20)
        found = self.verifier.find_radio_or_checkbox_in_band(
            band_img,
            click_screen_x=580,
            click_screen_y=300,
            band_origin_x=500,
            band_origin_y=280,
            max_scan_left=60
        )
        self.assertIsNotNone(found, "Failed to locate circular radio button in band")
        # Radio center in band is (45, 20), so screen coords should be (545, 300)
        screen_x, screen_y = found
        self.assertAlmostEqual(screen_x, 545, delta=5)
        self.assertAlmostEqual(screen_y, 300, delta=4)

    def test_engine_prevent_idle_on_unverified_answer(self):
        """
        CRITICAL INVARIANT TEST:
        When an answer click fails to register (unverified), the engine must NOT
        transition to IDLE and must NOT advance to the next question.
        """
        engine = AssistantEngine()
        engine.config_manager.update(
            autonomous_mode=False,
            auto_next=True,
            local_verification_enabled=True
        )

        # Mock action that is NOT verified
        unverified_action = {
            "type": "click",
            "screen_x": 400,
            "screen_y": 500,
            "description": "Click Option C",
            "verified": False,
            "verification_reason": "unverified"
        }

        engine.last_result = {
            "question": "What is the capital of France?",
            "answer": "Paris",
            "ready_to_advance": True,
            "next_button": {"screen_x": 900, "screen_y": 900},
            "actions": [unverified_action]
        }

        # Mock executor to return unverified summary
        engine.executor.execute_action_sequence = lambda actions, delay_between=0.3: {
            "all_verified": False,
            "verified_count": 0,
            "total_verifiable": 1,
            "actions": actions
        }

        # Execute solution
        engine.execute_current_solution()

        # Engine MUST NOT be in IDLE!
        self.assertNotEqual(
            engine.state,
            EngineState.IDLE,
            "Engine must NOT transition to IDLE when an action is unverified!"
        )
        self.assertNotEqual(
            engine.state,
            EngineState.NAVIGATING,
            "Engine must NOT navigate/advance when an action is unverified!"
        )
        # Engine must be in WAITING_CONFIRMATION with UNVERIFIED notice
        self.assertEqual(engine.state, EngineState.WAITING_CONFIRMATION)
        self.assertFalse(engine.last_result["ready_to_advance"])

    def test_engine_advance_or_idle_on_verified_answer(self):
        """When an answer is verified, engine marks confirmed and advances or goes idle."""
        engine = AssistantEngine()
        engine.config_manager.update(
            autonomous_mode=False,
            auto_next=False,
            local_verification_enabled=True
        )

        # Mock action that is verified
        verified_action = {
            "type": "click",
            "screen_x": 400,
            "screen_y": 500,
            "description": "Click Option B",
            "verified": True,
            "verification_reason": "radio_inner_bullet"
        }

        engine.last_result = {
            "question": "What is 12 x 12?",
            "answer": "144",
            "ready_to_advance": True,
            "actions": [verified_action]
        }

        engine.executor.execute_action_sequence = lambda actions, delay_between=0.3: {
            "all_verified": True,
            "verified_count": 1,
            "total_verifiable": 1,
            "actions": actions
        }

        engine.execute_current_solution()

        # Because auto_next is False, verified solution transitions to IDLE
        self.assertEqual(engine.state, EngineState.IDLE)

    def test_verify_modal_dismissed(self):
        """Verifies zero-token modal dismissal detection against pre-modal baseline."""
        baseline = Image.new("RGB", (300, 300), (245, 245, 245))
        d1 = ImageDraw.Draw(baseline)
        d1.rectangle([50, 50, 250, 250], outline=(100, 100, 100), width=2)

        # Modal open: dark backdrop and center modal overlay
        modal_open = Image.new("RGB", (300, 300), (30, 30, 30))
        d2 = ImageDraw.Draw(modal_open)
        d2.rectangle([80, 80, 220, 220], fill=(255, 255, 255))

        # Test with modal open (should NOT be dismissed)
        is_dismissed1, diff1 = self.verifier.verify_modal_dismissed(baseline, modal_open)
        self.assertFalse(is_dismissed1)
        self.assertGreater(diff1, 10.0)

        # Modal dismissed: screen returns to baseline (with minor sub-pixel/caret variance)
        modal_closed = Image.new("RGB", (300, 300), (245, 245, 245))
        d3 = ImageDraw.Draw(modal_closed)
        d3.rectangle([50, 50, 250, 250], outline=(100, 100, 100), width=2)
        # Add tiny single-pixel caret
        d3.line([60, 60, 60, 70], fill=(0, 0, 0))

        is_dismissed2, diff2 = self.verifier.verify_modal_dismissed(baseline, modal_closed)
        self.assertTrue(is_dismissed2)
        self.assertLess(diff2, 3.5)

    def test_verify_screen_scrolled(self):
        """Verifies zero-token detection of content displacement from scrolling."""
        img1 = Image.new("RGB", (200, 200), (255, 255, 255))
        d1 = ImageDraw.Draw(img1)
        for y in range(20, 180, 30):
            d1.line([20, y, 180, y], fill=(0, 0, 0), width=3)

        # Shifting content vertically creates displacement
        img2 = Image.new("RGB", (200, 200), (255, 255, 255))
        d2 = ImageDraw.Draw(img2)
        for y in range(40, 200, 30):
            d2.line([20, y, 180, y], fill=(0, 0, 0), width=3)

        has_scrolled, diff = self.verifier.verify_screen_scrolled(img1, img2)
        self.assertTrue(has_scrolled)
        self.assertGreater(diff, 2.0)

        # Identical screen must report False (0 scroll)
        no_scroll, diff_zero = self.verifier.verify_screen_scrolled(img1, img1)
        self.assertFalse(no_scroll)

    def test_verify_drag_completion(self):
        """Verifies zero-token confirmation of drag-and-drop actions."""
        # Origin element starts with a shape, destination is blank
        start_before = Image.new("RGB", (40, 40), (255, 255, 255))
        d1 = ImageDraw.Draw(start_before)
        d1.ellipse([10, 10, 30, 30], fill=(220, 50, 50))

        start_after = Image.new("RGB", (40, 40), (255, 255, 255))  # shape removed

        dest_before = Image.new("RGB", (40, 40), (255, 255, 255))  # empty target
        dest_after = Image.new("RGB", (40, 40), (255, 255, 255))
        d2 = ImageDraw.Draw(dest_after)
        d2.ellipse([10, 10, 30, 30], fill=(220, 50, 50))  # shape dropped here

        is_drag_ok, reason = self.verifier.verify_drag_completion(
            start_before, start_after, dest_before, dest_after
        )
        self.assertTrue(is_drag_ok)

        # Failed drag: both start and dest unchanged
        fail_drag, _ = self.verifier.verify_drag_completion(
            start_before, start_before, dest_before, dest_before
        )
        self.assertFalse(fail_drag)

    def test_verify_screen_transition(self):
        """Verifies screen visual change detection for navigation clicks."""
        screen1 = Image.new("RGB", (200, 200), (255, 255, 255))
        screen2 = Image.new("RGB", (200, 200), (255, 255, 255))
        d2 = ImageDraw.Draw(screen2)
        d2.rectangle([20, 20, 180, 80], fill=(34, 197, 94))  # Green banner

        is_trans, diff = self.verifier.verify_screen_transition(screen1, screen2)
        self.assertTrue(is_trans)

        no_trans, _ = self.verifier.verify_screen_transition(screen1, screen1)
        self.assertFalse(no_trans)


if __name__ == "__main__":
    unittest.main()

