"""
Main Application Coordinator for AVA School Assistant 2.
Initializes the root runtime, launches the anti-capture HUD overlay,
starts the global hotkeys listener, and coordinates settings windows.
"""

import sys
import tkinter as tk
import customtkinter as ctk
from typing import Optional

from config import ConfigManager, AppConfig
from core.assistant_engine import AssistantEngine
from core.hotkeys import GlobalHotkeyManager
from ui.hud_overlay import HUDOverlay
from ui.settings_view import SettingsWindow


from core.logger import get_logger

logger = get_logger("app")


class AVASchoolAssistantApp:
    """Main application lifecycle controller."""

    def __init__(self):
        # Configure CustomTkinter appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config_manager = ConfigManager()
        self.engine = AssistantEngine(config_manager=self.config_manager)
        self.hotkey_manager = GlobalHotkeyManager()

        # Root window (can stay hidden while HUD overlay floats)
        self.root = ctk.CTk()
        self.root.title("AVA School Assistant 2")
        self.root.geometry("1x1+-100+-100")
        self.root.overrideredirect(True)
        self.root.withdraw()

        self.hud_window: Optional[HUDOverlay] = None
        self.settings_window: Optional[SettingsWindow] = None
        self.snipping_tool = None

        self._setup_hotkeys()
        self._setup_hud()

    @property
    def config(self) -> AppConfig:
        return self.config_manager.config

    def _setup_hotkeys(self):
        """Binds global keyboard shortcuts to assistant engine commands."""
        hk = self.config.hotkeys
        self.hotkey_manager.register_hotkey(
            "trigger_solve",
            hk.get("trigger_solve", "F8"),
            self.engine.trigger_solve
        )
        self.hotkey_manager.register_hotkey(
            "confirm_action",
            hk.get("confirm_action", "F9"),
            self.engine.confirm_and_execute
        )
        self.hotkey_manager.register_hotkey(
            "next_question",
            hk.get("next_question", "F10"),
            self.engine.trigger_next_question
        )
        self.hotkey_manager.register_hotkey(
            "snip_solve",
            hk.get("snip_solve", "F4"),
            self.start_snipping
        )
        self.hotkey_manager.register_hotkey(
            "pause_resume",
            hk.get("pause_resume", "F7"),
            self.engine.pause_resume
        )
        self.hotkey_manager.register_hotkey(
            "emergency_stop",
            hk.get("emergency_stop", "F12"),
            self.engine.emergency_stop
        )
        self.hotkey_manager.register_hotkey(
            "toggle_overlay",
            hk.get("toggle_overlay", "F6"),
            self.toggle_overlay
        )
        self.hotkey_manager.register_hotkey(
            "close_app",
            hk.get("close_app", "Ctrl+Shift+Q"),
            self.quit_app
        )
        self.hotkey_manager.start()

    def _setup_hud(self):
        """Creates the floating anti-capture HUD overlay."""
        self.hud_window = HUDOverlay(
            master=self.root,
            engine=self.engine,
            on_open_settings=self.open_settings,
            on_close_app=self.quit_app,
            on_snip_solve=self.start_snipping
        )

    def open_settings(self):
        """Opens or focuses the Settings Dashboard."""
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        self.settings_window = SettingsWindow(
            master=self.root,
            on_save_callback=self._on_settings_saved
        )

    def _on_settings_saved(self):
        """Re-applies hotkeys and UI settings when user updates configuration."""
        logger.info("Settings updated. Refreshing hotkeys and HUD...")
        self._setup_hotkeys()
        if self.hud_window and self.hud_window.winfo_exists():
            self.hud_window.apply_cloak()
            self.hud_window.attributes("-alpha", self.config.overlay_opacity)
            self.hud_window.refresh_hotkey_labels()
            self.hud_window.mode_badge.configure(
                text="REVIEW MODE" if not self.config.autonomous_mode else "AUTO MODE"
            )
            if hasattr(self.hud_window, "debug_badge"):
                if self.config.debug_mode:
                    self.hud_window.debug_badge.pack(side="left", padx=4)
                else:
                    self.hud_window.debug_badge.pack_forget()

    def toggle_overlay(self):
        """Thread-safe toggle for showing/hiding the HUD overlay."""
        try:
            self.root.after(0, self._do_toggle_overlay)
        except Exception as e:
            logger.error(f"Failed to dispatch toggle_overlay: {e}")

    def _do_toggle_overlay(self):
        if self.hud_window and self.hud_window.winfo_exists():
            is_visible = self.hud_window.toggle_visibility()
            logger.info(f"Overlay visibility toggled: {'Visible' if is_visible else 'Hidden'}")

    def start_snipping(self):
        """Thread-safe trigger for fullscreen cloaked snip tool."""
        try:
            self.root.after(0, self._do_start_snipping)
        except Exception as e:
            logger.error(f"Failed to dispatch start_snipping: {e}")

    def _do_start_snipping(self):
        logger.info("Launching Snip Box Tool (F4)...")
        from ui.snipping_tool import SnippingOverlay
        self.snipping_tool = SnippingOverlay(
            master=self.root,
            on_snip_complete=lambda region: self.engine.trigger_solve(region=region)
        )
        self.snipping_tool.start()

    def quit_app(self):
        """Thread-safe shutdown of application and background listeners."""
        try:
            self.root.after(0, self._do_quit_app)
        except Exception as e:
            logger.error(f"Failed to dispatch quit_app: {e}")
            self._do_quit_app()

    def _do_quit_app(self):
        logger.info("Exiting AVA School Assistant 2...")
        try:
            self.hotkey_manager.stop()
        except Exception as e:
            logger.debug(f"Error stopping hotkey listener on quit: {e}")
        try:
            self.engine.emergency_stop()
        except Exception:
            pass
        if self.snipping_tool:
            try:
                self.snipping_tool._close()
            except Exception:
                pass
        if self.settings_window and self.settings_window.winfo_exists():
            try:
                if hasattr(self.settings_window, "_save_and_close"):
                    self.settings_window._save_and_close()
                else:
                    self.settings_window.destroy()
            except Exception:
                pass
        if self.hud_window and self.hud_window.winfo_exists():
            if hasattr(self.hud_window, "debug_window") and self.hud_window.debug_window and self.hud_window.debug_window.winfo_exists():
                try:
                    self.hud_window.debug_window.destroy()
                except Exception:
                    pass
            try:
                self.hud_window.destroy()
            except Exception:
                pass
        try:
            self.config_manager.save()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        logger.info("AVA School Assistant 2 terminated cleanly.")

    def run(self):
        """Starts main event loop."""
        logger.info("AVA School Assistant 2 is active!")
        logger.info(f"Active Hotkeys: {self.config.hotkeys}")
        try:
            self.root.mainloop()
        finally:
            self.hotkey_manager.stop()
