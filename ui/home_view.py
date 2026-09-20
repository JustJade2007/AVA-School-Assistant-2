"""
Home Page / Command Hub for AVA School Assistant 2.
Provides a modern, modular launching pad for:
- Automated Worker (Stealth HUD Overlay & Autonomous Solving)
- Playground Studio (Long-form Writing, Rubrics, Web/YouTube Citations, & Docx Export)
- Settings & Preferences
- Extensible slots for future modules (Flashcards, Quizzes, AI Agents)
"""

import os
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Optional, Callable, List

from core.logger import get_logger
from core.cloaking import apply_anti_capture
from ui.changelog_viewer import ChangelogViewer
from ui.asset_loader import apply_window_icon, get_logo_ctk_image

logger = get_logger("ui.home_view")


class HomeDashboard(ctk.CTkToplevel):
    """Modern Command Hub dashboard displaying application modules."""

    def __init__(
        self,
        master,
        config_manager=None,
        on_launch_worker: Optional[Callable[[], None]] = None,
        on_launch_playground: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)
        self.config_manager = config_manager
        self.on_launch_worker = on_launch_worker
        self.on_launch_playground = on_launch_playground
        self.on_open_settings = on_open_settings
        self.on_exit_app = on_exit_app

        self.is_cloaked = True

        self._setup_window()
        self._build_header()
        self._build_hero()
        self._build_module_grid()
        self._build_footer()

        # Apply stealth cloaking
        self.after(200, self._apply_initial_cloak)

    @property
    def config(self):
        return self.config_manager.config if self.config_manager else None

    def _setup_window(self):
        self.title("AVA • Command Hub")
        self.geometry("960x680+120+80")
        self.minsize(860, 600)
        self.configure(fg_color="#09090b")
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close_requested)

    def _apply_initial_cloak(self):
        enabled = self.config.anti_capture_enabled if self.config else True
        self.is_cloaked = enabled
        apply_anti_capture(self, enable=enabled)
        self._update_cloak_button()

    def _toggle_cloak(self):
        self.is_cloaked = not self.is_cloaked
        apply_anti_capture(self, enable=self.is_cloaked)
        self._update_cloak_button()

    def _update_cloak_button(self):
        if hasattr(self, "cloak_btn"):
            if self.is_cloaked:
                self.cloak_btn.configure(
                    text="🛡️ Cloaked",
                    fg_color="#064e3b",
                    hover_color="#065f46",
                    text_color="#34d399",
                    border_color="#059669"
                )
            else:
                self.cloak_btn.configure(
                    text="⚠️ Uncloaked",
                    fg_color="#78350f",
                    hover_color="#92400e",
                    text_color="#fcd34d",
                    border_color="#d97706"
                )

    # -------------------------------------------------------------------------
    # Header & Status
    # -------------------------------------------------------------------------

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="#121215", corner_radius=0, height=58)
        header_frame.pack(fill="x", side="top")

        # Left: Brand Logo & Title
        brand_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_box.pack(side="left", padx=24, pady=12)

        self.logo_img = get_logo_ctk_image(size=(32, 32))
        if self.logo_img:
            self.logo_icon_lbl = ctk.CTkLabel(brand_box, text="", image=self.logo_img)
            self.logo_icon_lbl.pack(side="left", padx=(0, 10))

        logo_lbl = ctk.CTkLabel(
            brand_box,
            text="⚡ AVA",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        logo_lbl.pack(side="left")

        title_lbl = ctk.CTkLabel(
            brand_box,
            text="SCHOOL ASSISTANT 2",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f8fafc"
        )
        title_lbl.pack(side="left", padx=(8, 10))

        ver_badge = ctk.CTkLabel(
            brand_box,
            text="v2.1",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#38bdf8",
            fg_color="#082f49",
            corner_radius=6,
            padx=8,
            pady=2
        )
        ver_badge.pack(side="left")

        # Right: AI Model Pill & Cloak Toggle
        right_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=24, pady=12)

        # AI Status pill
        model_name = self.config.model_name if self.config else "gemini-2.5-flash"
        provider = getattr(self.config, "ai_provider", "gemini").upper()
        self.ai_status_pill = ctk.CTkLabel(
            right_box,
            text=f"✨ {provider}: {model_name}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#a7f3d0",
            fg_color="#064e3b",
            corner_radius=12,
            padx=10,
            pady=4
        )
        self.ai_status_pill.pack(side="left", padx=(0, 10))

        # Changelog Button
        self.changelog_btn = ctk.CTkButton(
            right_box,
            text="📜 Changelog",
            command=self._show_changelog_dialog,
            width=105,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1,
            fg_color="#18181b",
            hover_color="#27272a",
            text_color="#38bdf8",
            border_color="#0284c7"
        )
        self.changelog_btn.pack(side="left", padx=(0, 10))

        # Cloak Toggle Button
        self.cloak_btn = ctk.CTkButton(
            right_box,
            text="🛡️ Cloaked",
            command=self._toggle_cloak,
            width=100,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1,
            fg_color="#064e3b",
            text_color="#34d399",
            border_color="#059669"
        )
        self.cloak_btn.pack(side="left")

    # -------------------------------------------------------------------------
    # Hero Welcome Section
    # -------------------------------------------------------------------------

    def _build_hero(self):
        hero_frame = ctk.CTkFrame(self, fg_color="transparent")
        hero_frame.pack(fill="x", padx=32, pady=(24, 16))

        h_title = ctk.CTkLabel(
            hero_frame,
            text="Welcome to AVA Command Hub",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#ffffff"
        )
        h_title.pack(anchor="w")

        h_desc = ctk.CTkLabel(
            hero_frame,
            text="Select an assistant module to begin. Use the Automated Worker for stealth screen-solving or the Playground Studio for long-form academic writing.",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
            wraplength=800,
            justify="left"
        )
        h_desc.pack(anchor="w", pady=(4, 0))

    # -------------------------------------------------------------------------
    # Module Cards Grid
    # -------------------------------------------------------------------------

    def _build_module_grid(self):
        grid_container = ctk.CTkFrame(self, fg_color="transparent")
        grid_container.pack(fill="both", expand=True, padx=32, pady=(0, 16))

        grid_container.grid_columnconfigure(0, weight=1)
        grid_container.grid_columnconfigure(1, weight=1)
        grid_container.grid_rowconfigure(0, weight=1)
        grid_container.grid_rowconfigure(1, weight=1)

        # Card 1: Automated Worker (HUD Mode)
        self._create_module_card(
            parent=grid_container,
            row=0,
            col=0,
            icon="🤖",
            title="Automated Worker",
            badge="STEALTH OVERLAY",
            badge_color=("#1e3a8a", "#93c5fd"),
            description="Active background assistant featuring real-time screen capture, question solving, humanized typing simulation, and emergency hotkeys.",
            features=["⚡ Hotkey Driven (F4, F8, F9, F10)", "🛡️ Anti-Screen Capture Cloaking", "🤖 Autonomous & Review Modes"],
            button_text="🚀 Launch Automated Worker",
            button_color=("#2563eb", "#1d4ed8"),
            command=self._launch_worker_action
        )

        # Card 2: Playground Studio
        self._create_module_card(
            parent=grid_container,
            row=0,
            col=1,
            icon="📝",
            title="Playground Studio",
            badge="DOCUMENT STUDIO",
            badge_color=("#3b0764", "#d8b4fe"),
            description="Dedicated 4-stage workspace for long-form essays, research papers, and reports with live rubric verification and bibliography citations.",
            features=["🎯 Rubric Parser & Checklist Editor", "🌐 Web & YouTube Source Ingestion", "📄 MLA / APA Word Document Export"],
            button_text="✨ Launch Playground Studio",
            button_color=("#7c3aed", "#6d28d9"),
            command=self._launch_playground_action
        )

        # Card 3: Settings & Preferences
        self._create_module_card(
            parent=grid_container,
            row=1,
            col=0,
            icon="⚙️",
            title="Settings & Preferences",
            badge="CONFIGURATION",
            badge_color=("#27272a", "#cbd5e1"),
            description="Configure Gemini & OpenAI API keys, AI model selection, typing speeds, humanizer tones, reading levels, and global hotkeys.",
            features=["🔑 API Keys & Provider Backends", "🎭 Humanizer Tone & Reading Level", "⌨️ Custom Hotkey Keybindings"],
            button_text="🔧 Open Settings",
            button_color=("#3f3f46", "#52525b"),
            command=self._open_settings_action
        )

        # Card 4: Extensible Slot (Coming Soon)
        self._create_module_card(
            parent=grid_container,
            row=1,
            col=1,
            icon="🧩",
            title="More Modules",
            badge="EXTENSIBLE HUB",
            badge_color=("#18181b", "#71717a"),
            description="AVA is architected for modular expansion. Flashcard creator, automated quiz generator, and custom agents will appear here.",
            features=["📚 Study Deck Generator (Coming Soon)", "📊 Interactive Quiz Mode (Coming Soon)", "🔌 Plugin & Agent Extensibility"],
            button_text="📌 Modules Coming Soon",
            button_color=("#18181b", "#27272a"),
            command=None,
            is_disabled=True
        )

    def _create_module_card(
        self,
        parent,
        row: int,
        col: int,
        icon: str,
        title: str,
        badge: str,
        badge_color: tuple,
        description: str,
        features: List[str],
        button_text: str,
        button_color: tuple,
        command: Optional[Callable],
        is_disabled: bool = False
    ):
        card = ctk.CTkFrame(
            parent,
            fg_color="#141417",
            corner_radius=12,
            border_width=1,
            border_color="#27272a"
        )
        card.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=16)

        # Card Header: Icon + Title + Badge
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            top_row,
            text=icon,
            font=ctk.CTkFont(size=22)
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            top_row,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f8fafc"
        ).pack(side="left")

        b_bg, b_fg = badge_color
        b_label = ctk.CTkLabel(
            top_row,
            text=badge,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=b_bg,
            text_color=b_fg,
            corner_radius=4,
            padx=6,
            pady=2
        )
        b_label.pack(side="right")

        # Description
        desc_lbl = ctk.CTkLabel(
            inner,
            text=description,
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
            wraplength=380,
            justify="left"
        )
        desc_lbl.pack(anchor="w", pady=(0, 10))

        # Feature Bullet Points
        feat_frame = ctk.CTkFrame(inner, fg_color="transparent")
        feat_frame.pack(fill="x", pady=(0, 12))
        for feat in features:
            f_lbl = ctk.CTkLabel(
                feat_frame,
                text=feat,
                font=ctk.CTkFont(size=11),
                text_color="#64748b" if is_disabled else "#cbd5e1"
            )
            f_lbl.pack(anchor="w", pady=1)

        # Card Action Button
        btn_fg, btn_hover = button_color
        state = "disabled" if is_disabled else "normal"
        action_btn = ctk.CTkButton(
            inner,
            text=button_text,
            command=command,
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=btn_fg,
            hover_color=btn_hover,
            state=state
        )
        action_btn.pack(fill="x", side="bottom")

    # -------------------------------------------------------------------------
    # Footer Section
    # -------------------------------------------------------------------------

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="#121215", corner_radius=0, height=48)
        footer.pack(fill="x", side="bottom")

        left_box = ctk.CTkFrame(footer, fg_color="transparent")
        left_box.pack(side="left", padx=24, pady=10)

        ctk.CTkLabel(
            left_box,
            text="🟢 System Ready • Stealth Security Cloaking Active",
            font=ctk.CTkFont(size=11),
            text_color="#34d399"
        ).pack(side="left")

        right_box = ctk.CTkFrame(footer, fg_color="transparent")
        right_box.pack(side="right", padx=24, pady=10)

        footer_changelog_btn = ctk.CTkButton(
            right_box,
            text="📜 Changelog",
            command=self._show_changelog_dialog,
            width=95,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#18181b",
            hover_color="#27272a",
            text_color="#94a3b8"
        )
        footer_changelog_btn.pack(side="left", padx=(0, 10))

        exit_btn = ctk.CTkButton(
            right_box,
            text="✕ Quit AVA",
            command=self._on_close_requested,
            width=90,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#450a0a",
            hover_color="#7f1d1d",
            text_color="#fecdd3"
        )
        exit_btn.pack(side="right")

    # -------------------------------------------------------------------------
    # Module Launch Handlers
    # -------------------------------------------------------------------------

    def _show_changelog_dialog(self):
        """Opens the formatted version changelog viewer dialog."""
        ChangelogViewer(self, is_cloaked=self.is_cloaked)

    def _launch_worker_action(self):
        logger.info("Launching Automated Worker from Home Dashboard...")
        self.withdraw()
        if self.on_launch_worker:
            self.on_launch_worker()

    def _launch_playground_action(self):
        logger.info("Launching Playground Studio from Home Dashboard...")
        self.withdraw()
        if self.on_launch_playground:
            self.on_launch_playground()

    def _open_settings_action(self):
        if self.on_open_settings:
            self.on_open_settings()

    def _on_close_requested(self):
        if self.on_exit_app:
            self.on_exit_app()
        else:
            self.destroy()

    def refresh_ai_status(self):
        """Updates the AI backend pill if settings changed."""
        if hasattr(self, "ai_status_pill") and self.config:
            model_name = self.config.model_name
            provider = getattr(self.config, "ai_provider", "gemini").upper()
            self.ai_status_pill.configure(text=f"✨ {provider}: {model_name}")
