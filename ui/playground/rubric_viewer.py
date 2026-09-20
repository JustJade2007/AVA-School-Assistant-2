"""
Rubric Viewer Component for AVA Playground Mode.
Displays criteria checklist items with completion states, target points,
and live fulfillment indicators.
"""

import customtkinter as ctk
from typing import List, Callable, Optional
from core.playground.project_model import RubricCriterion


class RubricViewer(ctk.CTkFrame):
    """Visual checklist display for parsed rubric criteria."""

    def __init__(
        self,
        master,
        criteria: Optional[List[RubricCriterion]] = None,
        on_criterion_toggle: Optional[Callable[[str, bool], None]] = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)
        self.criteria: List[RubricCriterion] = criteria or []
        self.on_criterion_toggle = on_criterion_toggle
        self._checkbox_vars = {}

        self.configure(fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        self._build_ui()

    def _build_ui(self):
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=12, pady=(10, 6))

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="📋 Rubric Checklist",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f8fafc"
        )
        self.title_label.pack(side="left")

        self.count_badge = ctk.CTkLabel(
            self.header_frame,
            text=f"0 / {len(self.criteria)} Met",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8",
            fg_color="#0f172a",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.count_badge.pack(side="right")

        # Scrollable list
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#09090b",
            corner_radius=8,
            scrollbar_button_color="#27272a",
            scrollbar_button_hover_color="#3f3f46"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.render_criteria(self.criteria)

    def set_criteria(self, criteria: List[RubricCriterion]):
        self.criteria = criteria
        self.render_criteria(criteria)

    def render_criteria(self, criteria: List[RubricCriterion]):
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self._checkbox_vars.clear()

        if not criteria:
            empty_lbl = ctk.CTkLabel(
                self.scroll_frame,
                text="No rubric criteria loaded.\nUpload a rubric or screen-snip to extract requirements.",
                font=ctk.CTkFont(size=12),
                text_color="#71717a",
                justify="center"
            )
            empty_lbl.pack(pady=30, padx=10)
            self.count_badge.configure(text="0 Criteria")
            return

        fulfilled_count = 0
        for crit in criteria:
            if crit.fulfilled:
                fulfilled_count += 1

            c_frame = ctk.CTkFrame(self.scroll_frame, fg_color="#18181b", corner_radius=6, border_width=1, border_color="#27272a")
            c_frame.pack(fill="x", pady=4, padx=2)

            var = ctk.BooleanVar(value=crit.fulfilled)
            self._checkbox_vars[crit.id] = var

            def on_check(c_id=crit.id, v=var):
                is_checked = v.get()
                for c in self.criteria:
                    if c.id == c_id:
                        c.fulfilled = is_checked
                        break
                self._update_badge()
                if self.on_criterion_toggle:
                    self.on_criterion_toggle(c_id, is_checked)

            cb = ctk.CTkCheckBox(
                c_frame,
                text=crit.title,
                variable=var,
                command=on_check,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#f1f5f9",
                fg_color="#3b82f6",
                hover_color="#2563eb",
                border_color="#52525b",
                corner_radius=4
            )
            cb.pack(anchor="w", padx=8, pady=(6, 2))

            if crit.target_score:
                score_lbl = ctk.CTkLabel(
                    c_frame,
                    text=f"Score: {crit.target_score}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#a855f7"
                )
                score_lbl.pack(anchor="w", padx=32, pady=(0, 2))

            if crit.description:
                desc_lbl = ctk.CTkLabel(
                    c_frame,
                    text=crit.description,
                    font=ctk.CTkFont(size=11),
                    text_color="#94a3b8",
                    wraplength=260,
                    justify="left"
                )
                desc_lbl.pack(anchor="w", padx=32, pady=(0, 6))

        self._update_badge()

    def _update_badge(self):
        fulfilled = sum(1 for c in self.criteria if c.fulfilled)
        self.count_badge.configure(text=f"{fulfilled} / {len(self.criteria)} Met")
        if fulfilled == len(self.criteria) and len(self.criteria) > 0:
            self.count_badge.configure(text_color="#10b981")
        else:
            self.count_badge.configure(text_color="#38bdf8")
