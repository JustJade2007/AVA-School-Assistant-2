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
from ui.home_view import HomeDashboard
from ui.asset_loader import apply_window_icon

from core.logger import get_logger

logger = get_logger("app")


class AVASchoolAssistantApp:
    """Main application lifecycle controller."""

    def __init__(self, start_mode: str = "home"):
        # Configure CustomTkinter appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config_manager = ConfigManager()
        self.engine = AssistantEngine(config_manager=self.config_manager)
        self.hotkey_manager = GlobalHotkeyManager()

        # Root window (stays withdrawn while top-level modules display)
        self.root = ctk.CTk()
        self.root.title("AVA School Assistant 2")
        self.root.geometry("1x1+-100+-100")
        self.root.withdraw()
        apply_window_icon(self.root)

        self.home_window: Optional[HomeDashboard] = None
        self.hud_window: Optional[HUDOverlay] = None
        self.settings_window: Optional[SettingsWindow] = None
        self.playground_window = None
        self.snipping_tool = None

        self._setup_hotkeys()

        # Initialize Home Dashboard as central command hub
        self.home_window = HomeDashboard(
            master=self.root,
            config_manager=self.config_manager,
            on_launch_worker=self.launch_automated_worker,
            on_launch_playground=self.open_playground,
            on_open_settings=self.open_settings,
            on_exit_app=self.quit_app
        )
        apply_window_icon(self.home_window)
        from ui.window_utils import ensure_taskbar_presence
        ensure_taskbar_presence(self.home_window)

        if start_mode == "worker":
            self.launch_automated_worker()
        elif start_mode == "playground":
            self.open_playground()
        else:
            self.home_window.lift()
            self.home_window.focus_force()

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
            "open_playground",
            hk.get("open_playground", "F3"),
            self.open_playground
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

    def _setup_hud(self):
        """Creates the floating anti-capture HUD overlay."""
        self.hud_window = HUDOverlay(
            master=self.root,
            engine=self.engine,
            on_open_settings=self.open_settings,
            on_close_app=self.return_to_home,
            on_snip_solve=self.start_snipping,
            on_open_playground=self.open_playground
        )
        apply_window_icon(self.hud_window)

    def launch_automated_worker(self):
        """Thread-safe trigger for launching the Automated Worker overlay."""
        try:
            self.root.after(0, self._do_launch_automated_worker)
        except Exception as e:
            logger.error(f"Failed to dispatch launch_automated_worker: {e}")

    def _do_launch_automated_worker(self):
        logger.info("Launching Automated Worker (HUD Mode)...")
        if self.home_window and self.home_window.winfo_exists():
            self.home_window.withdraw()

        if self.hud_window is None or not self.hud_window.winfo_exists():
            self._setup_hud()
        else:
            self.hud_window.deiconify()
            self.hud_window.lift()

        try:
            self.hotkey_manager.start()
        except Exception as e:
            logger.warning(f"Failed to start hotkeys: {e}")

    def return_to_home(self):
        """Thread-safe return to the Home Dashboard from any active module."""
        try:
            self.root.after(0, self._do_return_to_home)
        except Exception as e:
            logger.error(f"Failed to dispatch return_to_home: {e}")

    def _do_return_to_home(self):
        logger.info("Returning to AVA Command Hub Home...")
        # 1. Hide HUD overlay
        if self.hud_window and self.hud_window.winfo_exists():
            self.hud_window.withdraw()

        # 2. Hide or destroy Playground
        if self.playground_window and self.playground_window.winfo_exists():
            try:
                self.playground_window.destroy()
            except Exception:
                pass
            self.playground_window = None

        # 3. Stop background hotkeys & emergency stop solving
        try:
            self.hotkey_manager.stop()
        except Exception:
            pass
        try:
            self.engine.emergency_stop()
        except Exception:
            pass

        # 4. Show Home Dashboard
        if self.home_window and self.home_window.winfo_exists():
            self.home_window.deiconify()
            self.home_window.lift()
            self.home_window.focus_force()
            self.home_window.refresh_ai_status()

    def open_playground(self):
        """Thread-safe trigger for opening Playground Mode in a dedicated studio window."""
        try:
            self.root.after(0, self._do_open_playground)
        except Exception as e:
            logger.error(f"Failed to dispatch open_playground: {e}")

    def _do_open_playground(self):
        if self.playground_window is not None and self.playground_window.winfo_exists():
            self.playground_window.lift()
            self.playground_window.focus_force()
            return

        logger.info("Opening Playground Mode. Isolating background solving functions and hotkeys...")
        try:
            # 1. Temporarily stop global solving hotkeys to prevent typing conflicts in Word/browsers
            try:
                self.hotkey_manager.stop()
            except Exception as e:
                logger.debug(f"Error stopping hotkeys for Playground: {e}")

            # 2. Stop any active autonomous solving engine routines
            try:
                self.engine.emergency_stop()
            except Exception:
                pass

            # 3. Hide floating HUD overlay & Home window
            if self.hud_window and self.hud_window.winfo_exists():
                self.hud_window.withdraw()
            if self.home_window and self.home_window.winfo_exists():
                self.home_window.withdraw()

            from ui.playground.workspace import PlaygroundWorkspace

            self.playground_window = PlaygroundWorkspace(
                master=self.root,
                ai_client=self.engine.ai_client,
                config_manager=self.config_manager,
                on_exit=self.return_to_home
            )
            apply_window_icon(self.playground_window)
            self.playground_window.lift()
            self.playground_window.focus_force()
        except Exception as e:
            logger.error(f"Failed to open Playground Mode: {e}", exc_info=True)
            self.return_to_home()
            try:
                from tkinter import messagebox
                messagebox.showerror(
                    "Playground Error",
                    f"Failed to open Playground Mode:\n{e}"
                )
            except Exception:
                pass

    def _on_playground_closed(self):
        self.return_to_home()

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
        apply_window_icon(self.settings_window)

    def _on_settings_saved(self):
        """Re-applies hotkeys and UI settings when user updates configuration."""
        logger.info("Settings updated. Refreshing hotkeys and HUD...")
        self._setup_hotkeys()
        if self.hud_window and self.hud_window.winfo_exists():
            self.hud_window.apply_cloak()
            self.hud_window.attributes("-alpha", self.config.overlay_opacity)
            if hasattr(self.hud_window, "set_header_icon_size"):
                self.hud_window.set_header_icon_size(getattr(self.config, "header_icon_size", 11))
            self.hud_window.refresh_hotkey_labels()
            self.hud_window.mode_badge.configure(
                text="REVIEW MODE" if not self.config.autonomous_mode else "AUTO MODE"
            )
            if hasattr(self.hud_window, "debug_badge"):
                if self.config.debug_mode:
                    self.hud_window.debug_badge.pack(side="left", padx=4)
                else:
                    self.hud_window.debug_badge.pack_forget()

        if self.home_window and self.home_window.winfo_exists():
            self.home_window.refresh_ai_status()

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

    def bring_to_foreground(self):
        """
        Restores and brings the currently active application window to the foreground.
        Thread-safe and callable from external IPC signals when a duplicate launch is attempted.
        """
        try:
            self.root.after(0, self._do_bring_to_foreground)
        except Exception as e:
            logger.debug(f"Failed to dispatch bring_to_foreground: {e}")

    def _do_bring_to_foreground(self):
        logger.info("External activation signal received: Bringing active AVA window to foreground...")
        target_win = None
        if self.playground_window and self.playground_window.winfo_exists():
            target_win = self.playground_window
        elif self.hud_window and self.hud_window.winfo_exists() and not getattr(self.hud_window, "is_hidden", False):
            target_win = self.hud_window
            self.hud_window.show_overlay()
        elif self.home_window and self.home_window.winfo_exists():
            target_win = self.home_window

        if target_win:
            try:
                if hasattr(target_win, "state") and target_win.state() == "iconic":
                    target_win.deiconify()
                target_win.lift()
                target_win.focus_force()
            except Exception as e:
                logger.debug(f"Error focusing target window: {e}")

            if sys.platform == "win32":
                from core.single_instance import force_foreground_window
                from core.cloaking import get_window_hwnd
                hwnd = get_window_hwnd(target_win)
                if hwnd:
                    force_foreground_window(hwnd)

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
            from core.single_instance import cleanup_single_instance
            cleanup_single_instance()
        except Exception:
            pass
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
        if self.home_window and self.home_window.winfo_exists():
            try:
                self.home_window.destroy()
            except Exception:
                pass
        if self.playground_window and self.playground_window.winfo_exists():
            try:
                self.playground_window.destroy()
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
