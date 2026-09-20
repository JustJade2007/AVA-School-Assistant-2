"""
Playground Workspace Window for AVA School Assistant 2.
Dedicated long-form writing studio featuring a 4-stage pipeline:
1. Rubrics & Sources Ingestion (Screen snip, PDF, DOCX, DOC, TXT, free text)
2. Outline Formulation & Rubric Criteria Checklist Mapping
3. Section-by-Section Drafting & Humanizing with Interactive User Review & Refine Loop
4. Document Compilation & Academic .docx Export (MLA, APA, Standard Report)
Includes anti-screen capture cloaking by default with a header toggle.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Optional, Callable, List, Dict, Any

from core.logger import get_logger
from core.cloaking import apply_anti_capture, is_anti_capture_supported
from core.capture import ScreenCapture
from core.playground.project_model import (
    PlaygroundProject,
    RubricCriterion,
    SourceItem,
    SectionDraft,
)
from core.playground.doc_io import DocumentImporter, DocumentExporter
from core.playground.humanizer_bridge import PlaygroundHumanizerBridge
from core.playground.engine import PlaygroundEngine
from ui.playground.rubric_viewer import RubricViewer
from ui.snipping_tool import SnippingOverlay

logger = get_logger("playground.workspace")


class PlaygroundWorkspace(ctk.CTkToplevel):
    """Dedicated long-form writing workspace for AVA Playground Mode."""

    def __init__(
        self,
        master,
        ai_client=None,
        config_manager=None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        super().__init__(master)
        self.ai_client = ai_client
        self.config_manager = config_manager
        self.on_exit = on_exit

        self.project = PlaygroundProject()
        self.humanizer_bridge = PlaygroundHumanizerBridge(
            api_key=self.config.gemini_api_key or self.config.api_key if self.config else "",
            model_name=self.config.written_model_name if self.config else "gemini-3.5-flash-lite",
            default_tone=self.config.humanizer_tone if self.config else "academic",
            default_level=self.config.humanizer_reading_level if self.config else "college",
            default_mode=self.config.humanizer_mode if self.config else "budget",
        )
        self.engine = PlaygroundEngine(ai_client=self.ai_client, config_manager=self.config_manager)
        self.snipping_overlay: Optional[SnippingOverlay] = None

        # State
        self.current_step = 1
        self.current_section_idx = 0
        self.is_cloaked = True
        self.current_file_path: Optional[str] = None
        self._is_generating = False

        self._setup_window()
        self._build_header()
        self._build_stepper()
        self._build_stage_containers()

        # Switch to step 1
        self.show_step(1)

        # Apply cloaking after window mapping
        self.after(200, self._apply_initial_cloak)

    @property
    def config(self):
        return self.config_manager.config if self.config_manager else None

    def _setup_window(self):
        self.title("AVA Playground • Long-Form Document Studio")
        self.geometry("1140x740+80+60")
        self.minsize(980, 640)
        self.configure(fg_color="#09090b")
        self.attributes("-topmost", False)

        # Protocol when closing via OS window X
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
    # Header & Stepper
    # -------------------------------------------------------------------------

    def _build_header(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="#18181b", corner_radius=0, height=52)
        self.header_frame.pack(fill="x", side="top")

        # Left: App Logo & Mode Badge
        left_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        left_box.pack(side="left", padx=16, pady=8)

        logo_lbl = ctk.CTkLabel(
            left_box,
            text="⚡ AVA PLAYGROUND",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38bdf8"
        )
        logo_lbl.pack(side="left")

        studio_badge = ctk.CTkLabel(
            left_box,
            text="STUDIO",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#a855f7",
            fg_color="#2e1065",
            corner_radius=4,
            padx=6,
            pady=2
        )
        studio_badge.pack(side="left", padx=(8, 0))

        # Center: Project title & format preset
        center_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        center_box.pack(side="left", expand=True, padx=16)

        self.title_display = ctk.CTkLabel(
            center_box,
            text=self.project.title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f8fafc"
        )
        self.title_display.pack(side="left", padx=8)

        self.format_menu = ctk.CTkOptionMenu(
            center_box,
            values=["MLA", "APA", "Standard Report"],
            command=self._on_format_changed,
            width=130,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#27272a",
            button_color="#3f3f46",
            button_hover_color="#52525b"
        )
        self.format_menu.set(self.project.formatting_preset)
        self.format_menu.pack(side="left", padx=8)

        # Right: Cloak toggle, Save/Open, and Exit
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=16, pady=8)

        self.cloak_btn = ctk.CTkButton(
            right_box,
            text="🛡️ Cloaked",
            command=self._toggle_cloak,
            width=105,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1
        )
        self.cloak_btn.pack(side="left", padx=4)

        save_btn = ctk.CTkButton(
            right_box,
            text="💾 Save",
            command=self._save_project_dialog,
            width=65,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        save_btn.pack(side="left", padx=4)

        open_btn = ctk.CTkButton(
            right_box,
            text="📂 Open",
            command=self._open_project_dialog,
            width=65,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        open_btn.pack(side="left", padx=4)

        exit_btn = ctk.CTkButton(
            right_box,
            text="✕ Return to HUD",
            command=self._on_close_requested,
            width=110,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#991b1b",
            hover_color="#b91c1c",
            text_color="#fef2f2"
        )
        exit_btn.pack(side="left", padx=(8, 0))

    def _build_stepper(self):
        self.stepper_frame = ctk.CTkFrame(self, fg_color="#121215", corner_radius=0, height=44)
        self.stepper_frame.pack(fill="x", side="top", padx=0, pady=0)

        self.step_buttons = []
        steps = [
            ("1. Rubrics & Sources", 1),
            ("2. Outline & Plan", 2),
            ("3. Section Drafting & Review", 3),
            ("4. Document & Export", 4),
        ]

        bar_inner = ctk.CTkFrame(self.stepper_frame, fg_color="transparent")
        bar_inner.pack(expand=True, pady=6)

        for label, step_num in steps:
            btn = ctk.CTkButton(
                bar_inner,
                text=label,
                command=lambda s=step_num: self.show_step(s),
                width=220,
                height=32,
                corner_radius=6,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#18181b",
                hover_color="#27272a",
                text_color="#94a3b8"
            )
            btn.pack(side="left", padx=6)
            self.step_buttons.append((btn, step_num))

    def _build_stage_containers(self):
        self.stage_container = ctk.CTkFrame(self, fg_color="transparent")
        self.stage_container.pack(fill="both", expand=True, padx=16, pady=12)

        # Stage Frames
        self.stage_1_frame = ctk.CTkFrame(self.stage_container, fg_color="transparent")
        self.stage_2_frame = ctk.CTkFrame(self.stage_container, fg_color="transparent")
        self.stage_3_frame = ctk.CTkFrame(self.stage_container, fg_color="transparent")
        self.stage_4_frame = ctk.CTkFrame(self.stage_container, fg_color="transparent")

        self._build_stage_1_ui()
        self._build_stage_2_ui()
        self._build_stage_3_ui()
        self._build_stage_4_ui()

    def show_step(self, step_num: int):
        self.current_step = step_num
        self.stage_1_frame.pack_forget()
        self.stage_2_frame.pack_forget()
        self.stage_3_frame.pack_forget()
        self.stage_4_frame.pack_forget()

        # Update Stepper button styles
        for btn, s in self.step_buttons:
            if s == step_num:
                btn.configure(fg_color="#2563eb", text_color="#ffffff", hover_color="#1d4ed8")
            elif s < step_num:
                btn.configure(fg_color="#064e3b", text_color="#6ee7b7", hover_color="#065f46")
            else:
                btn.configure(fg_color="#18181b", text_color="#94a3b8", hover_color="#27272a")

        if step_num == 1:
            self.stage_1_frame.pack(fill="both", expand=True)
        elif step_num == 2:
            self._sync_stage_2_data()
            self.stage_2_frame.pack(fill="both", expand=True)
        elif step_num == 3:
            self._sync_stage_3_data()
            self.stage_3_frame.pack(fill="both", expand=True)
        elif step_num == 4:
            self._sync_stage_4_data()
            self.stage_4_frame.pack(fill="both", expand=True)

    def _on_format_changed(self, choice: str):
        self.project.formatting_preset = choice

    # -------------------------------------------------------------------------
    # Stage 1: Rubrics & Sources Ingestion
    # -------------------------------------------------------------------------

    def _build_stage_1_ui(self):
        grid = ctk.CTkFrame(self.stage_1_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)

        # Left Column: Project Metadata & Sources
        left_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # Project Info Card
        p_info_header = ctk.CTkLabel(left_col, text="📝 Project Details", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc")
        p_info_header.pack(anchor="w", padx=16, pady=(14, 6))

        # Title
        t_row = ctk.CTkFrame(left_col, fg_color="transparent")
        t_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(t_row, text="Title:", width=80, anchor="w", text_color="#94a3b8").pack(side="left")
        self.title_entry = ctk.CTkEntry(t_row, placeholder_text="e.g., The Impact of Renewable Energy Transitions")
        self.title_entry.pack(side="left", fill="x", expand=True)
        self.title_entry.insert(0, self.project.title)
        self.title_entry.bind("<KeyRelease>", lambda e: self._on_title_entry_changed())

        # Topic / Prompt description
        desc_lbl = ctk.CTkLabel(left_col, text="Assignment Prompt / Topic:", text_color="#94a3b8")
        desc_lbl.pack(anchor="w", padx=16, pady=(8, 2))
        self.topic_textbox = ctk.CTkTextbox(left_col, height=75, fg_color="#09090b")
        self.topic_textbox.pack(fill="x", padx=16, pady=(0, 6))
        self.topic_textbox.insert("1.0", self.project.topic_description)

        # Target Word Count & Author Details
        meta_row = ctk.CTkFrame(left_col, fg_color="transparent")
        meta_row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(meta_row, text="Target Words:", text_color="#94a3b8").pack(side="left")
        self.words_entry = ctk.CTkEntry(meta_row, width=80)
        self.words_entry.insert(0, str(self.project.target_total_words))
        self.words_entry.pack(side="left", padx=8)

        ctk.CTkLabel(meta_row, text="Author:", text_color="#94a3b8").pack(side="left", padx=(12, 0))
        self.author_entry = ctk.CTkEntry(meta_row, width=140, placeholder_text="Your Name")
        self.author_entry.pack(side="left", padx=6, fill="x", expand=True)

        meta_row2 = ctk.CTkFrame(left_col, fg_color="transparent")
        meta_row2.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(meta_row2, text="Course:", text_color="#94a3b8").pack(side="left")
        self.course_entry = ctk.CTkEntry(meta_row2, width=120, placeholder_text="e.g. ENGL 101")
        self.course_entry.pack(side="left", padx=8)

        ctk.CTkLabel(meta_row2, text="Instructor:", text_color="#94a3b8").pack(side="left", padx=(12, 0))
        self.instructor_entry = ctk.CTkEntry(meta_row2, width=120, placeholder_text="e.g. Dr. Smith")
        self.instructor_entry.pack(side="left", padx=6, fill="x", expand=True)

        # Source Materials List
        s_sep = ctk.CTkFrame(left_col, height=1, fg_color="#27272a")
        s_sep.pack(fill="x", padx=16, pady=10)

        s_head = ctk.CTkFrame(left_col, fg_color="transparent")
        s_head.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(s_head, text="📚 Source Materials", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc").pack(side="left")

        add_src_btn = ctk.CTkButton(
            s_head,
            text="+ Import File",
            command=self._import_source_file,
            width=90,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb"
        )
        add_src_btn.pack(side="right", padx=4)

        add_txt_btn = ctk.CTkButton(
            s_head,
            text="+ Add Notes",
            command=self._prompt_add_text_source,
            width=90,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        add_txt_btn.pack(side="right")

        self.sources_scroll = ctk.CTkScrollableFrame(left_col, fg_color="#09090b", height=140)
        self.sources_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self._render_sources_list()

        # Right Column: Rubric Ingestion & Checklist
        right_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0))

        r_head = ctk.CTkFrame(right_col, fg_color="transparent")
        r_head.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(r_head, text="🎯 Assignment Rubric", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc").pack(side="left")

        snip_btn = ctk.CTkButton(
            r_head,
            text="✂️ Screen-Snip",
            command=self._snip_rubric,
            width=100,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#8b5cf6",
            hover_color="#7c3aed"
        )
        snip_btn.pack(side="right", padx=4)

        upload_rub_btn = ctk.CTkButton(
            r_head,
            text="📂 Upload File",
            command=self._upload_rubric_file,
            width=95,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        upload_rub_btn.pack(side="right")

        self.rubric_raw_textbox = ctk.CTkTextbox(right_col, height=90, fg_color="#09090b")
        self.rubric_raw_textbox.pack(fill="x", padx=16, pady=(0, 6))
        self.rubric_raw_textbox.insert("1.0", "Paste rubric text here or use Screen-Snip / Upload...")

        parse_btn = ctk.CTkButton(
            right_col,
            text="⚡ Parse Rubric into Criteria Checklist",
            command=self._parse_rubric_action,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        parse_btn.pack(fill="x", padx=16, pady=(0, 8))

        # Embedded Checklist Viewer
        self.stage_1_rubric_viewer = RubricViewer(right_col, criteria=self.project.rubric_criteria)
        self.stage_1_rubric_viewer.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # Bottom Action Bar
        bottom_bar = ctk.CTkFrame(self.stage_1_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", pady=(12, 0))

        proceed_btn = ctk.CTkButton(
            bottom_bar,
            text="Proceed to Outline Formulation  →",
            command=lambda: self.show_step(2),
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857"
        )
        proceed_btn.pack(side="right")

    def _on_title_entry_changed(self):
        new_title = self.title_entry.get().strip()
        if new_title:
            self.project.title = new_title
            self.title_display.configure(text=new_title)

    def _import_source_file(self):
        filetypes = [
            ("Supported Documents", "*.pdf *.docx *.doc *.txt *.md"),
            ("PDF Documents", "*.pdf"),
            ("Word Documents", "*.docx *.doc"),
            ("Text Files", "*.txt *.md"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(title="Select Source Document", filetypes=filetypes)
        if not path:
            return

        try:
            content = DocumentImporter.read_file(path)
            name = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower().replace(".", "")
            source = SourceItem(name=name, source_type=ext, content=content, file_path=path)
            self.project.sources.append(source)
            self._render_sources_list()
            logger.info(f"Loaded source file: {name} ({len(content)} chars)")
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not read source file:\n{e}")

    def _prompt_add_text_source(self):
        dialog = ctk.CTkInputDialog(text="Enter source title or short description:", title="Add Free-Text Notes")
        name = dialog.get_input()
        if not name:
            return

        # Simple modal text box
        sub_win = ctk.CTkToplevel(self)
        sub_win.title(f"Enter Notes for '{name}'")
        sub_win.geometry("540x380")
        sub_win.transient(self)
        sub_win.grab_set()

        tb = ctk.CTkTextbox(sub_win, fg_color="#09090b")
        tb.pack(fill="both", expand=True, padx=16, pady=16)

        def save_notes():
            text = tb.get("1.0", "end").strip()
            if text:
                src = SourceItem(name=name, source_type="notes", content=text)
                self.project.sources.append(src)
                self._render_sources_list()
            sub_win.destroy()

        btn = ctk.CTkButton(sub_win, text="Save Notes Source", command=save_notes, fg_color="#2563eb")
        btn.pack(pady=(0, 16))

    def _render_sources_list(self):
        for w in self.sources_scroll.winfo_children():
            w.destroy()

        if not self.project.sources:
            lbl = ctk.CTkLabel(self.sources_scroll, text="No sources imported yet.", text_color="#71717a")
            lbl.pack(pady=20)
            return

        for src in self.project.sources:
            row = ctk.CTkFrame(self.sources_scroll, fg_color="#18181b", corner_radius=6, border_width=1, border_color="#27272a")
            row.pack(fill="x", pady=2, padx=2)

            icon = "📄" if src.source_type in ["pdf", "docx", "doc"] else "📝"
            words = len(src.content.split())
            ctk.CTkLabel(row, text=f"{icon} {src.name} (~{words} words)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1f5f9").pack(side="left", padx=8, pady=4)

            def del_src(s=src):
                self.project.sources.remove(s)
                self._render_sources_list()

            del_btn = ctk.CTkButton(row, text="✕", width=24, height=20, fg_color="#450a0a", hover_color="#7f1d1d", command=del_src)
            del_btn.pack(side="right", padx=6)

    def _upload_rubric_file(self):
        filetypes = [
            ("Supported Documents", "*.pdf *.docx *.doc *.txt"),
            ("PDF Documents", "*.pdf"),
            ("Word Documents", "*.docx *.doc"),
            ("Text Files", "*.txt"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(title="Select Rubric File", filetypes=filetypes)
        if not path:
            return

        try:
            content = DocumentImporter.read_file(path)
            self.rubric_raw_textbox.delete("1.0", "end")
            self.rubric_raw_textbox.insert("1.0", content)
            self._parse_rubric_action()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load rubric file:\n{e}")

    def _snip_rubric(self):
        """Opens snipping overlay to crop rubric area from screen."""
        self.withdraw()  # Temporarily hide workspace for clean snip

        def on_snip(region):
            self.deiconify()
            t = threading.Thread(target=self._process_snipped_rubric, args=(region,), daemon=True)
            t.start()

        self.snipping_overlay = SnippingOverlay(master=self.master, on_snip_complete=on_snip)
        self.snipping_overlay.start()

    def _process_snipped_rubric(self, region):
        try:
            sc = ScreenCapture()
            b64, w, h, _, _, _, _ = sc.capture_and_encode(region=region)

            if self.ai_client:
                ocr_text = self.ai_client.extract_text_from_image(
                    base64_image=b64,
                    prompt="Extract all grading criteria, guidelines, and point values from this rubric screenshot verbatim."
                )
                self.after(0, lambda: self._apply_snipped_rubric_text(ocr_text))
            else:
                self.after(0, lambda: messagebox.showwarning("Notice", "AI Client not configured for OCR extraction."))
        except Exception as e:
            logger.error(f"Error snipping rubric: {e}")
            self.after(0, lambda: messagebox.showerror("Snip Error", f"Could not extract rubric from snip: {e}"))

    def _apply_snipped_rubric_text(self, text: str):
        self.rubric_raw_textbox.delete("1.0", "end")
        self.rubric_raw_textbox.insert("1.0", text)
        self._parse_rubric_action()

    def _parse_rubric_action(self):
        text = self.rubric_raw_textbox.get("1.0", "end").strip()
        if not text:
            return

        def task():
            criteria = self.engine.parse_rubric(text)
            self.after(0, lambda: self._finish_rubric_parse(criteria))

        threading.Thread(target=task, daemon=True).start()

    def _finish_rubric_parse(self, criteria: List[RubricCriterion]):
        self.project.rubric_criteria = criteria
        self.stage_1_rubric_viewer.set_criteria(criteria)

    # -------------------------------------------------------------------------
    # Stage 2: Outline Formulation & Plan
    # -------------------------------------------------------------------------

    def _build_stage_2_ui(self):
        grid = ctk.CTkFrame(self.stage_2_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)

        # Left Column: Outline Editor
        left_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        o_header = ctk.CTkFrame(left_col, fg_color="transparent")
        o_header.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(o_header, text="📑 Document Outline & Section Plan", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc").pack(side="left")

        gen_out_btn = ctk.CTkButton(
            o_header,
            text="⚡ AI Auto-Generate Outline",
            command=self._generate_outline_action,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb"
        )
        gen_out_btn.pack(side="right", padx=4)

        add_sec_btn = ctk.CTkButton(
            o_header,
            text="+ Add Section",
            command=self._add_manual_section,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        add_sec_btn.pack(side="right")

        self.outline_scroll = ctk.CTkScrollableFrame(left_col, fg_color="#09090b")
        self.outline_scroll.pack(fill="both", expand=True, padx=16, pady=(6, 10))

        # Outline word count summary bar
        self.outline_stats_bar = ctk.CTkLabel(
            left_col,
            text="Total Outline Words: 0 / Target: 1000",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.outline_stats_bar.pack(anchor="w", padx=16, pady=(0, 12))

        # Right Column: Rubric Reference Viewer
        right_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        right_col.pack(side="right", fill="both", width=340, padx=(8, 0))

        self.stage_2_rubric_viewer = RubricViewer(right_col, criteria=self.project.rubric_criteria)
        self.stage_2_rubric_viewer.pack(fill="both", expand=True, padx=12, pady=12)

        # Bottom Bar
        bottom_bar = ctk.CTkFrame(self.stage_2_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", pady=(12, 0))

        back_btn = ctk.CTkButton(
            bottom_bar,
            text="← Back to Rubrics & Sources",
            command=lambda: self.show_step(1),
            height=40,
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        back_btn.pack(side="left")

        proceed_btn = ctk.CTkButton(
            bottom_bar,
            text="Proceed to Section Drafting & Review  →",
            command=lambda: self.show_step(3),
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857"
        )
        proceed_btn.pack(side="right")

    def _sync_stage_2_data(self):
        # Update metadata from step 1 fields
        self.project.topic_description = self.topic_textbox.get("1.0", "end").strip()
        try:
            self.project.target_total_words = int(self.words_entry.get().strip())
        except ValueError:
            pass
        self.project.author_name = self.author_entry.get().strip()
        self.project.course_name = self.course_entry.get().strip()
        self.project.instructor_name = self.instructor_entry.get().strip()

        self.stage_2_rubric_viewer.set_criteria(self.project.rubric_criteria)
        self._render_outline_list()

    def _generate_outline_action(self):
        def task():
            sections = self.engine.generate_outline(self.project)
            self.after(0, lambda: self._finish_outline_gen(sections))

        threading.Thread(target=task, daemon=True).start()

    def _finish_outline_gen(self, sections: List[SectionDraft]):
        self.project.sections = sections
        self._render_outline_list()

    def _add_manual_section(self):
        new_sec = SectionDraft(
            title=f"Section {len(self.project.sections) + 1}",
            goal_summary="Describe section objective and arguments...",
            target_word_count=250,
        )
        self.project.sections.append(new_sec)
        self._render_outline_list()

    def _render_outline_list(self):
        for w in self.outline_scroll.winfo_children():
            w.destroy()

        if not self.project.sections:
            lbl = ctk.CTkLabel(
                self.outline_scroll,
                text="No outline sections defined yet.\nClick 'AI Auto-Generate Outline' or '+ Add Section'.",
                font=ctk.CTkFont(size=12),
                text_color="#71717a"
            )
            lbl.pack(pady=40)
            self.outline_stats_bar.configure(text=f"Total Outline Words: 0 / Target: {self.project.target_total_words}")
            return

        total_words = 0
        for i, sec in enumerate(self.project.sections):
            total_words += sec.target_word_count

            card = ctk.CTkFrame(self.outline_scroll, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
            card.pack(fill="x", pady=6, padx=4)

            # Top row: number, title entry, target words entry, delete button
            top_r = ctk.CTkFrame(card, fg_color="transparent")
            top_r.pack(fill="x", padx=10, pady=(8, 4))

            ctk.CTkLabel(top_r, text=f"{i+1}.", font=ctk.CTkFont(size=13, weight="bold"), text_color="#38bdf8").pack(side="left", padx=(0, 6))

            t_entry = ctk.CTkEntry(top_r, font=ctk.CTkFont(size=12, weight="bold"))
            t_entry.insert(0, sec.title)
            t_entry.pack(side="left", fill="x", expand=True, padx=4)

            def update_t(e, s=sec, ent=t_entry):
                s.title = ent.get().strip()

            t_entry.bind("<KeyRelease>", update_t)

            ctk.CTkLabel(top_r, text="Words:", text_color="#94a3b8", font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
            w_entry = ctk.CTkEntry(top_r, width=60)
            w_entry.insert(0, str(sec.target_word_count))
            w_entry.pack(side="left", padx=4)

            def update_w(e, s=sec, ent=w_entry):
                try:
                    s.target_word_count = int(ent.get().strip())
                    self._update_outline_totals()
                except ValueError:
                    pass

            w_entry.bind("<KeyRelease>", update_w)

            # Move Up/Down buttons
            if i > 0:
                up_btn = ctk.CTkButton(top_r, text="▲", width=22, height=22, fg_color="#27272a", command=lambda idx=i: self._move_section(idx, -1))
                up_btn.pack(side="left", padx=2)
            if i < len(self.project.sections) - 1:
                dn_btn = ctk.CTkButton(top_r, text="▼", width=22, height=22, fg_color="#27272a", command=lambda idx=i: self._move_section(idx, 1))
                dn_btn.pack(side="left", padx=2)

            del_btn = ctk.CTkButton(top_r, text="✕", width=24, height=22, fg_color="#450a0a", hover_color="#7f1d1d", command=lambda s=sec: self._delete_section(s))
            del_btn.pack(side="left", padx=(6, 0))

            # Goal summary textbox
            g_box = ctk.CTkTextbox(card, height=48, fg_color="#09090b", font=ctk.CTkFont(size=11))
            g_box.pack(fill="x", padx=10, pady=(0, 8))
            g_box.insert("1.0", sec.goal_summary)

            def update_g(e, s=sec, box=g_box):
                s.goal_summary = box.get("1.0", "end").strip()

            g_box.bind("<KeyRelease>", update_g)

        self._update_outline_totals()

    def _move_section(self, index: int, delta: int):
        new_idx = index + delta
        if 0 <= new_idx < len(self.project.sections):
            self.project.sections[index], self.project.sections[new_idx] = self.project.sections[new_idx], self.project.sections[index]
            self._render_outline_list()

    def _delete_section(self, section: SectionDraft):
        self.project.sections.remove(section)
        self._render_outline_list()

    def _update_outline_totals(self):
        total = sum(s.target_word_count for s in self.project.sections)
        self.outline_stats_bar.configure(
            text=f"Total Outline Target: {total} words / Project Goal: {self.project.target_total_words} words"
        )

    # -------------------------------------------------------------------------
    # Stage 3: Section Drafting & Humanizing with Interactive User Review
    # -------------------------------------------------------------------------

    def _build_stage_3_ui(self):
        # Top bar: Section selector & approval indicator
        top_ctrl = ctk.CTkFrame(self.stage_3_frame, fg_color="#18181b", corner_radius=8, height=48)
        top_ctrl.pack(fill="x", pady=(0, 8))

        self.sec_prev_btn = ctk.CTkButton(top_ctrl, text="◀ Prev", width=70, height=30, fg_color="#27272a", command=self._prev_section)
        self.sec_prev_btn.pack(side="left", padx=(12, 6), pady=8)

        self.sec_menu = ctk.CTkOptionMenu(
            top_ctrl,
            values=["(No Sections)"],
            command=self._on_section_selected,
            width=280,
            height=30,
            fg_color="#27272a"
        )
        self.sec_menu.pack(side="left", padx=6, pady=8)

        self.sec_next_btn = ctk.CTkButton(top_ctrl, text="Next ▶", width=70, height=30, fg_color="#27272a", command=self._next_section)
        self.sec_next_btn.pack(side="left", padx=6, pady=8)

        self.approval_badge = ctk.CTkLabel(
            top_ctrl,
            text="PENDING REVIEW",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#f59e0b",
            fg_color="#451a03",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.approval_badge.pack(side="left", padx=12)

        # Right side of top bar: Drafting and Humanizing controls
        self.tone_menu = ctk.CTkOptionMenu(
            top_ctrl,
            values=["Academic", "Casual", "Neutral", "Professional"],
            width=110,
            height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a"
        )
        self.tone_menu.set("Academic")
        self.tone_menu.pack(side="right", padx=(4, 12), pady=8)

        self.rehumanize_btn = ctk.CTkButton(
            top_ctrl,
            text="✨ Re-Humanize",
            command=self._rehumanize_current_section,
            width=115,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#6366f1",
            hover_color="#4f46e5"
        )
        self.rehumanize_btn.pack(side="right", padx=4, pady=8)

        self.draft_ai_btn = ctk.CTkButton(
            top_ctrl,
            text="⚡ Draft Section with AI",
            command=self._draft_active_section,
            width=160,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        self.draft_ai_btn.pack(side="right", padx=4, pady=8)

        # Section Info bar (Goal & Target Words)
        self.sec_info_bar = ctk.CTkFrame(self.stage_3_frame, fg_color="transparent")
        self.sec_info_bar.pack(fill="x", padx=4, pady=(0, 6))

        self.sec_goal_label = ctk.CTkLabel(
            self.sec_info_bar,
            text="Goal: ...",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8",
            wraplength=800,
            justify="left"
        )
        self.sec_goal_label.pack(side="left")

        self.sec_word_label = ctk.CTkLabel(
            self.sec_info_bar,
            text="Words: 0 / 250",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.sec_word_label.pack(side="right")

        # Side-by-Side Review Panels
        panels = ctk.CTkFrame(self.stage_3_frame, fg_color="transparent")
        panels.pack(fill="both", expand=True)

        # Left Panel: Raw AI Draft (Reference)
        left_p = ctk.CTkFrame(panels, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
        left_p.pack(side="left", fill="both", expand=True, padx=(0, 6))

        l_head = ctk.CTkLabel(left_p, text="🤖 Raw AI Generation", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8")
        l_head.pack(anchor="w", padx=12, pady=(10, 4))

        self.raw_text_box = ctk.CTkTextbox(left_p, fg_color="#09090b", font=ctk.CTkFont(size=13))
        self.raw_text_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Right Panel: Humanized & Polished Draft (Directly Editable by User!)
        right_p = ctk.CTkFrame(panels, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
        right_p.pack(side="right", fill="both", expand=True, padx=(6, 0))

        r_head = ctk.CTkFrame(right_p, fg_color="transparent")
        r_head.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(r_head, text="✍️ Humanized & Final Text (Editable)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#34d399").pack(side="left")

        self.humanizer_status_badge = ctk.CTkLabel(
            r_head,
            text="Jade's AI Humanizer",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#a855f7"
        )
        self.humanizer_status_badge.pack(side="right")

        self.final_text_box = ctk.CTkTextbox(right_p, fg_color="#09090b", font=ctk.CTkFont(size=13))
        self.final_text_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.final_text_box.bind("<KeyRelease>", self._on_final_text_edited)

        # AI Refine Box
        refine_frame = ctk.CTkFrame(self.stage_3_frame, fg_color="#18181b", corner_radius=8, height=44)
        refine_frame.pack(fill="x", pady=6)

        ctk.CTkLabel(refine_frame, text="💬 Refine Draft:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#cbd5e1").pack(side="left", padx=(12, 6), pady=8)

        self.refine_entry = ctk.CTkEntry(
            refine_frame,
            placeholder_text="Enter instructions (e.g. 'Expand paragraph 2 with historical context', 'Tone down academic jargon')...",
            font=ctk.CTkFont(size=12)
        )
        self.refine_entry.pack(side="left", fill="x", expand=True, padx=6, pady=8)
        self.refine_entry.bind("<Return>", lambda e: self._refine_active_section())

        self.refine_btn = ctk.CTkButton(
            refine_frame,
            text="Apply Refinement",
            command=self._refine_active_section,
            width=130,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb"
        )
        self.refine_btn.pack(side="left", padx=(4, 12), pady=8)

        # Bottom Bar: Navigation and Approve & Next Action
        bottom_bar = ctk.CTkFrame(self.stage_3_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", pady=(6, 0))

        back_btn = ctk.CTkButton(
            bottom_bar,
            text="← Back to Outline",
            command=lambda: self.show_step(2),
            height=40,
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        back_btn.pack(side="left")

        self.approve_btn = ctk.CTkButton(
            bottom_bar,
            text="✓ Approve Section & Next  →",
            command=self._approve_and_next_section,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857"
        )
        self.approve_btn.pack(side="right")

    def _sync_stage_3_data(self):
        if not self.project.sections:
            self.sec_menu.configure(values=["(No Sections Defined)"])
            self.sec_menu.set("(No Sections Defined)")
            return

        names = [f"{i+1}. {s.title}" for i, s in enumerate(self.project.sections)]
        self.sec_menu.configure(values=names)

        if self.current_section_idx >= len(self.project.sections):
            self.current_section_idx = 0

        self.sec_menu.set(names[self.current_section_idx])
        self._load_active_section_into_editor()

    def _on_section_selected(self, choice: str):
        for i, s in enumerate(self.project.sections):
            if f"{i+1}. {s.title}" == choice:
                self.current_section_idx = i
                break
        self._load_active_section_into_editor()

    def _prev_section(self):
        if self.current_section_idx > 0:
            self.current_section_idx -= 1
            names = [f"{i+1}. {s.title}" for i, s in enumerate(self.project.sections)]
            self.sec_menu.set(names[self.current_section_idx])
            self._load_active_section_into_editor()

    def _next_section(self):
        if self.current_section_idx < len(self.project.sections) - 1:
            self.current_section_idx += 1
            names = [f"{i+1}. {s.title}" for i, s in enumerate(self.project.sections)]
            self.sec_menu.set(names[self.current_section_idx])
            self._load_active_section_into_editor()

    def _load_active_section_into_editor(self):
        if not self.project.sections or self.current_section_idx >= len(self.project.sections):
            return

        sec = self.project.sections[self.current_section_idx]
        self.sec_goal_label.configure(text=f"Goal: {sec.goal_summary}")

        # Update text areas
        self.raw_text_box.delete("1.0", "end")
        self.raw_text_box.insert("1.0", sec.raw_ai_text)

        self.final_text_box.delete("1.0", "end")
        self.final_text_box.insert("1.0", sec.get_active_text())

        # Update word count and approval status
        words = len(sec.get_active_text().split()) if sec.get_active_text().strip() else 0
        self.sec_word_label.configure(text=f"Words: {words} / {sec.target_word_count}")

        if sec.is_approved:
            self.approval_badge.configure(
                text="✓ APPROVED",
                text_color="#34d399",
                fg_color="#064e3b"
            )
        else:
            self.approval_badge.configure(
                text="PENDING REVIEW",
                text_color="#f59e0b",
                fg_color="#451a03"
            )

    def _on_final_text_edited(self, event=None):
        if not self.project.sections or self.current_section_idx >= len(self.project.sections):
            return
        sec = self.project.sections[self.current_section_idx]
        text = self.final_text_box.get("1.0", "end").strip()
        sec.final_text = text
        words = len(text.split()) if text else 0
        self.sec_word_label.configure(text=f"Words: {words} / {sec.target_word_count}")

    def _draft_active_section(self):
        if not self.project.sections:
            return

        sec = self.project.sections[self.current_section_idx]
        self.draft_ai_btn.configure(text="⏳ Drafting...", state="disabled")

        tone = self.tone_menu.get().lower()

        def task():
            self.engine.draft_section(
                project=self.project,
                section=sec,
                humanizer_bridge=self.humanizer_bridge,
                auto_humanize=True,
            )
            self.after(0, self._finish_draft_active_section)

        threading.Thread(target=task, daemon=True).start()

    def _finish_draft_active_section(self):
        self.draft_ai_btn.configure(text="⚡ Draft Section with AI", state="normal")
        self._load_active_section_into_editor()

    def _rehumanize_current_section(self):
        if not self.project.sections:
            return

        sec = self.project.sections[self.current_section_idx]
        text_to_humanize = self.final_text_box.get("1.0", "end").strip() or sec.raw_ai_text
        if not text_to_humanize:
            return

        self.rehumanize_btn.configure(text="✨ Tuning...", state="disabled")
        tone = self.tone_menu.get().lower()

        def task():
            res = self.humanizer_bridge.humanize_text(
                text=text_to_humanize,
                tone=tone,
            )
            h_text = res.get("humanized_text", text_to_humanize)
            sec.humanized_text = h_text
            sec.final_text = h_text
            self.after(0, self._finish_rehumanize)

        threading.Thread(target=task, daemon=True).start()

    def _finish_rehumanize(self):
        self.rehumanize_btn.configure(text="✨ Re-Humanize", state="normal")
        self._load_active_section_into_editor()

    def _refine_active_section(self):
        instructions = self.refine_entry.get().strip()
        if not instructions or not self.project.sections:
            return

        sec = self.project.sections[self.current_section_idx]
        # Save any inline changes made prior to refining
        sec.final_text = self.final_text_box.get("1.0", "end").strip()

        self.refine_btn.configure(text="⏳ Refining...", state="disabled")

        def task():
            self.engine.refine_section(
                project=self.project,
                section=sec,
                user_instructions=instructions,
                humanizer_bridge=self.humanizer_bridge,
                auto_humanize=True,
            )
            self.after(0, self._finish_refine)

        threading.Thread(target=task, daemon=True).start()

    def _finish_refine(self):
        self.refine_btn.configure(text="Apply Refinement", state="normal")
        self.refine_entry.delete(0, "end")
        self._load_active_section_into_editor()

    def _approve_and_next_section(self):
        if not self.project.sections:
            return

        sec = self.project.sections[self.current_section_idx]
        sec.final_text = self.final_text_box.get("1.0", "end").strip()
        sec.is_approved = True

        # Check off any mapped criteria
        for c_id in sec.criteria_ids:
            for c in self.project.rubric_criteria:
                if c.id == c_id:
                    c.fulfilled = True

        self._load_active_section_into_editor()

        # Advance to next section or step 4 if completed
        if self.current_section_idx < len(self.project.sections) - 1:
            self._next_section()
        else:
            messagebox.showinfo("Project Complete", "All sections drafted and reviewed! Proceeding to document export.")
            self.show_step(4)

    # -------------------------------------------------------------------------
    # Stage 4: Document Compilation & .docx Export
    # -------------------------------------------------------------------------

    def _build_stage_4_ui(self):
        grid = ctk.CTkFrame(self.stage_4_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True)

        # Left Column: Compiled Document Preview
        left_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        d_head = ctk.CTkLabel(left_col, text="📄 Full Compiled Document Preview", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc")
        d_head.pack(anchor="w", padx=16, pady=(14, 6))

        self.full_doc_preview = ctk.CTkTextbox(left_col, fg_color="#09090b", font=ctk.CTkFont(size=13))
        self.full_doc_preview.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # Right Column: Export Settings & Works Cited
        right_col = ctk.CTkFrame(grid, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        right_col.pack(side="right", fill="both", width=360, padx=(8, 0))

        e_head = ctk.CTkLabel(right_col, text="⚙️ Export Configuration", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc")
        e_head.pack(anchor="w", padx=16, pady=(14, 10))

        # Stats summary card
        self.export_stats_frame = ctk.CTkFrame(right_col, fg_color="#09090b", corner_radius=8)
        self.export_stats_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.export_words_lbl = ctk.CTkLabel(self.export_stats_frame, text="Total Words: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8")
        self.export_words_lbl.pack(anchor="w", padx=12, pady=(8, 2))

        self.export_criteria_lbl = ctk.CTkLabel(self.export_stats_frame, text="Rubric Criteria Met: 0 / 0", font=ctk.CTkFont(size=12), text_color="#34d399")
        self.export_criteria_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        # Format Style selector
        ctk.CTkLabel(right_col, text="Document Formatting Preset:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=16, pady=(6, 2))
        self.stage_4_format_menu = ctk.CTkOptionMenu(
            right_col,
            values=["MLA", "APA", "Standard Report"],
            command=self._on_format_changed,
            fg_color="#27272a"
        )
        self.stage_4_format_menu.set(self.project.formatting_preset)
        self.stage_4_format_menu.pack(fill="x", padx=16, pady=(0, 10))

        # Bibliography / Works Cited entries
        ctk.CTkLabel(right_col, text="Works Cited / References:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=16, pady=(6, 2))
        self.biblio_textbox = ctk.CTkTextbox(right_col, height=120, fg_color="#09090b", font=ctk.CTkFont(size=11))
        self.biblio_textbox.pack(fill="x", padx=16, pady=(0, 10))
        self.biblio_textbox.insert("1.0", "Paste MLA/APA citations here (one per line)...")

        # Big Export Button
        export_docx_btn = ctk.CTkButton(
            right_col,
            text="📥 Export to Word Document (.docx)",
            command=self._export_to_docx_action,
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        export_docx_btn.pack(fill="x", padx=16, pady=(10, 8))

        # Bottom Bar
        bottom_bar = ctk.CTkFrame(self.stage_4_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", pady=(12, 0))

        back_btn = ctk.CTkButton(
            bottom_bar,
            text="← Back to Section Review",
            command=lambda: self.show_step(3),
            height=40,
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        back_btn.pack(side="left")

    def _sync_stage_4_data(self):
        full_text = self.project.get_full_document_text()
        self.full_doc_preview.delete("1.0", "end")
        self.full_doc_preview.insert("1.0", full_text)

        total_words = self.project.total_word_count()
        self.export_words_lbl.configure(text=f"Total Words: {total_words} (Target: {self.project.target_total_words})")

        fulfilled = sum(1 for c in self.project.rubric_criteria if c.fulfilled)
        self.export_criteria_lbl.configure(text=f"Rubric Criteria Met: {fulfilled} / {len(self.project.rubric_criteria)}")

        self.stage_4_format_menu.set(self.project.formatting_preset)

    def _export_to_docx_action(self):
        default_name = f"{self.project.title.replace(' ', '_')}_{self.project.formatting_preset}.docx"
        output_path = filedialog.asksaveasfilename(
            title="Export Word Document",
            defaultextension=".docx",
            initialfile=default_name,
            filetypes=[("Word Document", "*.docx")]
        )
        if not output_path:
            return

        # Parse bibliography entries
        bib_raw = self.biblio_textbox.get("1.0", "end").strip()
        bib_lines = [l.strip() for l in bib_raw.splitlines() if l.strip() and not l.startswith("Paste MLA")]

        sections_data = []
        for sec in self.project.sections:
            sections_data.append({
                "title": sec.title,
                "text": sec.get_active_text(),
            })

        try:
            exported_path = DocumentExporter.export_to_docx(
                project_title=self.project.title,
                sections=sections_data,
                output_path=output_path,
                preset=self.project.formatting_preset,
                author_name=self.project.author_name,
                course_name=self.project.course_name,
                instructor_name=self.project.instructor_name,
                bibliography=bib_lines,
            )
            messagebox.showinfo("Export Successful", f"Document exported successfully to:\n{exported_path}")
            # Highlight in Windows Explorer
            os.system(f'explorer /select,"{exported_path}"')
        except Exception as e:
            logger.error(f"Failed to export docx: {e}")
            messagebox.showerror("Export Failed", f"Could not create .docx document:\n{e}")

    # -------------------------------------------------------------------------
    # Save & Open Project
    # -------------------------------------------------------------------------

    def _save_project_dialog(self):
        if not self.current_file_path:
            default_name = f"{self.project.title.replace(' ', '_')}.avaproj"
            self.current_file_path = filedialog.asksaveasfilename(
                title="Save Playground Project",
                defaultextension=".avaproj",
                initialfile=default_name,
                filetypes=[("AVA Project", "*.avaproj"), ("JSON File", "*.json")]
            )
        if self.current_file_path:
            self._save_project_to_path(self.current_file_path)

    def _save_project_to_path(self, path: str):
        try:
            # Sync latest field values
            self.project.topic_description = self.topic_textbox.get("1.0", "end").strip()
            self.project.author_name = self.author_entry.get().strip()
            self.project.course_name = self.course_entry.get().strip()
            self.project.instructor_name = self.instructor_entry.get().strip()

            self.project.save_to_file(path)
            messagebox.showinfo("Saved", f"Project saved to:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save project:\n{e}")

    def _open_project_dialog(self):
        path = filedialog.askopenfilename(
            title="Open Playground Project",
            filetypes=[("AVA Project", "*.avaproj"), ("JSON File", "*.json")]
        )
        if not path:
            return

        try:
            self.project = PlaygroundProject.load_from_file(path)
            self.current_file_path = path

            # Update UI
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, self.project.title)
            self.title_display.configure(text=self.project.title)

            self.topic_textbox.delete("1.0", "end")
            self.topic_textbox.insert("1.0", self.project.topic_description)

            self.words_entry.delete(0, "end")
            self.words_entry.insert(0, str(self.project.target_total_words))

            self.author_entry.delete(0, "end")
            self.author_entry.insert(0, self.project.author_name)

            self.course_entry.delete(0, "end")
            self.course_entry.insert(0, self.project.course_name)

            self.instructor_entry.delete(0, "end")
            self.instructor_entry.insert(0, self.project.instructor_name)

            self.format_menu.set(self.project.formatting_preset)
            self._render_sources_list()
            self.stage_1_rubric_viewer.set_criteria(self.project.rubric_criteria)

            messagebox.showinfo("Project Loaded", f"Successfully loaded project:\n{self.project.title}")
            self.show_step(1)
        except Exception as e:
            messagebox.showerror("Open Error", f"Failed to load project file:\n{e}")

    # -------------------------------------------------------------------------
    # Lifecycle & Exit
    # -------------------------------------------------------------------------

    def _on_close_requested(self):
        # Auto-save session to temporary backup before exiting
        try:
            os.makedirs("projects", exist_ok=True)
            self.project.save_to_file("projects/last_session.avaproj")
        except Exception:
            pass

        self.destroy()
        if self.on_exit:
            self.on_exit()
