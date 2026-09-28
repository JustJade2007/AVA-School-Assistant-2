"""
Rubric Viewer Component for AVA Playground Mode.
Displays criteria checklist items with completion states, target points,
and live fulfillment indicators.
Supports interactive editing, manual additions, and deletions of criteria.
"""

import uuid
import customtkinter as ctk
from tkinter import messagebox
from typing import List, Callable, Optional
from core.playground.project_model import RubricCriterion


class CriterionEditModal(ctk.CTkToplevel):
    """Dialog for creating or editing an individual rubric criterion."""

    def __init__(
        self,
        master,
        criterion: Optional[RubricCriterion] = None,
        on_save: Optional[Callable[[RubricCriterion], None]] = None,
    ):
        super().__init__(master)
        self.criterion = criterion
        self.on_save = on_save

        self.title("Edit Rubric Criterion" if criterion else "Add Rubric Criterion")
        self.geometry("440x360")
        self.resizable(False, False)
        self.configure(fg_color="#18181b")

        self.transient(master)
        self.grab_set()

        self._build_ui()
        self.after(50, self.lift)

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=16)

        # Header
        ctk.CTkLabel(
            container,
            text="✏️ Edit Rubric Criterion" if self.criterion else "➕ Add Rubric Criterion",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f8fafc",
        ).pack(anchor="w", pady=(0, 12))

        # Title Field
        ctk.CTkLabel(
            container,
            text="Criterion Title / Requirement:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(0, 4))

        self.title_entry = ctk.CTkEntry(
            container,
            placeholder_text="e.g., Historical Context & Evidence",
            font=ctk.CTkFont(size=12),
            fg_color="#09090b",
        )
        self.title_entry.pack(fill="x", pady=(0, 10))
        if self.criterion:
            self.title_entry.insert(0, self.criterion.title)

        # Score / Points Field
        ctk.CTkLabel(
            container,
            text="Points / Weight (optional):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(0, 4))

        self.score_entry = ctk.CTkEntry(
            container,
            placeholder_text="e.g., 20 pts or 15%",
            font=ctk.CTkFont(size=12),
            fg_color="#09090b",
        )
        self.score_entry.pack(fill="x", pady=(0, 10))
        if self.criterion and self.criterion.target_score:
            self.score_entry.insert(0, self.criterion.target_score)

        # Detailed Description
        ctk.CTkLabel(
            container,
            text="Guidelines / What is required to fulfill this:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
        ).pack(anchor="w", pady=(0, 4))

        self.desc_box = ctk.CTkTextbox(
            container,
            height=90,
            font=ctk.CTkFont(size=12),
            fg_color="#09090b",
        )
        self.desc_box.pack(fill="both", expand=True, pady=(0, 14))
        if self.criterion and self.criterion.description:
            self.desc_box.insert("1.0", self.criterion.description)

        # Action Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self.destroy,
            width=80,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46",
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Criterion",
            command=self._on_save_clicked,
            width=120,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
        )
        save_btn.pack(side="right")

    def _on_save_clicked(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Validation", "Please enter a criterion title.")
            return

        score = self.score_entry.get().strip()
        desc = self.desc_box.get("1.0", "end").strip()

        if self.criterion:
            self.criterion.title = title
            self.criterion.target_score = score
            self.criterion.description = desc
            res = self.criterion
        else:
            res = RubricCriterion(
                id=str(uuid.uuid4())[:8],
                title=title,
                target_score=score,
                description=desc,
                fulfilled=False,
            )

        if self.on_save:
            self.on_save(res)
        self.destroy()


class RubricViewer(ctk.CTkFrame):
    """Visual checklist display with full editing, addition, and deletion of rubric criteria."""

    def __init__(
        self,
        master,
        criteria: Optional[List[RubricCriterion]] = None,
        on_criterion_toggle: Optional[Callable[[str, bool], None]] = None,
        on_criteria_changed: Optional[Callable[[List[RubricCriterion]], None]] = None,
        editable: bool = True,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.criteria: List[RubricCriterion] = criteria or []
        self.on_criterion_toggle = on_criterion_toggle
        self.on_criteria_changed = on_criteria_changed
        self.editable = editable
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
            text_color="#f8fafc",
        )
        self.title_label.pack(side="left")

        # Right side header: Count Badge and + Add Criterion button
        self.count_badge = ctk.CTkLabel(
            self.header_frame,
            text=f"0 / {len(self.criteria)} Met",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8",
            fg_color="#0f172a",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.count_badge.pack(side="right")

        if self.editable:
            self.add_crit_btn = ctk.CTkButton(
                self.header_frame,
                text="+ Add Criterion",
                command=self._prompt_add_criterion,
                width=100,
                height=24,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#2563eb",
                hover_color="#1d4ed8",
            )
            self.add_crit_btn.pack(side="right", padx=(0, 8))

        # Scrollable list
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#09090b",
            corner_radius=8,
            scrollbar_button_color="#27272a",
            scrollbar_button_hover_color="#3f3f46",
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
                text="No rubric criteria loaded.\nUpload a rubric, screen-snip, or click '+ Add Criterion'.",
                font=ctk.CTkFont(size=12),
                text_color="#71717a",
                justify="center",
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

            top_row = ctk.CTkFrame(c_frame, fg_color="transparent")
            top_row.pack(fill="x", padx=8, pady=(6, 2))

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
                if self.on_criteria_changed:
                    self.on_criteria_changed(self.criteria)

            cb = ctk.CTkCheckBox(
                top_row,
                text=crit.title,
                variable=var,
                command=on_check,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#f1f5f9",
                fg_color="#3b82f6",
                hover_color="#2563eb",
                border_color="#52525b",
                corner_radius=4,
            )
            if self.editable:
                del_btn = ctk.CTkButton(
                    top_row,
                    text="✕",
                    command=lambda c_id=crit.id: self._delete_criterion(c_id),
                    width=22,
                    height=22,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color="transparent",
                    hover_color="#991b1b",
                    text_color="#94a3b8",
                )
                del_btn.pack(side="right", padx=(2, 0))

                edit_btn = ctk.CTkButton(
                    top_row,
                    text="✏️",
                    command=lambda c=crit: self._prompt_edit_criterion(c),
                    width=24,
                    height=22,
                    font=ctk.CTkFont(size=10),
                    fg_color="transparent",
                    hover_color="#3f3f46",
                    text_color="#94a3b8",
                )
                edit_btn.pack(side="right")

            cb.pack(side="left", fill="x", expand=True)

            if crit.target_score:
                score_lbl = ctk.CTkLabel(
                    c_frame,
                    text=f"Score / Weight: {crit.target_score}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="#a855f7",
                )
                score_lbl.pack(anchor="w", padx=32, pady=(0, 2))

            if crit.description:
                desc_lbl = ctk.CTkLabel(
                    c_frame,
                    text=crit.description,
                    font=ctk.CTkFont(size=11),
                    text_color="#94a3b8",
                    wraplength=260,
                    justify="left",
                )
                desc_lbl.pack(anchor="w", padx=32, pady=(0, 6))

        self._update_badge()

    def _prompt_add_criterion(self):
        def on_save(new_c: RubricCriterion):
            self.criteria.append(new_c)
            self.render_criteria(self.criteria)
            if self.on_criteria_changed:
                self.on_criteria_changed(self.criteria)

        CriterionEditModal(master=self.winfo_toplevel(), criterion=None, on_save=on_save)

    def _prompt_edit_criterion(self, crit: RubricCriterion):
        def on_save(updated_c: RubricCriterion):
            self.render_criteria(self.criteria)
            if self.on_criteria_changed:
                self.on_criteria_changed(self.criteria)

        CriterionEditModal(master=self.winfo_toplevel(), criterion=crit, on_save=on_save)

    def _delete_criterion(self, crit_id: str):
        target = next((c for c in self.criteria if c.id == crit_id), None)
        title = target.title if target else "this criterion"
        if messagebox.askyesno("Delete Criterion", f"Are you sure you want to remove '{title}'?"):
            self.criteria = [c for c in self.criteria if c.id != crit_id]
            self.render_criteria(self.criteria)
            if self.on_criteria_changed:
                self.on_criteria_changed(self.criteria)

    def _update_badge(self):
        fulfilled = sum(1 for c in self.criteria if c.fulfilled)
        self.count_badge.configure(text=f"{fulfilled} / {len(self.criteria)} Met")
        if fulfilled == len(self.criteria) and len(self.criteria) > 0:
            self.count_badge.configure(text_color="#10b981")
        else:
            self.count_badge.configure(text_color="#38bdf8")
