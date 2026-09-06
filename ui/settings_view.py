"""
Configuration and Settings Dashboard for AVA School Assistant 2.
CustomTkinter interface for API credentials, AI model selection,
execution modes, humanization settings, and hotkeys.
"""

import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Optional, Callable, Dict, List

from config import AppConfig, ConfigManager, AVAILABLE_MODELS
from core.cloaking import is_anti_capture_supported
from core.ai_client import AIClient
from core.logger import get_log_directory, get_log_file_path, clear_log_file, get_logger
from ui.debug_window import DebugWindow

logger = get_logger("settings")


class SettingsWindow(ctk.CTkToplevel):
    """Configuration dashboard for user preferences."""

    def __init__(self, master, on_save_callback: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.config_manager = ConfigManager()
        self.on_save_callback = on_save_callback
        self._last_test_msg = ""
        self.hotkey_entries: Dict[str, ctk.CTkEntry] = {}
        self.model_chips: List[ctk.CTkButton] = []

        self.current_provider = (self.config.ai_provider or "gemini").lower()
        self.provider_keys: Dict[str, str] = {
            "gemini": self.config.get_api_key_for_provider("gemini"),
            "openai": self.config.get_api_key_for_provider("openai"),
            "anthropic": self.config.get_api_key_for_provider("anthropic"),
            "custom": self.config.get_api_key_for_provider("custom"),
        }

        self.title("AVA School Assistant 2 - Configuration Dashboard")
        self.geometry("660x740")
        self.minsize(580, 600)
        self.configure(fg_color="#18181b")

        # Auto-save settings if user closes window via titlebar 'X' button
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._build_ui()
        self._load_values()

    def _on_window_close(self):
        """Called when user closes window via titlebar 'X'. Automatically persists settings."""
        self._save_and_close()

    @property
    def config(self) -> AppConfig:
        return self.config_manager.config

    def _build_ui(self):
        # Header banner
        header = ctk.CTkFrame(self, fg_color="#27272a", corner_radius=8)
        header.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            header,
            text="⚙ SYSTEM CONFIGURATION & PREFERENCES",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#60a5fa"
        ).pack(side="left", padx=12, pady=10)

        # Tabview for organizing sections
        self.tabs = ctk.CTkTabview(self, fg_color="#27272a", segmented_button_selected_color="#2563eb")
        self.tabs.pack(fill="both", expand=True, padx=16, pady=8)

        self.tab_ai = self.tabs.add("🤖 AI & Model")
        self.tab_exec = self.tabs.add("⚡ Execution & Behavior")
        self.tab_cloak = self.tabs.add("🛡️ Anti-Capture & HUD")
        self.tab_display = self.tabs.add("🖥️ Display & Calibration")
        self.tab_keys = self.tabs.add("⌨ Hotkeys")
        self.tab_debug = self.tabs.add("🐞 Debug & Logging")

        self._build_ai_tab()
        self._build_exec_tab()
        self._build_cloak_tab()
        self._build_display_tab()
        self._build_keys_tab()
        self._build_debug_tab()

        # Bottom Save / Cancel bar
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=16, pady=(8, 16))

        self.btn_save = ctk.CTkButton(
            bottom_bar,
            text="💾 Save & Apply Settings",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=36,
            command=self._save_and_close
        )
        self.btn_save.pack(side="right", padx=6)

        self.btn_cancel = ctk.CTkButton(
            bottom_bar,
            text="Cancel",
            font=ctk.CTkFont(size=12),
            fg_color="#4b5563",
            hover_color="#374151",
            height=36,
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", padx=6)

    # --- TAB 1: AI & MODEL ---
    def _build_ai_tab(self):
        f = self.tab_ai

        # Provider Selector
        ctk.CTkLabel(f, text="AI Provider:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self.combo_provider = ctk.CTkComboBox(
            f,
            values=["gemini", "openai", "anthropic", "custom"],
            command=self._on_provider_changed,
            width=260
        )
        self.combo_provider.grid(row=0, column=1, sticky="w", padx=12, pady=(12, 4))

        # Model Selector / Entry
        ctk.CTkLabel(f, text="Model Name:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="w", padx=12, pady=6)
        model_input_frame = ctk.CTkFrame(f, fg_color="transparent")
        model_input_frame.grid(row=1, column=1, sticky="w", padx=12, pady=6)

        current_provider = (self.config.ai_provider or "gemini").lower()
        initial_models = AVAILABLE_MODELS.get(current_provider, ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])

        self.combo_model = ctk.CTkComboBox(model_input_frame, values=initial_models, width=200)
        self.combo_model.pack(side="left")
        if self.config.model_name:
            self.combo_model.set(self.config.model_name)
        elif initial_models:
            self.combo_model.set(initial_models[0])

        self.btn_autofill_model = ctk.CTkButton(
            model_input_frame,
            text="✨ Autofill",
            width=68,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._autofill_default_model
        )
        self.btn_autofill_model.pack(side="left", padx=(6, 0))

        # Quick Model Presets Row
        ctk.CTkLabel(
            f,
            text="Quick Presets:",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 6))

        self.frame_model_chips = ctk.CTkFrame(f, fg_color="transparent")
        self.frame_model_chips.grid(row=2, column=1, sticky="w", padx=12, pady=(0, 6))
        self._render_model_chips(current_provider)

        # API Key
        ctk.CTkLabel(f, text="API Key:", font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, sticky="w", padx=12, pady=8)
        key_frame = ctk.CTkFrame(f, fg_color="transparent")
        key_frame.grid(row=3, column=1, sticky="ew", padx=12, pady=8)

        self.entry_api_key = ctk.CTkEntry(key_frame, show="•", width=200)
        self.entry_api_key.pack(side="left", fill="x", expand=True)

        self.btn_toggle_key = ctk.CTkButton(
            key_frame,
            text="👁",
            width=32,
            fg_color="#3f3f46",
            command=self._toggle_key_visibility
        )
        self.btn_toggle_key.pack(side="left", padx=(4, 0))

        # Custom Base URL (for OpenRouter, Local Ollama, etc.)
        self.lbl_custom_url = ctk.CTkLabel(f, text="Custom Base URL:", font=ctk.CTkFont(weight="bold"))
        self.lbl_custom_url.grid(row=4, column=0, sticky="w", padx=12, pady=8)
        self.entry_custom_url = ctk.CTkEntry(f, width=260)
        self.entry_custom_url.grid(row=4, column=1, sticky="w", padx=12, pady=8)

        # Test Connection button & status
        test_frame = ctk.CTkFrame(f, fg_color="#18181b", corner_radius=8)
        test_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=16)

        self.btn_test_conn = ctk.CTkButton(
            test_frame,
            text="🔗 Test API Connection",
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            width=160,
            command=self._test_api_connection
        )
        self.btn_test_conn.pack(side="left", padx=12, pady=10)

        self.lbl_conn_status = ctk.CTkLabel(
            test_frame,
            text="Not tested",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        self.lbl_conn_status.pack(side="left", padx=10)

        self.btn_view_full_conn = ctk.CTkButton(
            test_frame,
            text="🔍 View Details",
            width=90,
            height=26,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._show_conn_details
        )

    def _autofill_default_model(self):
        """Autofills the primary/recommended model for the selected provider."""
        provider = self.combo_provider.get().strip().lower()
        models = AVAILABLE_MODELS.get(provider, ["gemini-3.6-flash"])
        if models:
            self.combo_model.set(models[0])

    def _render_model_chips(self, provider: str):
        """Displays clickable chip buttons for available models under the current provider."""
        if not hasattr(self, "frame_model_chips") or self.frame_model_chips is None:
            return

        for widget in self.frame_model_chips.winfo_children():
            widget.destroy()

        provider = provider.lower()
        models = AVAILABLE_MODELS.get(provider, [])
        for m in models[:5]:
            chip_label = m
            if chip_label.startswith("gemini-"):
                chip_label = chip_label.replace("gemini-", "⚡ ")
            elif chip_label.startswith("claude-"):
                chip_label = chip_label.replace("claude-", "🧠 ")
            elif chip_label.startswith("gpt-"):
                chip_label = chip_label.replace("gpt-", "🤖 ")

            btn = ctk.CTkButton(
                self.frame_model_chips,
                text=chip_label,
                height=24,
                font=ctk.CTkFont(size=10),
                fg_color="#27272a",
                hover_color="#3b82f6",
                command=lambda name=m: self.combo_model.set(name)
            )
            btn.pack(side="left", padx=(0, 4))

    def _toggle_key_visibility(self):
        if self.entry_api_key.cget("show") == "•":
            self.entry_api_key.configure(show="")
        else:
            self.entry_api_key.configure(show="•")

    def _on_provider_changed(self, provider: str, preserve_model: bool = False):
        new_provider = provider.lower()

        # Cache currently entered key for previous provider
        if hasattr(self, "current_provider") and hasattr(self, "entry_api_key") and hasattr(self, "provider_keys"):
            current_text = self.entry_api_key.get().strip()
            self.provider_keys[self.current_provider] = current_text

        self.current_provider = new_provider

        # Populate entry with new provider's key
        if hasattr(self, "entry_api_key") and hasattr(self, "provider_keys"):
            self.entry_api_key.delete(0, "end")
            self.entry_api_key.insert(0, self.provider_keys.get(new_provider, ""))

        models = AVAILABLE_MODELS.get(new_provider, ["default"])
        self.combo_model.configure(values=models)
        if not preserve_model and models:
            self.combo_model.set(models[0])

        self._render_model_chips(new_provider)

        # Show or hide custom URL field
        if new_provider == "custom":
            self.lbl_custom_url.grid()
            self.entry_custom_url.grid()
        else:
            self.lbl_custom_url.grid_remove()
            self.entry_custom_url.grid_remove()

    def _test_api_connection(self):
        provider = self.combo_provider.get().strip().lower()
        key = self.entry_api_key.get().strip()
        model = self.combo_model.get().strip()
        custom_url = self.entry_custom_url.get().strip()

        self.lbl_conn_status.configure(text="Testing connection...", text_color="#38bdf8")
        self.btn_test_conn.configure(state="disabled")
        self.btn_view_full_conn.pack_forget()

        def task():
            client = AIClient(
                provider=provider,
                api_key=key,
                model_name=model,
                custom_base_url=custom_url
            )
            ok, msg = client.test_connection()
            color = "#10b981" if ok else "#ef4444"

            # Auto-persist verified credentials immediately upon connection success!
            if ok and key:
                if hasattr(self, "provider_keys"):
                    self.provider_keys[provider] = key
                update_kwargs = {
                    "ai_provider": provider,
                    "model_name": model,
                    "api_key": key,
                    f"{provider}_api_key": key,
                }
                if provider == "custom":
                    update_kwargs["custom_api_base"] = custom_url
                self.config_manager.update(**update_kwargs)
                logger.info(f"Auto-persisted verified {provider} credentials to config.")

            self.after(0, lambda: self._update_test_status(ok, msg, color))

        threading.Thread(target=task, daemon=True).start()

    def _update_test_status(self, ok: bool, msg: str, color: str):
        self._last_test_msg = msg
        self.btn_test_conn.configure(state="normal")
        if len(msg) <= 65:
            self.lbl_conn_status.configure(text=msg, text_color=color)
            self.btn_view_full_conn.pack_forget()
        else:
            self.lbl_conn_status.configure(text=msg[:60] + "...", text_color=color)
            self.btn_view_full_conn.pack(side="left", padx=6)

    def _show_conn_details(self):
        if not self._last_test_msg:
            return
        details_win = ctk.CTkToplevel(self)
        details_win.title("API Connection Response Details")
        details_win.geometry("560x360")
        details_win.attributes("-topmost", True)
        ctk.CTkLabel(
            details_win,
            text="Server Response Details:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(12, 4))

        txt = tk.Text(details_win, bg="#0f172a", fg="#f87171", font=("Consolas", 10), wrap="word")
        txt.insert("1.0", self._last_test_msg)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=16, pady=8)

        btn_box = ctk.CTkFrame(details_win, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 12))

        def copy_msg():
            self.clipboard_clear()
            self.clipboard_append(self._last_test_msg)
            messagebox.showinfo("Copied", "Response copied to clipboard.")

        ctk.CTkButton(btn_box, text="📋 Copy Response", width=120, command=copy_msg).pack(side="left")
        ctk.CTkButton(btn_box, text="Close", width=80, command=details_win.destroy).pack(side="right")

    # --- TAB 2: EXECUTION & BEHAVIOR ---
    def _build_exec_tab(self):
        # Scrollable container so all behavioral controls fit comfortably
        scroll_f = ctk.CTkScrollableFrame(self.tab_exec, fg_color="transparent")
        scroll_f.pack(fill="both", expand=True, padx=4, pady=4)
        f = scroll_f

        # Autonomous mode switch
        self.switch_autonomous = ctk.CTkSwitch(
            f,
            text="Autonomous Mode (Solve & Execute immediately without asking)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_autonomous.pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            f,
            text="If disabled, AVA shows the answer on the HUD and highlights targets,\nwaiting for your confirmation (F9) before moving the mouse.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=42, pady=(0, 10))

        # Auto next switch
        self.switch_auto_next = ctk.CTkSwitch(
            f,
            text="Auto Click Next Question (Advance automatically)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_auto_next.pack(anchor="w", padx=12, pady=(4, 4))

        # Next delay slider
        delay_frame = ctk.CTkFrame(f, fg_color="transparent")
        delay_frame.pack(fill="x", padx=42, pady=(0, 10))
        self.lbl_next_delay = ctk.CTkLabel(delay_frame, text="Delay before clicking Next: 2.0s")
        self.lbl_next_delay.pack(anchor="w")
        self.slider_next_delay = ctk.CTkSlider(
            delay_frame,
            from_=0.5,
            to=8.0,
            number_of_steps=15,
            command=lambda v: self.lbl_next_delay.configure(text=f"Delay before clicking Next: {v:.1f}s")
        )
        self.slider_next_delay.pack(fill="x", pady=4)

        # Continuous Multi-Part Completion Switch
        self.switch_chain_multi_parts = ctk.CTkSwitch(
            f,
            text="Continuous Multi-Part Completion (Do not stop until question is done)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_chain_multi_parts.pack(anchor="w", padx=12, pady=(4, 4))
        ctk.CTkLabel(
            f,
            text="Automatically checks after clicking Check/Next for subsequent question parts\nand continues solving until all sequential parts are completed.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=42, pady=(0, 10))

        # Humanized movement switch
        self.switch_humanize = ctk.CTkSwitch(
            f,
            text="Humanize Mouse & Typing (Bézier curves & natural cadence)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_humanize.pack(anchor="w", padx=12, pady=(6, 4))

        # Mouse Speed slider
        speed_frame = ctk.CTkFrame(f, fg_color="transparent")
        speed_frame.pack(fill="x", padx=42, pady=(0, 10))
        self.lbl_mouse_speed = ctk.CTkLabel(speed_frame, text="Mouse Movement Pace: Normal (0.4s)")
        self.lbl_mouse_speed.pack(anchor="w")
        self.slider_mouse_speed = ctk.CTkSlider(
            speed_frame,
            from_=0.1,
            to=1.2,
            number_of_steps=11,
            command=lambda v: self.lbl_mouse_speed.configure(text=f"Mouse Movement Pace: {v:.2f}s")
        )
        self.slider_mouse_speed.pack(fill="x", pady=4)

        # Reading Deliberation Switch & Slider
        self.switch_reading_delay = ctk.CTkSwitch(
            f,
            text="Reading Deliberation Delay (Human-paced question reading)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_reading_delay.pack(anchor="w", padx=12, pady=(4, 4))

        reading_frame = ctk.CTkFrame(f, fg_color="transparent")
        reading_frame.pack(fill="x", padx=42, pady=(0, 10))
        self.lbl_base_reading = ctk.CTkLabel(reading_frame, text="Base Reading Pause: 4.0s (Skip anytime with F9)")
        self.lbl_base_reading.pack(anchor="w")
        self.slider_base_reading = ctk.CTkSlider(
            reading_frame,
            from_=1.0,
            to=8.0,
            number_of_steps=14,
            command=lambda v: self.lbl_base_reading.configure(text=f"Base Reading Pause: {v:.1f}s (Skip anytime with F9)")
        )
        self.slider_base_reading.pack(fill="x", pady=4)

        # Gaussian Click Jitter Switch
        self.switch_click_variance = ctk.CTkSwitch(
            f,
            text="Gaussian Click Jitter (Subtle off-center variance)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_click_variance.pack(anchor="w", padx=12, pady=(4, 4))
        ctk.CTkLabel(
            f,
            text="Applies organic Gaussian jitter so clicks never land on the exact mathematical center pixel.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=42, pady=(0, 8))

        # Smart Typo Simulation Switch
        self.switch_smart_typos = ctk.CTkSwitch(
            f,
            text="Smart Typo Simulation (Realistic word typos & backspace fixes)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_smart_typos.pack(anchor="w", padx=12, pady=(4, 4))
        ctk.CTkLabel(
            f,
            text="Introduces rare adjacent QWERTY key slips on words with Backspace fixes.\nPure numbers, equations, and code are 100% protected and typo-free.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=42, pady=(0, 8))

        # Zero-Token Local Verification Switch
        self.switch_local_verification = ctk.CTkSwitch(
            f,
            text="Zero-Token Local Verification (Action validation & layout shift tracking)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_local_verification.pack(anchor="w", padx=12, pady=(4, 4))
        ctk.CTkLabel(
            f,
            text="Locally verifies element response and tracks shifted blanks when typed text expands inputs.\nOperates purely on local screen pixels with ZERO AI token consumption.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=42, pady=(0, 12))

    # --- TAB 3: ANTI-CAPTURE & HUD ---
    def _build_cloak_tab(self):
        f = self.tab_cloak

        # Support check
        supported = is_anti_capture_supported()
        status_box = ctk.CTkFrame(f, fg_color="#18181b", corner_radius=8)
        status_box.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            status_box,
            text=f"Hardware Anti-Capture Status: {'SUPPORTED' if supported else 'UNSUPPORTED'}",
            font=ctk.CTkFont(weight="bold"),
            text_color="#10b981" if supported else "#ef4444"
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            status_box,
            text="Uses Windows SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE).\n"
                 "When enabled, HUD & Visual Targets are completely invisible to screen shares,\n"
                 "proctoring tools (Honorlock, Proctorio, LockDown Browser), Discord, and Zoom.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        self.switch_anti_capture = ctk.CTkSwitch(
            f,
            text="Enable Anti-Capture Cloaking for HUD & Target Canvas",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_anti_capture.pack(anchor="w", padx=16, pady=8)

        # Opacity slider
        opacity_frame = ctk.CTkFrame(f, fg_color="transparent")
        opacity_frame.pack(fill="x", padx=16, pady=8)
        self.lbl_opacity = ctk.CTkLabel(opacity_frame, text="HUD Opacity: 95%")
        self.lbl_opacity.pack(anchor="w")
        self.slider_opacity = ctk.CTkSlider(
            opacity_frame,
            from_=0.5,
            to=1.0,
            number_of_steps=10,
            command=lambda v: self.lbl_opacity.configure(text=f"HUD Opacity: {int(v * 100)}%")
        )
        self.slider_opacity.pack(fill="x", pady=4)

    # --- TAB: DISPLAY & CALIBRATION ---
    def _build_display_tab(self):
        f = self.tab_display

        # System Metrics Box
        metrics_box = ctk.CTkFrame(f, fg_color="#18181b", corner_radius=8)
        metrics_box.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(
            metrics_box,
            text="🖥️ Detected Workstation Display Environment",
            font=ctk.CTkFont(weight="bold"),
            text_color="#60a5fa"
        ).pack(anchor="w", padx=12, pady=(10, 2))

        sys_metrics_text = "Querying display..."
        try:
            import ctypes
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            dpi = getattr(ctypes.windll.user32, 'GetDpiForSystem', lambda: 96)()
            scale_pct = int((dpi / 96.0) * 100)
            sys_metrics_text = f"Physical Resolution: {w} × {h}  |  Windows Scaling: {scale_pct}% ({dpi} DPI)"
        except Exception:
            sys_metrics_text = "Windows display metrics available on Windows 10/11."

        ctk.CTkLabel(
            metrics_box,
            text=sys_metrics_text,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#10b981"
        ).pack(anchor="w", padx=12, pady=(2, 10))

        # Capture Resolution Frame
        res_frame = ctk.CTkFrame(f, fg_color="transparent")
        res_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            res_frame,
            text="AI Screenshot Capture Resolution:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(0, 2))

        self.combo_capture_res = ctk.CTkComboBox(
            res_frame,
            values=[
                "1920p (Fast / Balanced - Recommended)",
                "2560p (High Quality Detail)",
                "Native / Unscaled (Full Workstation Resolution)"
            ],
            width=360
        )
        self.combo_capture_res.pack(anchor="w", pady=2)

        # Coordinate Translation Mode Frame
        mode_frame = ctk.CTkFrame(f, fg_color="transparent")
        mode_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            mode_frame,
            text="Spatial Coordinate Translation Mode:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(0, 2))

        self.combo_coord_mode = ctk.CTkComboBox(
            mode_frame,
            values=[
                "Normalized [0-1000] (Pinpoint Accuracy for Gemini & Claude)",
                "Auto-Detect (Adaptive)",
                "Raw Pixels (Legacy)"
            ],
            width=360
        )
        self.combo_coord_mode.pack(anchor="w", pady=2)

        # Manual Pixel Calibration Frame
        cal_box = ctk.CTkFrame(f, fg_color="#1f2937", corner_radius=8)
        cal_box.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            cal_box,
            text="🎯 Fine-Tuning & Offset Calibration",
            font=ctk.CTkFont(weight="bold"),
            text_color="#f3f4f6"
        ).pack(anchor="w", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            cal_box,
            text="Adjust if clicks are slightly off on non-standard DPI scales or multi-monitor setups.\n"
                 "Offsets shift the target in pixels (+X = right, +Y = down).",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 6))

        grid_f = ctk.CTkFrame(cal_box, fg_color="transparent")
        grid_f.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(grid_f, text="X Offset (px):").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.entry_cal_offset_x = ctk.CTkEntry(grid_f, width=80)
        self.entry_cal_offset_x.grid(row=0, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(grid_f, text="Y Offset (px):").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        self.entry_cal_offset_y = ctk.CTkEntry(grid_f, width=80)
        self.entry_cal_offset_y.grid(row=0, column=3, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(grid_f, text="X Scale (mult):").grid(row=1, column=0, padx=6, pady=4, sticky="w")
        self.entry_cal_scale_x = ctk.CTkEntry(grid_f, width=80)
        self.entry_cal_scale_x.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(grid_f, text="Y Scale (mult):").grid(row=1, column=2, padx=6, pady=4, sticky="w")
        self.entry_cal_scale_y = ctk.CTkEntry(grid_f, width=80)
        self.entry_cal_scale_y.grid(row=1, column=3, padx=6, pady=4, sticky="w")

        # Action Buttons
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=6)

        self.btn_run_cal = ctk.CTkButton(
            btn_row,
            text="🎯 Test Visual Target Alignment",
            fg_color="#059669",
            hover_color="#047857",
            command=self._run_calibration_test
        )
        self.btn_run_cal.pack(side="left", padx=(0, 8))

        self.btn_reset_cal = ctk.CTkButton(
            btn_row,
            text="Reset to Zero Offsets",
            fg_color="#4b5563",
            hover_color="#374151",
            command=self._reset_calibration_defaults
        )
        self.btn_reset_cal.pack(side="left")

    def _run_calibration_test(self):
        """Displays test target markers on screen to verify alignment."""
        try:
            import pyautogui
            import ctypes
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            cx = w // 2
            cy = h // 2

            # Parse current offsets from entries
            try:
                ox = int(self.entry_cal_offset_x.get().strip() or "0")
                oy = int(self.entry_cal_offset_y.get().strip() or "0")
            except Exception:
                ox, oy = 0, 0

            test_target_x = cx + ox
            test_target_y = cy + oy

            # Move mouse to the calibrated center target
            pyautogui.moveTo(test_target_x, test_target_y, duration=0.4)
            messagebox.showinfo(
                "Calibration Test",
                f"Moved mouse cursor to screen center:\n"
                f"Target: ({test_target_x}, {test_target_y}) on {w}×{h} display.\n\n"
                f"If the cursor is slightly off from your desired center, adjust X/Y offset values and re-test."
            )
        except Exception as e:
            messagebox.showwarning("Calibration Test", f"Could not perform test movement: {e}")

    def _reset_calibration_defaults(self):
        self.entry_cal_offset_x.delete(0, "end")
        self.entry_cal_offset_x.insert(0, "0")
        self.entry_cal_offset_y.delete(0, "end")
        self.entry_cal_offset_y.insert(0, "0")
        self.entry_cal_scale_x.delete(0, "end")
        self.entry_cal_scale_x.insert(0, "1.0")
        self.entry_cal_scale_y.delete(0, "end")
        self.entry_cal_scale_y.insert(0, "1.0")
        messagebox.showinfo("Reset", "Calibration offsets reset to zero.")

    # --- TAB 5: HOTKEYS ---
    def _build_keys_tab(self):
        f = self.tab_keys

        ctk.CTkLabel(
            f,
            text="Global Keybinds (active system-wide even when other apps are focused):",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=16, pady=(16, 8))

        keys_frame = ctk.CTkFrame(f, fg_color="transparent")
        keys_frame.pack(fill="x", padx=16, pady=4)

        hotkey_labels = [
            ("trigger_solve", "Capture & Solve Problem:"),
            ("snip_solve", "Snip Box & Solve:"),
            ("confirm_action", "Confirm & Execute Solution:"),
            ("next_question", "Go To Next Question:"),
            ("pause_resume", "Pause / Resume Assistant:"),
            ("emergency_stop", "EMERGENCY KILLSWITCH:"),
            ("toggle_overlay", "Show / Hide Overlay:"),
            ("close_app", "Close Application:"),
        ]

        for i, (key_id, label_text) in enumerate(hotkey_labels):
            ctk.CTkLabel(keys_frame, text=label_text).grid(row=i, column=0, sticky="w", padx=8, pady=6)
            ent = ctk.CTkEntry(keys_frame, width=120)
            ent.grid(row=i, column=1, sticky="w", padx=8, pady=6)
            self.hotkey_entries[key_id] = ent

    # --- TAB 5: DEBUG & LOGGING ---
    def _build_debug_tab(self):
        f = self.tab_debug

        # Debug mode switch
        self.switch_debug_mode = ctk.CTkSwitch(
            f,
            text="Enable Verbose Debug Mode",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_debug_mode.pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(
            f,
            text="Enables detailed DEBUG log levels, inline stack traces on the HUD upon failure,\n"
                 "and full API payload logging.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=46, pady=(0, 12))

        # Log to file switch
        self.switch_log_file = ctk.CTkSwitch(
            f,
            text="Enable Persistent File Logging (logs/ava_assistant.log)",
            font=ctk.CTkFont(weight="bold")
        )
        self.switch_log_file.pack(anchor="w", padx=16, pady=(4, 4))
        ctk.CTkLabel(
            f,
            text="Saves rotating log files to disk for troubleshooting and post-session analysis.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            justify="left"
        ).pack(anchor="w", padx=46, pady=(0, 12))

        # Log level selector
        level_frame = ctk.CTkFrame(f, fg_color="transparent")
        level_frame.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(level_frame, text="Default Log Level:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 12))
        self.combo_log_level = ctk.CTkComboBox(
            level_frame,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            width=140
        )
        self.combo_log_level.pack(side="left")

        # In-memory buffer size slider
        buf_frame = ctk.CTkFrame(f, fg_color="transparent")
        buf_frame.pack(fill="x", padx=16, pady=(4, 16))
        self.lbl_buffer_size = ctk.CTkLabel(buf_frame, text="In-Memory Log Buffer Size: 500 records")
        self.lbl_buffer_size.pack(anchor="w")
        self.slider_buffer_size = ctk.CTkSlider(
            buf_frame,
            from_=100,
            to=2000,
            number_of_steps=19,
            command=lambda v: self.lbl_buffer_size.configure(text=f"In-Memory Log Buffer Size: {int(v)} records")
        )
        self.slider_buffer_size.pack(fill="x", pady=4)

        # Action buttons card
        action_box = ctk.CTkFrame(f, fg_color="#18181b", corner_radius=8)
        action_box.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            action_box,
            text="Debug Console & Log Maintenance:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 6))

        btn_row = ctk.CTkFrame(action_box, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="🐞 Open Debug Console",
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._open_debug_console
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="📁 Open Logs Folder",
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._open_logs_folder
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row,
            text="🧹 Clear Log File",
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self._clear_saved_log_file
        ).pack(side="right", padx=(8, 0))

    def _open_debug_console(self):
        DebugWindow(master=self)

    def _open_logs_folder(self):
        folder = get_log_directory()
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            messagebox.showinfo("Logs Directory", f"Logs path:\n{folder}")

    def _clear_saved_log_file(self):
        if messagebox.askyesno("Clear Logs", "Do you want to reset the disk log file (ava_assistant.log)?"):
            if clear_log_file():
                messagebox.showinfo("Success", "Log file cleared successfully.")
            else:
                messagebox.showerror("Error", "Could not clear log file.")

    # --- Load & Save ---
    def _load_values(self):
        cfg = self.config
        self.current_provider = (cfg.ai_provider or "gemini").lower()
        self.provider_keys = {
            "gemini": cfg.get_api_key_for_provider("gemini"),
            "openai": cfg.get_api_key_for_provider("openai"),
            "anthropic": cfg.get_api_key_for_provider("anthropic"),
            "custom": cfg.get_api_key_for_provider("custom"),
        }
        self.combo_provider.set(cfg.ai_provider)
        self._on_provider_changed(cfg.ai_provider, preserve_model=True)
        if cfg.model_name:
            self.combo_model.set(cfg.model_name)
        elif AVAILABLE_MODELS.get(cfg.ai_provider.lower()):
            self.combo_model.set(AVAILABLE_MODELS[cfg.ai_provider.lower()][0])

        active_key = self.provider_keys.get(self.current_provider, "") or cfg.api_key or ""
        self.entry_api_key.delete(0, "end")
        self.entry_api_key.insert(0, active_key)
        self.entry_custom_url.delete(0, "end")
        self.entry_custom_url.insert(0, cfg.custom_api_base or "")

        if cfg.autonomous_mode:
            self.switch_autonomous.select()
        else:
            self.switch_autonomous.deselect()

        if cfg.auto_next:
            self.switch_auto_next.select()
        else:
            self.switch_auto_next.deselect()

        self.slider_next_delay.set(cfg.auto_next_delay)
        self.lbl_next_delay.configure(text=f"Delay before clicking Next: {cfg.auto_next_delay:.1f}s")

        if cfg.humanize_mouse:
            self.switch_humanize.select()
        else:
            self.switch_humanize.deselect()

        self.slider_mouse_speed.set(cfg.mouse_speed)
        self.lbl_mouse_speed.configure(text=f"Mouse Movement Pace: {cfg.mouse_speed:.2f}s")

        if getattr(cfg, "chain_multi_parts", True):
            self.switch_chain_multi_parts.select()
        else:
            self.switch_chain_multi_parts.deselect()

        if getattr(cfg, "reading_delay_enabled", True):
            self.switch_reading_delay.select()
        else:
            self.switch_reading_delay.deselect()

        base_read = getattr(cfg, "base_reading_time", 4.0)
        self.slider_base_reading.set(base_read)
        self.lbl_base_reading.configure(text=f"Base Reading Pause: {base_read:.1f}s (Skip anytime with F9)")

        if getattr(cfg, "click_variance_enabled", True):
            self.switch_click_variance.select()
        else:
            self.switch_click_variance.deselect()

        if getattr(cfg, "smart_typos_enabled", True):
            self.switch_smart_typos.select()
        else:
            self.switch_smart_typos.deselect()

        if getattr(cfg, "local_verification_enabled", True):
            self.switch_local_verification.select()
        else:
            self.switch_local_verification.deselect()

        if cfg.anti_capture_enabled:
            self.switch_anti_capture.select()
        else:
            self.switch_anti_capture.deselect()

        self.slider_opacity.set(cfg.overlay_opacity)
        self.lbl_opacity.configure(text=f"HUD Opacity: {int(cfg.overlay_opacity * 100)}%")

        for key_id, ent in self.hotkey_entries.items():
            ent.delete(0, "end")
            ent.insert(0, cfg.hotkeys.get(key_id, ""))

        # Load debug preferences
        if getattr(cfg, "debug_mode", False):
            self.switch_debug_mode.select()
        else:
            self.switch_debug_mode.deselect()

        if getattr(cfg, "log_to_file", True):
            self.switch_log_file.select()
        else:
            self.switch_log_file.deselect()

        self.combo_log_level.set(getattr(cfg, "log_level", "INFO"))
        buf_size = getattr(cfg, "max_log_entries", 500)
        self.slider_buffer_size.set(buf_size)
        self.lbl_buffer_size.configure(text=f"In-Memory Log Buffer Size: {int(buf_size)} records")

        # Load display & calibration preferences
        max_dim = getattr(cfg, "max_capture_dimension", 1920)
        if max_dim == 0:
            self.combo_capture_res.set("Native / Unscaled (Full Workstation Resolution)")
        elif max_dim == 2560:
            self.combo_capture_res.set("2560p (High Quality Detail)")
        else:
            self.combo_capture_res.set("1920p (Fast / Balanced - Recommended)")

        cm = getattr(cfg, "coordinate_mode", "normalized_1000")
        if cm == "raw_pixels":
            self.combo_coord_mode.set("Raw Pixels (Legacy)")
        elif cm == "auto":
            self.combo_coord_mode.set("Auto-Detect (Adaptive)")
        else:
            self.combo_coord_mode.set("Normalized [0-1000] (Pinpoint Accuracy for Gemini & Claude)")

        self.entry_cal_offset_x.delete(0, "end")
        self.entry_cal_offset_x.insert(0, str(getattr(cfg, "calibration_offset_x", 0)))
        self.entry_cal_offset_y.delete(0, "end")
        self.entry_cal_offset_y.insert(0, str(getattr(cfg, "calibration_offset_y", 0)))
        self.entry_cal_scale_x.delete(0, "end")
        self.entry_cal_scale_x.insert(0, str(getattr(cfg, "calibration_scale_x", 1.0)))
        self.entry_cal_scale_y.delete(0, "end")
        self.entry_cal_scale_y.insert(0, str(getattr(cfg, "calibration_scale_y", 1.0)))

    def _save_and_close(self):
        merged_hotkeys = dict(self.config.hotkeys)
        for key_id, ent in self.hotkey_entries.items():
            val = ent.get().strip()
            if val:
                merged_hotkeys[key_id] = val

        # Fallback model name if left blank
        model_val = self.combo_model.get().strip()
        provider_val = self.combo_provider.get().strip().lower()
        if not model_val:
            model_val = AVAILABLE_MODELS.get(provider_val, ["gemini-3.6-flash"])[0]

        # Parse capture resolution
        res_str = self.combo_capture_res.get()
        if "Native" in res_str:
            max_dim = 0
        elif "2560p" in res_str:
            max_dim = 2560
        else:
            max_dim = 1920

        # Parse coordinate mode
        mode_str = self.combo_coord_mode.get()
        if "Raw" in mode_str:
            coord_mode = "raw_pixels"
        elif "Auto" in mode_str:
            coord_mode = "auto"
        else:
            coord_mode = "normalized_1000"

        try:
            cal_ox = int(self.entry_cal_offset_x.get().strip() or "0")
        except ValueError:
            cal_ox = 0

        try:
            cal_oy = int(self.entry_cal_offset_y.get().strip() or "0")
        except ValueError:
            cal_oy = 0

        try:
            cal_sx = float(self.entry_cal_scale_x.get().strip() or "1.0")
        except ValueError:
            cal_sx = 1.0

        try:
            cal_sy = float(self.entry_cal_scale_y.get().strip() or "1.0")
        except ValueError:
            cal_sy = 1.0

        current_typed_key = self.entry_api_key.get().strip()
        if hasattr(self, "provider_keys"):
            self.provider_keys[provider_val] = current_typed_key
        else:
            self.provider_keys = {provider_val: current_typed_key}

        self.config_manager.update(
            ai_provider=provider_val,
            model_name=model_val,
            api_key=current_typed_key,
            gemini_api_key=self.provider_keys.get("gemini", ""),
            openai_api_key=self.provider_keys.get("openai", ""),
            anthropic_api_key=self.provider_keys.get("anthropic", ""),
            custom_api_key=self.provider_keys.get("custom", ""),
            custom_api_base=self.entry_custom_url.get().strip(),
            autonomous_mode=bool(self.switch_autonomous.get()),
            auto_next=bool(self.switch_auto_next.get()),
            auto_next_delay=float(self.slider_next_delay.get()),
            chain_multi_parts=bool(self.switch_chain_multi_parts.get()),
            reading_delay_enabled=bool(self.switch_reading_delay.get()),
            base_reading_time=float(self.slider_base_reading.get()),
            click_variance_enabled=bool(self.switch_click_variance.get()),
            smart_typos_enabled=bool(self.switch_smart_typos.get()),
            local_verification_enabled=bool(self.switch_local_verification.get()),
            humanize_mouse=bool(self.switch_humanize.get()),
            mouse_speed=float(self.slider_mouse_speed.get()),
            anti_capture_enabled=bool(self.switch_anti_capture.get()),
            overlay_opacity=float(self.slider_opacity.get()),
            debug_mode=bool(self.switch_debug_mode.get()),
            log_to_file=bool(self.switch_log_file.get()),
            log_level=self.combo_log_level.get(),
            max_log_entries=int(self.slider_buffer_size.get()),
            max_capture_dimension=max_dim,
            coordinate_mode=coord_mode,
            calibration_offset_x=cal_ox,
            calibration_offset_y=cal_oy,
            calibration_scale_x=cal_sx,
            calibration_scale_y=cal_sy,
            hotkeys=merged_hotkeys
        )

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
