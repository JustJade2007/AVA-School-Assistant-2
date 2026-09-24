"""
Unit tests for the cosmetic rework of the Automated Worker HUD Overlay in AVA School Assistant 2.
Tests cover:
- High-DPI PIL vector icon generation and caching (ui.hud_icons)
- HUDOverlay rounded corner window configuration with -transparentcolor
- Typewriter text reveal animation and cancellation
- Status dot breathing glow / pulse animation
- Modern floating action dock structure, buttons, hotkey refresh, and collapse toggling
"""

import unittest
from unittest.mock import MagicMock, patch
import customtkinter as ctk

from config import ConfigManager
from core.assistant_engine import AssistantEngine, EngineState
from ui.hud_icons import get_hud_icon, _ICON_CACHE
from ui.hud_overlay import HUDOverlay


class TestHUDCosmetics(unittest.TestCase):

    def setUp(self):
        _ICON_CACHE.clear()
        self.config_manager = ConfigManager()

    def test_get_hud_icon_all_types(self):
        """Verifies all HUD icons generate valid CTkImage objects with caching."""
        icon_names = [
            "close", "minimize", "collapse_up", "collapse_down", "settings",
            "debug", "snip", "playground", "solve", "execute", "stop",
            "next", "pause", "cloak", "retry"
        ]
        for name in icon_names:
            img = get_hud_icon(name, size=(16, 16), color="#ffffff")
            self.assertIsNotNone(img)
            self.assertIsInstance(img, ctk.CTkImage)

        # Verify caching: requesting same icon returns cached instance
        cached_img = get_hud_icon("solve", size=(16, 16), color="#ffffff")
        self.assertIn(("solve", (16, 16), "#ffffff"), _ICON_CACHE)

    def test_get_hud_icon_unknown_fallback(self):
        """Verifies unknown icon name safely falls back to a placeholder dot without crashing."""
        img = get_hud_icon("nonexistent_icon_name", size=(12, 12))
        self.assertIsNotNone(img)
        self.assertIsInstance(img, ctk.CTkImage)

    def test_hud_overlay_window_and_dock_structure(self):
        """Verifies HUDOverlay window transparency, corner radius, and action dock."""
        mock_engine = MagicMock(spec=AssistantEngine)
        mock_engine.config_manager = self.config_manager
        mock_engine.error_message = None
        mock_engine.last_error = None

        root = ctk.CTk()
        root.withdraw()
        try:
            with patch("ui.hud_overlay.apply_anti_capture", return_value=True), \
                 patch("ui.hud_overlay.apply_window_icon"):

                hud = HUDOverlay(
                    master=root,
                    engine=mock_engine,
                    on_open_settings=MagicMock(),
                    on_close_app=MagicMock(),
                    on_snip_solve=MagicMock(),
                    on_open_playground=MagicMock()
                )

                # 1. Window transparency keying
                self.assertEqual(hud.TRANSPARENT_KEY, "#010203")

                # 2. Main frame rounded border
                self.assertEqual(hud.main_frame.cget("corner_radius"), 14)
                self.assertEqual(hud.main_frame.cget("border_color"), "#3b82f6")

                # 3. Action dock hierarchy
                self.assertTrue(hasattr(hud, "dock_frame"))
                self.assertTrue(hasattr(hud, "actions_dock_frame"))
                self.assertTrue(hasattr(hud, "aux_dock_frame"))

                # 4. Primary hero buttons
                self.assertTrue(hasattr(hud, "btn_solve"))
                self.assertTrue(hasattr(hud, "btn_confirm"))
                self.assertTrue(hasattr(hud, "btn_next"))
                self.assertTrue(hasattr(hud, "btn_stop"))

                # 5. Aux row buttons
                self.assertTrue(hasattr(hud, "btn_pause"))
                self.assertTrue(hasattr(hud, "btn_scroll_up"))
                self.assertTrue(hasattr(hud, "btn_scroll_down"))
                self.assertTrue(hasattr(hud, "btn_inspect_whole"))
                self.assertTrue(hasattr(hud, "btn_test_cloak"))

                # 6. Header action buttons exist
                self.assertTrue(hasattr(hud, "btn_close"))
                self.assertTrue(hasattr(hud, "btn_hide"))
                self.assertTrue(hasattr(hud, "btn_collapse"))
                self.assertTrue(hasattr(hud, "btn_settings"))
                self.assertTrue(hasattr(hud, "btn_debug"))
                self.assertTrue(hasattr(hud, "btn_snip"))
                self.assertTrue(hasattr(hud, "btn_playground"))

                # 7. Hotkey labels update correctly
                hud.config_manager.config.hotkeys["trigger_solve"] = "F1"
                hud.refresh_hotkey_labels()
                self.assertIn("F1", hud.btn_solve.cget("text"))

                # 8. Collapse toggle updates geometry and icon
                hud.toggle_collapse()
                self.assertTrue(hud.is_collapsed)
                hud.toggle_collapse()
                self.assertFalse(hud.is_collapsed)

                hud.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_typewriter_text_animation(self):
        """Verifies _animate_typewriter_text reveals text chunk by chunk and cancels cleanly."""
        mock_engine = MagicMock(spec=AssistantEngine)
        mock_engine.config_manager = self.config_manager
        mock_engine.error_message = None
        mock_engine.last_error = None

        root = ctk.CTk()
        root.withdraw()
        try:
            with patch("ui.hud_overlay.apply_anti_capture", return_value=True), \
                 patch("ui.hud_overlay.apply_window_icon"):

                hud = HUDOverlay(master=root, engine=mock_engine)

                mock_label = MagicMock(spec=ctk.CTkLabel)
                mock_label.winfo_exists.return_value = True

                after_callbacks = []
                def fake_after(ms, func):
                    after_callbacks.append(func)
                    return f"after_id_{len(after_callbacks)}"

                hud.after = fake_after
                hud.winfo_exists = lambda: True

                callback_fired = []
                hud._animate_typewriter_text(
                    mock_label,
                    full_text="Hello World",
                    char_delay_ms=5,
                    chunk_size=3,
                    callback=lambda: callback_fired.append(True)
                )

                # Initial step sets first chunk "Hel"
                mock_label.configure.assert_called_with(text="Hel")

                # Execute remaining scheduled steps
                while after_callbacks:
                    cb = after_callbacks.pop(0)
                    cb()

                # Final text must be the complete string
                mock_label.configure.assert_called_with(text="Hello World")
                self.assertEqual(len(callback_fired), 1)

                hud.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_status_pulse_animation(self):
        """Verifies _start_status_pulse and _stop_status_pulse cycling and cancellation."""
        mock_engine = MagicMock(spec=AssistantEngine)
        mock_engine.config_manager = self.config_manager
        mock_engine.error_message = None
        mock_engine.last_error = None

        root = ctk.CTk()
        root.withdraw()
        try:
            with patch("ui.hud_overlay.apply_anti_capture", return_value=True), \
                 patch("ui.hud_overlay.apply_window_icon"):

                hud = HUDOverlay(master=root, engine=mock_engine)
                hud.status_dot = MagicMock()
                hud.status_dot.winfo_exists.return_value = True
                hud.winfo_exists = lambda: True

                hud.after = MagicMock(return_value="pulse_timer_123")
                hud.after_cancel = MagicMock()

                # Start pulse for scanning state
                hud._start_status_pulse("#38bdf8")
                self.assertEqual(hud._pulse_after_id, "pulse_timer_123")
                hud.after.assert_called()

                # Stop pulse cancels timer
                hud._stop_status_pulse()
                hud.after_cancel.assert_called_with("pulse_timer_123")
                self.assertIsNone(hud._pulse_after_id)

                hud.destroy()
        finally:
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
