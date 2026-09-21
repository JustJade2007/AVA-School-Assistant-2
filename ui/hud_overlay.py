"""
Anti-Capture HUD Overlay for AVA School Assistant 2.
Stays always-on-top, displays live assistant status, questions, answers,
action buttons with hotkey tags, and uses Windows SetWindowDisplayAffinity
to remain completely hidden from screen sharing and recording tools.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from typing import Optional, Dict, Any, Callable

from core.cloaking import apply_anti_capture, is_anti_capture_supported
from core.assistant_engine import AssistantEngine, EngineState
from config import AppConfig, ConfigManager
from ui.visualizer import CloakedVisualizer
from ui.asset_loader import apply_window_icon, get_logo_ctk_image


class HUDOverlay(ctk.CTkToplevel):
    """Floating, cloaked HUD overlay with autonomous controls."""

    def __init__(
        self,
        master,
        engine: AssistantEngine,
        on_open_settings: Optional[Callable[[], None]] = None,
        on_close_app: Optional[Callable[[], None]] = None,
        on_snip_solve: Optional[Callable[[], None]] = None,
        on_open_playground: Optional[Callable[[], None]] = None
    ):
        super().__init__(master)
        self.engine = engine
        self.on_open_settings = on_open_settings
        self.on_close_app = on_close_app
        self.on_snip_solve = on_snip_solve
        self.on_open_playground = on_open_playground
        self.config_manager = engine.config_manager
        self.visualizer = CloakedVisualizer(master=self)

        # Window state
        self.is_collapsed = False
        self.is_hidden = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self.debug_window = None

        self._setup_window()
        self._build_ui()
        self._register_engine_callbacks()

        # Apply Cloaking to ensure invisibility to screen readers/recorders
        self.after(200, self.apply_cloak)

    @property
    def config(self) -> AppConfig:
        return self.config_manager.config

    def _setup_window(self):
        self.title("AVA_HUD_Cloaked")
        apply_window_icon(self)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", self.config.overlay_opacity)

        from ui.window_utils import ensure_taskbar_presence, attach_minimize_restore_handlers
        self.after(50, lambda: ensure_taskbar_presence(self))
        attach_minimize_restore_handlers(
            self,
            is_cloaked_getter=lambda: self.config.anti_capture_enabled,
            on_restore=lambda: (self.attributes("-topmost", True), self.apply_cloak())
        )

        # Position on screen (width supports generous room for header controls)
        x = max(10, self.config.overlay_x)
        y = max(10, self.config.overlay_y)
        w = max(480, getattr(self.config, "overlay_width", 490))
        self.geometry(f"{w}x320+{x}+{y}")
        self.configure(fg_color="#18181b")

        # Draggable window bindings
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)
        self.bind("<ButtonRelease-1>", self._on_drag_release)

    def apply_cloak(self):
        """Applies Win32 WDA_EXCLUDEFROMCAPTURE affinity."""
        success = apply_anti_capture(self, enable=self.config.anti_capture_enabled)
        if hasattr(self, "cloak_badge"):
            if success and self.config.anti_capture_enabled:
                self.cloak_badge.configure(text="🛡️ CLOAK", text_color="#10b981", fg_color="#064e3b")
            else:
                self.cloak_badge.configure(text="⚠️ UNCLOAK", text_color="#f59e0b", fg_color="#451a03")

    def _build_ui(self):
        # Outer border frame
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color="#18181b",
            corner_radius=12,
            border_width=2,
            border_color="#3b82f6"
        )
        self.main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # --- Top Header Bar ---
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="#27272a", corner_radius=8, height=36)
        self.header_frame.pack(fill="x", padx=6, pady=6)
        self.header_frame.bind("<Control-MouseWheel>", self._on_header_mousewheel)

        # Drag handle / Logo (compact text so action buttons have ample room)
        self.logo_img = get_logo_ctk_image(size=(18, 18))
        if self.logo_img:
            self.logo_icon_lbl = ctk.CTkLabel(self.header_frame, text="", image=self.logo_img)
            self.logo_icon_lbl.pack(side="left", padx=(6, 2))
            self.logo_icon_lbl.bind("<Control-MouseWheel>", self._on_header_mousewheel)

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="AVA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#60a5fa"
        )
        self.title_label.pack(side="left", padx=(4, 4))
        self.title_label.bind("<Control-MouseWheel>", self._on_header_mousewheel)

        # Cloak Status indicator (compact badge)
        self.cloak_badge = ctk.CTkLabel(
            self.header_frame,
            text="🛡️ CLOAK",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#10b981",
            fg_color="#064e3b",
            corner_radius=4,
            padx=5,
            pady=1
        )
        self.cloak_badge.pack(side="left", padx=2)

        # Debug Mode badge (visible when debug mode is enabled)
        self.debug_badge = ctk.CTkLabel(
            self.header_frame,
            text="🐞",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#38bdf8",
            fg_color="#0c4a6e",
            corner_radius=4,
            padx=4,
            pady=1
        )
        if self.config.debug_mode:
            self.debug_badge.pack(side="left", padx=2)

        # Dedicated right container for compact, circular action buttons
        self.header_actions_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_actions_frame.pack(side="right", padx=(0, 4), pady=2)
        self.header_actions_frame.bind("<Control-MouseWheel>", self._on_header_mousewheel)

        # Calculate initial button dimensions from configurable icon size
        self.icon_size = getattr(self.config, "header_icon_size", 11)
        btn_wh = self.icon_size + 11
        corner_rad = btn_wh // 2
        btn_font = ctk.CTkFont(size=self.icon_size)

        # 1. Close button (circular, rightmost)
        self.btn_close = ctk.CTkButton(
            self.header_actions_frame,
            text="✕",
            width=btn_wh,
            height=btn_wh,
            corner_radius=corner_rad,
            font=btn_font,
            fg_color="#3f3f46",
            hover_color="#ef4444",
            text_color="#fecdd3",
            command=self._handle_close
        )
        self.btn_close.pack(side="right", padx=1)

        # 2. Minimize button (circular)
        self.btn_hide = ctk.CTkButton(
            self.header_actions_frame,
            text="—",
            width=btn_wh,
            height=btn_wh,
            corner_radius=corner_rad,
            font=btn_font,
            fg_color="#3f3f46",
            hover_color="#52525b",
            text_color="#e4e4e7",
            command=self.minimize_overlay
        )
        self.btn_hide.pack(side="right", padx=1)

        # 3. Collapse button (circular)
        self.btn_collapse = ctk.CTkButton(
            self.header_actions_frame,
            text="▲",
            width=btn_wh,
            height=btn_wh,
            corner_radius=corner_rad,
            font=btn_font,
            fg_color="#3f3f46",
            hover_color="#52525b",
            text_color="#e4e4e7",
            command=self.toggle_collapse
        )
        self.btn_collapse.pack(side="right", padx=1)

        # 4. Settings button (circular)
        if self.on_open_settings:
            self.btn_settings = ctk.CTkButton(
                self.header_actions_frame,
                text="⚙",
                width=btn_wh,
                height=btn_wh,
                corner_radius=corner_rad,
                font=btn_font,
                fg_color="#3f3f46",
                hover_color="#2563eb",
                text_color="#bfdbfe",
                command=self.on_open_settings
            )
            self.btn_settings.pack(side="right", padx=1)

        # 5. Debug Console button (circular)
        self.btn_debug = ctk.CTkButton(
            self.header_actions_frame,
            text="🐞",
            width=btn_wh,
            height=btn_wh,
            corner_radius=corner_rad,
            font=btn_font,
            fg_color="#3f3f46",
            hover_color="#52525b",
            text_color="#7dd3fc",
            command=self.open_debug_window
        )
        self.btn_debug.pack(side="right", padx=1)

        # 6. Quick Snip Tool (cutout button) - SMALLER & sleek circular accent
        snip_wh = max(18, btn_wh - 4)
        snip_corner = snip_wh // 2
        snip_font = ctk.CTkFont(size=max(8, self.icon_size - 2))

        if self.on_snip_solve:
            self.btn_snip = ctk.CTkButton(
                self.header_actions_frame,
                text="✂️",
                width=snip_wh,
                height=snip_wh,
                corner_radius=snip_corner,
                font=snip_font,
                fg_color="#0369a1",
                hover_color="#0284c7",
                text_color="#f0f9ff",
                command=self.on_snip_solve
            )
            self.btn_snip.pack(side="right", padx=1)

        # 7. Playground Studio button (F3, circular)
        if self.on_open_playground:
            self.btn_playground = ctk.CTkButton(
                self.header_actions_frame,
                text="📝",
                width=btn_wh,
                height=btn_wh,
                corner_radius=corner_rad,
                font=btn_font,
                fg_color="#312e81",
                hover_color="#4338ca",
                text_color="#c7d2fe",
                command=self.on_open_playground
            )
            self.btn_playground.pack(side="right", padx=1)

        # --- Status Banner ---
        self.status_frame = ctk.CTkFrame(self.main_frame, fg_color="#1f2937", corner_radius=6, height=28)
        self.status_frame.pack(fill="x", padx=8, pady=(0, 6))

        self.status_dot = ctk.CTkLabel(self.status_frame, text="●", text_color="#10b981", font=ctk.CTkFont(size=14))
        self.status_dot.pack(side="left", padx=(8, 4))

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready (Idle)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#f3f4f6"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        # Quick Error Details Button (hidden by default, shown on error)
        self.btn_status_details = ctk.CTkButton(
            self.status_frame,
            text="[Details]",
            width=58,
            height=20,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=lambda: self.open_debug_window(open_error_tab=True)
        )

        self.mode_badge = ctk.CTkLabel(
            self.status_frame,
            text="REVIEW MODE" if not self.config.autonomous_mode else "AUTO MODE",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#93c5fd"
        )
        self.mode_badge.pack(side="right", padx=8)

        # --- Expandable Content Area ---
        self.content_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True, padx=8, pady=2)

        # Question / Answer card
        self.qa_card = ctk.CTkScrollableFrame(self.content_container, fg_color="#27272a", corner_radius=8, height=130)
        self.qa_card.pack(fill="both", expand=True, pady=(0, 6))

        self.lbl_question = ctk.CTkLabel(
            self.qa_card,
            text="Question will appear here upon scan.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#e4e4e7",
            wraplength=410,
            justify="left"
        )
        self.lbl_question.pack(anchor="w", padx=6, pady=(4, 2))

        self.lbl_answer = ctk.CTkLabel(
            self.qa_card,
            text="Solution: Awaiting trigger (F8)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8",
            wraplength=410,
            justify="left"
        )
        self.lbl_answer.pack(anchor="w", padx=6, pady=(2, 4))

        # Platform Evaluation Status Frame & Badges (shown between question & answer)
        self.eval_status_frame = ctk.CTkFrame(self.qa_card, fg_color="transparent")
        self.lbl_eval_badge = ctk.CTkLabel(
            self.eval_status_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            corner_radius=4,
            padx=6,
            pady=1
        )
        self.lbl_eval_platform_feedback = ctk.CTkLabel(
            self.eval_status_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#fca5a5",
            wraplength=260,
            justify="left"
        )

        # Rethink Strategy Frame (shown prominently if question was marked incorrect)
        self.rethink_frame = ctk.CTkFrame(self.qa_card, fg_color="#450a0a", corner_radius=6, border_width=1, border_color="#ef4444")
        self.lbl_rethink_title = ctk.CTkLabel(
            self.rethink_frame,
            text="🔄 RETHINKING INCORRECT ANSWER",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#f87171"
        )
        self.lbl_rethink_title.pack(anchor="w", padx=6, pady=(3, 1))
        self.lbl_rethink_text = ctk.CTkLabel(
            self.rethink_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#fecaca",
            wraplength=400,
            justify="left"
        )
        self.lbl_rethink_text.pack(anchor="w", padx=6, pady=(0, 4))

        # Container for multi-part items / sub-question pills
        self.items_container = ctk.CTkFrame(self.qa_card, fg_color="transparent")

        # Written Question Preview & Live Editor Panel (AVA 2.0)
        self.written_card = ctk.CTkFrame(
            self.qa_card,
            fg_color="#0f172a",
            corner_radius=8,
            border_width=1,
            border_color="#38bdf8"
        )
        self.written_header_frame = ctk.CTkFrame(self.written_card, fg_color="transparent")
        self.written_header_frame.pack(fill="x", padx=6, pady=(4, 2))

        self.lbl_written_title = ctk.CTkLabel(
            self.written_header_frame,
            text="✍️ WRITTEN DRAFT (GEMINI 3.8 FLASH)",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_written_title.pack(side="left")

        self.lbl_written_badge = ctk.CTkLabel(
            self.written_header_frame,
            text="0 words",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            fg_color="#0284c7",
            text_color="#ffffff",
            corner_radius=4,
            padx=6,
            pady=1
        )
        self.lbl_written_badge.pack(side="right")

        self.lbl_humanizer_badge = ctk.CTkLabel(
            self.written_header_frame,
            text="Jade's Humanizer",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            fg_color="#064e3b",
            text_color="#34d399",
            corner_radius=4,
            padx=5,
            pady=1
        )
        self.lbl_humanizer_badge.pack(side="right", padx=(0, 4))

        # Editable Text Box
        self.txt_written_edit = ctk.CTkTextbox(
            self.written_card,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#f8fafc",
            fg_color="#1e293b",
            height=85,
            wrap="word",
            border_width=1,
            border_color="#334155"
        )
        self.txt_written_edit.pack(fill="x", padx=6, pady=4)
        self.txt_written_edit.bind("<KeyRelease>", self._on_written_text_edited)

        # Editor footer actions
        self.written_footer_frame = ctk.CTkFrame(self.written_card, fg_color="transparent")
        self.written_footer_frame.pack(fill="x", padx=6, pady=(0, 4))

        self.lbl_written_hint = ctk.CTkLabel(
            self.written_footer_frame,
            text="✏️ Edit text above if needed, then press F9 to type.",
            font=ctk.CTkFont(size=9),
            text_color="#94a3b8"
        )
        self.lbl_written_hint.pack(side="left")

        self.btn_rehumanize = ctk.CTkButton(
            self.written_footer_frame,
            text="✨ Re-Humanize",
            font=ctk.CTkFont(size=9),
            fg_color="#1e293b",
            hover_color="#334155",
            height=22,
            command=self._rehumanize_written_draft
        )
        self.btn_rehumanize.pack(side="right")

        self.lbl_reasoning = ctk.CTkLabel(
            self.qa_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#9ca3af",
            wraplength=410,
            justify="left"
        )
        self.lbl_reasoning.pack(anchor="w", padx=6, pady=(0, 4))

        # Error diagnostic actions frame (shown only when in EngineState.ERROR)
        self.error_actions_frame = ctk.CTkFrame(self.qa_card, fg_color="#18181b", corner_radius=6)

        self.btn_inspect_full_error = ctk.CTkButton(
            self.error_actions_frame,
            text="🔍 Full Diagnostic & Logs",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=26,
            command=lambda: self.open_debug_window(open_error_tab=True)
        )
        self.btn_inspect_full_error.pack(side="left", padx=4, pady=4)

        self.btn_copy_quick_error = ctk.CTkButton(
            self.error_actions_frame,
            text="📋 Copy Error",
            font=ctk.CTkFont(size=10),
            fg_color="#374151",
            hover_color="#4b5563",
            height=26,
            command=self._copy_current_error_report
        )
        self.btn_copy_quick_error.pack(side="left", padx=4, pady=4)

        self.btn_retry_error = ctk.CTkButton(
            self.error_actions_frame,
            text="🔄 Retry (F8)",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=26,
            command=self.engine.trigger_solve
        )
        self.btn_retry_error.pack(side="left", padx=4, pady=4)

        # --- Interactive Controls & Keybind Buttons ---
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=6, pady=(0, 6))

        hk = self.config.hotkeys
        hk_solve = hk.get("trigger_solve", "F8")
        hk_confirm = hk.get("confirm_action", "F9")
        hk_next = hk.get("next_question", "F10")
        hk_pause = hk.get("pause_resume", "F7")
        hk_stop = hk.get("emergency_stop", "F12")

        # Row 1 of controls
        self.btn_solve = ctk.CTkButton(
            self.btn_frame,
            text=f"▶ Solve ({hk_solve})",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=30,
            command=self.engine.trigger_solve
        )
        self.btn_solve.grid(row=0, column=0, padx=3, pady=3, sticky="ew")

        self.btn_confirm = ctk.CTkButton(
            self.btn_frame,
            text=f"✓ Confirm ({hk_confirm})",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=30,
            command=self.engine.confirm_and_execute
        )
        self.btn_confirm.grid(row=0, column=1, padx=3, pady=3, sticky="ew")

        self.btn_next = ctk.CTkButton(
            self.btn_frame,
            text=f"⏭ Next ({hk_next})",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            height=30,
            command=self.engine.trigger_next_question
        )
        self.btn_next.grid(row=0, column=2, padx=3, pady=3, sticky="ew")

        # Row 2 of controls
        self.btn_pause = ctk.CTkButton(
            self.btn_frame,
            text=f"⏸ Pause ({hk_pause})",
            font=ctk.CTkFont(size=11),
            fg_color="#4b5563",
            hover_color="#374151",
            height=28,
            command=self.engine.pause_resume
        )
        self.btn_pause.grid(row=1, column=0, padx=3, pady=3, sticky="ew")

        self.btn_stop = ctk.CTkButton(
            self.btn_frame,
            text=f"⏹ Killswitch ({hk_stop})",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            height=28,
            command=self.engine.emergency_stop
        )
        self.btn_stop.grid(row=1, column=1, padx=3, pady=3, sticky="ew")

        self.btn_test_cloak = ctk.CTkButton(
            self.btn_frame,
            text="👁 Verify Cloak",
            font=ctk.CTkFont(size=10),
            fg_color="#374151",
            hover_color="#4b5563",
            height=28,
            command=self._test_cloak_visibility
        )
        self.btn_test_cloak.grid(row=1, column=2, padx=3, pady=3, sticky="ew")

        # Row 3 of controls: Viewport scrolling for long questions
        self.btn_scroll_down = ctk.CTkButton(
            self.btn_frame,
            text="📜 Scroll Down",
            font=ctk.CTkFont(size=10),
            fg_color="#1e293b",
            hover_color="#334155",
            height=26,
            command=self._manual_scroll_down
        )
        self.btn_scroll_down.grid(row=2, column=0, padx=3, pady=2, sticky="ew")

        self.btn_scroll_up = ctk.CTkButton(
            self.btn_frame,
            text="📜 Scroll Up",
            font=ctk.CTkFont(size=10),
            fg_color="#1e293b",
            hover_color="#334155",
            height=26,
            command=self._manual_scroll_up
        )
        self.btn_scroll_up.grid(row=2, column=1, padx=3, pady=2, sticky="ew")

        self.btn_inspect_whole = ctk.CTkButton(
            self.btn_frame,
            text="🔍 Inspect Whole Q",
            font=ctk.CTkFont(size=10),
            fg_color="#0f766e",
            hover_color="#115e59",
            height=26,
            command=self._manual_inspect_whole_question
        )
        self.btn_inspect_whole.grid(row=2, column=2, padx=3, pady=2, sticky="ew")

        # Row 3 of controls: Playground Mode launcher
        if self.on_open_playground:
            self.btn_playground_launch = ctk.CTkButton(
                self.btn_frame,
                text="📝 Launch Playground Mode (F3)",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#312e81",
                hover_color="#4338ca",
                height=26,
                command=self.on_open_playground
            )
            self.btn_playground_launch.grid(row=3, column=0, columnspan=3, padx=3, pady=(3, 2), sticky="ew")

        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)
        self.btn_frame.grid_columnconfigure(2, weight=1)

    def _register_engine_callbacks(self):
        self.engine.add_state_listener(self._on_engine_state_change)
        self.engine.add_result_listener(self._on_engine_result)
        self.engine.add_error_listener(self._on_engine_error)
        self.engine.add_adjustment_listener(self._on_engine_adjustment)

    def _on_engine_adjustment(self, message: str):
        self.after(0, lambda: self._show_adjustment_toast(message))

    def _show_adjustment_toast(self, message: str):
        prev_text = self.status_label.cget("text")
        self.status_label.configure(text=message, text_color="#38bdf8")
        # Revert back after 2.5s if status hasn't transitioned
        self.after(2500, lambda: self._restore_status_text(message, prev_text))

    def _restore_status_text(self, expected_toast: str, fallback_text: str):
        if self.status_label.cget("text") == expected_toast:
            self.status_label.configure(text=fallback_text, text_color="#f3f4f6")

    def _on_engine_error(self, diag):
        self.after(0, lambda: self._render_error_card(diag.message))

    def _on_engine_state_change(self, state: EngineState, detail: str):
        # Update thread-safely via Tkinter after
        self.after(0, lambda: self._update_state_ui(state, detail))

    def _update_state_ui(self, state: EngineState, detail: str):
        colors = {
            EngineState.IDLE: ("●", "#10b981", "Ready (Idle)"),
            EngineState.SCANNING: ("●", "#38bdf8", "Scanning Screen..."),
            EngineState.THINKING: ("●", "#a855f7", "Thinking (AI Solving)..."),
            EngineState.READING: ("●", "#38bdf8", f"Reading Question... {f'({detail})' if detail else ''}"),
            EngineState.WAITING_CONFIRMATION: ("●", "#f59e0b", "Solved - Press F9 to Confirm"),
            EngineState.EXECUTING: ("●", "#3b82f6", "Executing Actions..."),
            EngineState.VERIFYING: ("●", "#06b6d4", "Verifying Answer (Zero-Token)..."),
            EngineState.INSPECTING: ("●", "#ec4899", f"Inspecting Material... {f'({detail})' if detail else ''}"),
            EngineState.NAVIGATING: ("●", "#8b5cf6", "Navigating to Next..."),
            EngineState.PAUSED: ("■", "#ef4444", f"Paused {f'({detail})' if detail else ''}")
        }

        is_unverified = (state == EngineState.WAITING_CONFIRMATION and detail.startswith("UNVERIFIED"))

        if state == EngineState.ERROR:
            clean_first_line = detail.split("\n")[0].strip() if detail else "Unknown Error"
            short_msg = clean_first_line if len(clean_first_line) <= 38 else clean_first_line[:35] + "..."
            text = f"Error: {short_msg}"
            self.status_dot.configure(text="✖", text_color="#ef4444")
            self.status_label.configure(text=text, text_color="#f3f4f6")
            self.btn_status_details.pack(side="right", padx=4)
            self._render_error_card(detail)
        elif is_unverified:
            self.status_dot.configure(text="⚠️", text_color="#f59e0b")
            self.status_label.configure(text="⚠️ Action Missed: Question Not Answered!", text_color="#fde047")
            self.btn_status_details.pack_forget()
        else:
            dot, color, text = colors.get(state, ("●", "#9ca3af", state.value))
            self.status_dot.configure(text=dot, text_color=color)
            self.status_label.configure(text=text, text_color="#f3f4f6")
            self.btn_status_details.pack_forget()
            if state != EngineState.IDLE or not self.engine.error_message:
                self.error_actions_frame.pack_forget()

        # Update confirm button label & styling based on state
        hk_confirm = self.config.hotkeys.get("confirm_action", "F9")
        if is_unverified:
            self.btn_confirm.configure(
                text=f"🔄 Retry Answer ({hk_confirm})",
                fg_color="#d97706",
                hover_color="#b45309",
                border_width=2,
                border_color="#fbbf24"
            )
        elif state == EngineState.READING:
            self.btn_confirm.configure(text=f"✓ Skip Wait ({hk_confirm})", fg_color="#0284c7", border_width=2, border_color="#38bdf8")
        elif state == EngineState.WAITING_CONFIRMATION:
            self.btn_confirm.configure(text=f"✓ Confirm ({hk_confirm})", fg_color="#10b981", border_width=2, border_color="#ffffff")
        elif state == EngineState.VERIFYING:
            self.btn_confirm.configure(text="🔍 Verifying...", fg_color="#0891b2", border_width=0)
        else:
            self.btn_confirm.configure(text=f"✓ Confirm ({hk_confirm})", fg_color="#059669", border_width=0)

    def _render_error_card(self, detail: str):
        """Displays rich error diagnostics inside the Q&A card for debug users."""
        diag = self.engine.last_error
        if diag:
            self.lbl_question.configure(text=f"✖ {diag.title} ({diag.component})", text_color="#ef4444")
            if self.config.debug_mode:
                tb_snip = f"\n\n[Stack Trace Preview]:\n{diag.traceback_str[:250]}..." if diag.traceback_str else ""
                self.lbl_answer.configure(text=f"Error Details: {diag.message}", text_color="#fca5a5")
                self.lbl_reasoning.configure(text=f"{diag.troubleshooting_hint}{tb_snip}", text_color="#93c5fd")
            else:
                self.lbl_answer.configure(text=f"Error: {diag.message}", text_color="#fca5a5")
                self.lbl_reasoning.configure(text=diag.troubleshooting_hint, text_color="#93c5fd")
        else:
            self.lbl_question.configure(text="✖ Execution Error Encountered", text_color="#ef4444")
            self.lbl_answer.configure(text=detail or "An unknown error occurred.", text_color="#fca5a5")
            self.lbl_reasoning.configure(
                text="Click 'Full Diagnostic & Logs' below or in the status bar for full details.",
                text_color="#93c5fd"
            )

        self.error_actions_frame.pack(fill="x", padx=6, pady=4)

    def _copy_current_error_report(self):
        diag = self.engine.last_error
        if diag:
            text = diag.to_clipboard_text()
        else:
            text = self.engine.error_message or "No error details available."
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Error diagnostic report copied to clipboard!")

    def open_debug_window(self, open_error_tab: bool = False):
        """Opens or focuses the cloaked Debug Console & Error Inspector."""
        from ui.debug_window import DebugWindow
        if self.debug_window is not None and self.debug_window.winfo_exists():
            if open_error_tab:
                self.debug_window.tabs.set("⚠️ Error Diagnostics")
                self.debug_window._display_error_diagnostic(self.engine.last_error)
            self.debug_window.lift()
            self.debug_window.focus_force()
            return

        self.debug_window = DebugWindow(
            master=self.master,
            engine=self.engine,
            open_error_tab=open_error_tab,
            initial_error=self.engine.last_error
        )

    def _on_engine_result(self, result: Dict[str, Any]):
        self.after(0, lambda: self._update_result_ui(result))

    def _update_result_ui(self, result: Dict[str, Any]):
        self.error_actions_frame.pack_forget()
        q = result.get("question") or result.get("question_text") or result.get("summary") or "Question detected"
        ans = result.get("answer") or result.get("correct_answer") or result.get("proposed_answer")
        items = result.get("items", [])
        if not ans and items:
            answers_list = []
            for itm in items:
                part_name = itm.get("label") or itm.get("part_id") or "Part"
                p_a = itm.get("correct_answer") or itm.get("proposed_answer") or itm.get("answer")
                if p_a:
                    answers_list.append(f"{part_name}: {p_a}")
            if answers_list:
                ans = " | ".join(answers_list)
        if not ans:
            ans = "Answer resolved"

        reasoning = result.get("reasoning") or result.get("summary") or ""
        conf = result.get("confidence", 1.0)
        actions = result.get("actions", [])
        next_btn = result.get("next_button")

        eval_status = result.get("evaluation_status", "unsubmitted")
        is_rethinking = result.get("is_rethinking", False)
        rethink_reasoning = result.get("rethink_reasoning") or ""
        platform_feedback = result.get("platform_feedback") or ""

        self.lbl_question.configure(text=f"Q: {q}", text_color="#e4e4e7")

        if eval_status == "incorrect" or is_rethinking:
            self.lbl_answer.configure(text=f"New Solution ({int(conf * 100)}%): {ans}", text_color="#fde047")
        elif eval_status == "correct":
            self.lbl_answer.configure(text=f"Verified Solution: {ans}", text_color="#34d399")
        else:
            self.lbl_answer.configure(text=f"Answer ({int(conf * 100)}%): {ans}", text_color="#38bdf8")

        self.lbl_reasoning.configure(text=f"Reasoning: {reasoning}", text_color="#9ca3af")

        # Update Platform Evaluation Status badge & banner
        if eval_status == "correct":
            self.eval_status_frame.pack(fill="x", padx=6, pady=(1, 2), before=self.lbl_answer)
            self.lbl_eval_badge.configure(
                text="✓ PLATFORM: CORRECT",
                fg_color="#064e3b",
                text_color="#34d399"
            )
            self.lbl_eval_badge.pack(side="left")
            if platform_feedback:
                self.lbl_eval_platform_feedback.configure(text=f"({platform_feedback})", text_color="#6ee7b7")
                self.lbl_eval_platform_feedback.pack(side="left", padx=4)
            else:
                self.lbl_eval_platform_feedback.pack_forget()
            self.rethink_frame.pack_forget()
        elif eval_status == "incorrect" or is_rethinking:
            self.eval_status_frame.pack(fill="x", padx=6, pady=(1, 2), before=self.lbl_answer)
            self.lbl_eval_badge.configure(
                text="❌ PLATFORM: INCORRECT -> RETHINKING",
                fg_color="#7f1d1d",
                text_color="#fca5a5"
            )
            self.lbl_eval_badge.pack(side="left")
            if platform_feedback:
                self.lbl_eval_platform_feedback.configure(text=f"Platform: {platform_feedback}", text_color="#fca5a5")
                self.lbl_eval_platform_feedback.pack(side="left", padx=4)
            else:
                self.lbl_eval_platform_feedback.pack_forget()

            if rethink_reasoning:
                self.lbl_rethink_text.configure(text=rethink_reasoning)
                self.rethink_frame.pack(fill="x", padx=6, pady=3, before=self.lbl_reasoning)
            else:
                self.rethink_frame.pack_forget()
        else:
            self.eval_status_frame.pack(fill="x", padx=6, pady=(1, 2), before=self.lbl_answer)
            self.lbl_eval_badge.configure(
                text="● PLATFORM: UNCHECKED / DRAFT",
                fg_color="#1e293b",
                text_color="#94a3b8"
            )
            self.lbl_eval_badge.pack(side="left")
            self.lbl_eval_platform_feedback.pack_forget()
            self.rethink_frame.pack_forget()

        # Clear existing multi-part item widgets
        for child in self.items_container.winfo_children():
            child.destroy()

        if items and len(items) > 0:
            self.items_container.pack(fill="x", padx=4, pady=2, before=self.lbl_reasoning)
            for itm in items:
                part_id = itm.get("part_id", "")
                label = itm.get("label") or itm.get("part_id") or f"Part {part_id}"
                q_text = itm.get("question_text") or itm.get("question") or ""
                p_ans = itm.get("correct_answer") or itm.get("proposed_answer") or itm.get("answer") or "N/A"
                itm_eval = itm.get("evaluation_status", "unsubmitted")
                itm_rethinking = itm.get("is_rethinking", False)
                state = itm.get("current_state", "unanswered")
                needs_act = itm.get("needs_action", True)

                # Determine badge text and colors
                if itm_eval == "correct" or state == "correct" or not needs_act:
                    badge_text = "✓ CORRECT"
                    badge_bg = "#064e3b"
                    badge_fg = "#34d399"
                    note = "(Kept untouched)"
                elif itm_eval == "incorrect" or itm_rethinking or state == "wrong":
                    badge_text = "❌ INCORRECT -> RETHINKING"
                    badge_bg = "#7f1d1d"
                    badge_fg = "#fca5a5"
                    r_text = itm.get("rethink_reasoning")
                    note = f"-> {p_ans}" + (f" (Rethink: {r_text[:60]}...)" if r_text else "")
                else:
                    badge_text = "● ANSWERING"
                    badge_bg = "#1e3a8a"
                    badge_fg = "#93c5fd"
                    note = f"-> {p_ans}"

                row = ctk.CTkFrame(self.items_container, fg_color="#18181b", corner_radius=6)
                row.pack(fill="x", pady=2)

                top_bar = ctk.CTkFrame(row, fg_color="transparent")
                top_bar.pack(fill="x", padx=6, pady=(4, 2))

                lbl_part = ctk.CTkLabel(
                    top_bar,
                    text=label,
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color="#f8fafc"
                )
                lbl_part.pack(side="left")

                badge = ctk.CTkLabel(
                    top_bar,
                    text=badge_text,
                    font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                    fg_color=badge_bg,
                    text_color=badge_fg,
                    corner_radius=4,
                    padx=6,
                    pady=1
                )
                badge.pack(side="right")

                content_text = f"{q_text[:70]}..." if len(q_text) > 70 else q_text
                lbl_desc = ctk.CTkLabel(
                    row,
                    text=f"{content_text}\nAnswer: {p_ans} {note}",
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color="#cbd5e1",
                    justify="left",
                    wraplength=400
                )
                lbl_desc.pack(anchor="w", padx=6, pady=(0, 4))
        else:
            self.items_container.pack_forget()

        # Written Questions Card & Live Editor (AVA 2.0)
        is_written = bool(result.get("is_written_response", False))
        if is_written:
            written_info = result.get("written_details", {})
            full_text = written_info.get("text", "")
            if not full_text:
                full_text = ans if len(ans) > 25 else ""

            word_count = written_info.get("word_count", len(re.findall(r"\b[A-Za-z0-9'-]+\b", full_text)))
            min_w = written_info.get("min_words")
            humanized = written_info.get("humanized", False)
            metrics = written_info.get("humanize_metrics", {})
            grade = metrics.get("flesch_kincaid_grade")

            min_str = f" / Min: {min_w}" if min_w else ""
            badge_color = "#10b981" if not min_w or word_count >= min_w else "#f59e0b"
            self.lbl_written_badge.configure(text=f"{word_count} words{min_str}", fg_color=badge_color)

            if humanized:
                h_text = "Jade's Humanizer: Active" + (f" (Grade {grade:.1f})" if grade else "")
                self.lbl_humanizer_badge.configure(text=h_text, fg_color="#064e3b", text_color="#34d399")
            else:
                self.lbl_humanizer_badge.configure(text="Jade's Humanizer: Off", fg_color="#1e293b", text_color="#94a3b8")

            # Update editor content if different
            curr_editor_content = self.txt_written_edit.get("1.0", "end-1c").strip()
            if curr_editor_content != full_text:
                self.txt_written_edit.delete("1.0", "end")
                self.txt_written_edit.insert("1.0", full_text)

            self.written_card.pack(fill="x", padx=6, pady=4, before=self.lbl_reasoning)
        else:
            self.written_card.pack_forget()

        # Update Next button label to reflect whether Check Answer, Next, or Submit was detected
        check_btn = result.get("check_button")
        submit_btn = result.get("submit_button")
        hk_next = self.config.hotkeys.get("next_question", "F10")
        if submit_btn and not next_btn:
            self.btn_next.configure(text=f"🚀 Submit ({hk_next})")
        elif check_btn and not next_btn:
            self.btn_next.configure(text=f"✓ Check ({hk_next})")
        elif check_btn and next_btn:
            self.btn_next.configure(text=f"✓ Check & Next ({hk_next})")
        else:
            self.btn_next.configure(text=f"⏭ Next ({hk_next})")

        # Draw targets on cloaked visualizer overlay
        self.visualizer.draw_actions(actions, next_btn, check_btn, submit_btn)

    def _on_written_text_edited(self, event=None):
        """Called live as the user types into the written response preview box."""
        raw_text = self.txt_written_edit.get("1.0", "end-1c").strip()
        words = len(re.findall(r"\b[A-Za-z0-9'-]+\b", raw_text))
        min_w = None
        if self.engine.last_result and "written_details" in self.engine.last_result:
            min_w = self.engine.last_result["written_details"].get("min_words")

        min_str = f" / Min: {min_w}" if min_w else ""
        color = "#10b981" if not min_w or words >= min_w else "#f59e0b"
        self.lbl_written_badge.configure(text=f"{words} words{min_str}", fg_color=color)

        # Propagate edited text directly to engine
        self.engine.update_written_text(raw_text)

    def _rehumanize_written_draft(self):
        """Re-runs Jade's AI Humanizer and spellcheck on the current text in the editor."""
        raw_text = self.txt_written_edit.get("1.0", "end-1c").strip()
        if not raw_text or not self.engine.written_solver:
            return
        try:
            res = self.engine.written_solver.humanizer.humanize(
                raw_text,
                mode=self.config.humanizer_mode,
                tone=self.config.humanizer_tone,
                reading_level=self.config.humanizer_reading_level,
            )
            polished, _ = self.engine.written_solver.spellcheck.check_and_correct(res.text)
            self.txt_written_edit.delete("1.0", "end")
            self.txt_written_edit.insert("1.0", polished)
            self._on_written_text_edited()
        except Exception as e:
            logger.warning(f"Re-humanize failed: {e}")

    def toggle_collapse(self):
        """Toggles between compact pill and expanded view."""
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.content_container.pack_forget()
            self.btn_frame.pack_forget()
            self.btn_collapse.configure(text="▼")
            self.geometry(f"460x86")
        else:
            self.content_container.pack(fill="both", expand=True, padx=8, pady=2)
            self.btn_frame.pack(fill="x", padx=6, pady=(0, 6))
            self.btn_collapse.configure(text="▲")
            self.geometry(f"460x320")

    def minimize_overlay(self):
        """Minimizes the HUD overlay to the Windows taskbar normally."""
        self.is_hidden = False
        try:
            if hasattr(self, "visualizer") and self.visualizer:
                self.visualizer.clear()
            from core.cloaking import get_window_hwnd, apply_anti_capture
            hwnd = get_window_hwnd(self)
            if hwnd:
                apply_anti_capture(hwnd, enable=False)
            self.overrideredirect(False)
            self.iconify()
        except Exception as e:
            logger.debug(f"Error in minimize_overlay: {e}")
            self.iconify()

    def hide_overlay(self):
        """Hides the overlay window from the screen (delegates to minimize_overlay)."""
        self.minimize_overlay()

    def show_overlay(self):
        """Shows and restores the overlay to topmost with cloaking intact."""
        self.is_hidden = False
        try:
            self.deiconify()
            self.overrideredirect(True)
            self.lift()
            self.attributes("-topmost", True)
            self.apply_cloak()
        except Exception as e:
            logger.debug(f"Error in show_overlay: {e}")

    def toggle_visibility(self) -> bool:
        """Toggles between minimized and shown states. Returns True if now visible."""
        try:
            is_iconic = False
            if hasattr(self, "state") and self.state() == "iconic":
                is_iconic = True
            elif sys.platform == "win32":
                import ctypes
                from core.cloaking import get_window_hwnd
                hwnd = get_window_hwnd(self)
                if hwnd and ctypes.windll.user32.IsIconic(hwnd):
                    is_iconic = True

            if is_iconic or not self.winfo_viewable() or self.is_hidden:
                self.show_overlay()
                return True
            else:
                self.minimize_overlay()
                return False
        except Exception as e:
            logger.debug(f"Error toggling visibility: {e}")
            self.show_overlay()
            return True

    def _handle_close(self):
        """Handles close button click from HUD header."""
        if self.on_close_app:
            self.on_close_app()
        else:
            self.destroy()

    def set_header_icon_size(self, size: int):
        """Dynamically resizes all header bar action icons and container buttons."""
        self.icon_size = max(8, min(18, int(size)))
        btn_wh = self.icon_size + 11
        corner_rad = btn_wh // 2
        btn_font = ctk.CTkFont(size=self.icon_size)

        # Cutout button is smaller
        snip_wh = max(18, btn_wh - 4)
        snip_corner = snip_wh // 2
        snip_font = ctk.CTkFont(size=max(8, self.icon_size - 2))

        if hasattr(self, "btn_snip") and self.btn_snip and self.btn_snip.winfo_exists():
            self.btn_snip.configure(width=snip_wh, height=snip_wh, corner_radius=snip_corner, font=snip_font)

        standard_buttons = [
            getattr(self, "btn_playground", None),
            getattr(self, "btn_debug", None),
            getattr(self, "btn_settings", None),
            getattr(self, "btn_collapse", None),
            getattr(self, "btn_hide", None),
            getattr(self, "btn_close", None),
        ]
        for b in standard_buttons:
            if b and b.winfo_exists():
                b.configure(width=btn_wh, height=btn_wh, corner_radius=corner_rad, font=btn_font)

        # Persist to configuration
        try:
            self.config_manager.update(header_icon_size=self.icon_size)
        except Exception:
            pass

    def _on_header_mousewheel(self, event):
        """Ctrl + MouseWheel on header bar to dynamically scale header icon size."""
        if hasattr(event, "delta") and event.delta != 0:
            step = 1 if event.delta > 0 else -1
            self.set_header_icon_size(self.icon_size + step)

    def refresh_hotkey_labels(self):
        """Refreshes button labels to reflect updated hotkey settings."""
        hk = self.config.hotkeys
        hk_solve = hk.get("trigger_solve", "F8")
        hk_confirm = hk.get("confirm_action", "F9")
        hk_next = hk.get("next_question", "F10")
        hk_pause = hk.get("pause_resume", "F7")
        hk_stop = hk.get("emergency_stop", "F12")

        if hasattr(self, "btn_solve"):
            self.btn_solve.configure(text=f"▶ Solve ({hk_solve})")
        if hasattr(self, "btn_confirm"):
            self.btn_confirm.configure(text=f"✓ Confirm ({hk_confirm})")
        if hasattr(self, "btn_next"):
            self.btn_next.configure(text=f"⏭ Next ({hk_next})")
        if hasattr(self, "btn_pause"):
            self.btn_pause.configure(text=f"⏸ Pause ({hk_pause})")
        if hasattr(self, "btn_stop"):
            self.btn_stop.configure(text=f"⏹ Killswitch ({hk_stop})")

    def _on_drag_start(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag_motion(self, event):
        deltax = event.x - self._drag_start_x
        deltay = event.y - self._drag_start_y
        new_x = self.winfo_x() + deltax
        new_y = self.winfo_y() + deltay
        self.geometry(f"+{new_x}+{new_y}")

    def _on_drag_release(self, event):
        # Save position to config
        self.config_manager.update(overlay_x=self.winfo_x(), overlay_y=self.winfo_y())

    def _test_cloak_visibility(self):
        """
        Takes a screenshot of the region occupied by this HUD using mss,
        and displays it to prove that the HUD is completely invisible to screen capture!
        """
        x = self.winfo_x()
        y = self.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()

        # Capture area where HUD sits
        img = self.engine.capture.capture_screen(region=(x, y, x + w, y + h))

        # Show verification dialog with the captured image
        test_win = ctk.CTkToplevel(self)
        test_win.title("Anti-Capture Cloak Verification")
        test_win.geometry("500x380")
        test_win.attributes("-topmost", True)

        ctk.CTkLabel(
            test_win,
            text="🛡️ Screen Capture Proof",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#10b981"
        ).pack(pady=8)

        ctk.CTkLabel(
            test_win,
            text="The image below was captured from the screen right where the HUD is sitting.\n"
                 "Notice the HUD is 100% invisible to screen recorders, screen sharing, and captures!",
            font=ctk.CTkFont(size=11),
            text_color="#d1d5db"
        ).pack(pady=4)

        # Convert PIL image for CTkImage
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(380, 200))
        img_lbl = ctk.CTkLabel(test_win, image=ctk_img, text="")
        img_lbl.pack(pady=10)

        ctk.CTkButton(test_win, text="Close", command=test_win.destroy, width=120).pack(pady=6)

    def _manual_scroll_down(self):
        """Manually scrolls viewport down 450px to view more of the question."""
        try:
            self.engine.executor.scroll(-450)
            self._show_adjustment_toast("📜 Scrolled viewport down 450px")
        except Exception as e:
            logger.debug(f"Manual scroll down error: {e}")

    def _manual_scroll_up(self):
        """Manually scrolls viewport up 450px to return to top."""
        try:
            self.engine.executor.scroll(450)
            self._show_adjustment_toast("📜 Scrolled viewport up 450px")
        except Exception as e:
            logger.debug(f"Manual scroll up error: {e}")

    def _manual_inspect_whole_question(self):
        """Forces solve pipeline to inspect both upper and lower views for long questions."""
        self._show_adjustment_toast("🔍 Inspecting whole question (Dual-View)...")
        self.engine.trigger_solve()

