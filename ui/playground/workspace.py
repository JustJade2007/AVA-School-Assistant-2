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
from core.playground.teacher_evaluator import TeacherEvaluator
from core.playground.metadata_manager import AcademicMetadataManager
from core.written_solver import WrittenSolver
from core.playground.web_source import WebSourceIngestor, CitationGenerator
from ui.playground.rubric_viewer import RubricViewer
from ui.snipping_tool import SnippingOverlay
from ui.asset_loader import apply_window_icon, get_logo_ctk_image

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
        self.metadata_mgr = AcademicMetadataManager(config_manager=self.config_manager)
        self.humanizer_bridge = PlaygroundHumanizerBridge(
            api_key=self.config.gemini_api_key or self.config.api_key if self.config else "",
            model_name=self.config.written_model_name if self.config else "gemini-3.5-flash-lite",
            default_tone=self.config.humanizer_tone if self.config else "academic",
            default_level=self.config.humanizer_reading_level if self.config else "college",
            default_mode=self.config.humanizer_mode if self.config else "budget",
        )
        self.engine = PlaygroundEngine(ai_client=self.ai_client, config_manager=self.config_manager)
        self.teacher_evaluator = TeacherEvaluator(ai_client=self.ai_client, config_manager=self.config_manager)
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
        apply_window_icon(self)
        self.attributes("-topmost", False)
        self.lift()
        self.focus_force()

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

        self.logo_img = get_logo_ctk_image(size=(28, 28))
        if self.logo_img:
            self.logo_icon_lbl = ctk.CTkLabel(left_box, text="", image=self.logo_img)
            self.logo_icon_lbl.pack(side="left", padx=(0, 8))

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

        # Right: Cloak toggle, Start Over, Save/Open dropdown, and Return to Home
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=16, pady=8)

        self.cloak_btn = ctk.CTkButton(
            right_box,
            text="🛡️ Cloaked",
            command=self._toggle_cloak,
            width=100,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1
        )
        self.cloak_btn.pack(side="left", padx=4)

        start_over_btn = ctk.CTkButton(
            right_box,
            text="🔄 Start Over",
            command=self._start_over_dialog,
            width=90,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        start_over_btn.pack(side="left", padx=4)

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

        self.open_recent_menu = ctk.CTkOptionMenu(
            right_box,
            values=self._get_recent_projects_list(),
            command=self._on_recent_project_selected,
            width=140,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            button_color="#3f3f46",
            button_hover_color="#52525b"
        )
        self.open_recent_menu.set("📂 Open Recent ▾")
        self.open_recent_menu.pack(side="left", padx=4)

        exit_btn = ctk.CTkButton(
            right_box,
            text="🏠 Home",
            command=self._on_close_requested,
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#991b1b",
            hover_color="#b91c1c",
            text_color="#fef2f2"
        )
        exit_btn.pack(side="left", padx=(6, 0))

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
        self.topic_textbox.bind("<KeyRelease>", lambda e: self._on_topic_changed())

        # Target Word Count row
        word_row = ctk.CTkFrame(left_col, fg_color="transparent")
        word_row.pack(fill="x", padx=16, pady=(4, 2))
        ctk.CTkLabel(word_row, text="Target Words:", text_color="#94a3b8", width=80, anchor="w").pack(side="left")
        self.words_entry = ctk.CTkEntry(word_row, width=80)
        self.words_entry.insert(0, str(self.project.target_total_words))
        self.words_entry.pack(side="left", padx=(0, 8))

        self.detected_words_label = ctk.CTkLabel(
            word_row,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#38bdf8"
        )
        self.detected_words_label.pack(side="left", padx=4)

        # Academic Metadata Rows: Author, Course, Professor (Saved, Loaded, Deleted separately)
        # 1. Author Name
        author_row = ctk.CTkFrame(left_col, fg_color="transparent")
        author_row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(author_row, text="Author:", text_color="#94a3b8", width=80, anchor="w").pack(side="left")
        self.author_entry = ctk.CTkEntry(author_row, placeholder_text="Student / Author Name")
        self.author_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.author_entry.insert(0, self.project.author_name)

        self.author_menu = ctk.CTkOptionMenu(
            author_row,
            values=self._get_author_menu_values(),
            command=self._on_author_selected,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            button_color="#3f3f46",
            button_hover_color="#52525b"
        )
        self.author_menu.set("📂 Load ▾")
        self.author_menu.pack(side="left", padx=(0, 4))

        self.author_save_btn = ctk.CTkButton(
            author_row,
            text="💾 Save",
            command=self._save_author_action,
            width=54,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669"
        )
        self.author_save_btn.pack(side="left", padx=(0, 4))

        self.author_del_btn = ctk.CTkButton(
            author_row,
            text="🗑️",
            command=self._delete_author_action,
            width=32,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#ef4444",
            hover_color="#dc2626"
        )
        self.author_del_btn.pack(side="left")

        # 2. Course Title
        course_row = ctk.CTkFrame(left_col, fg_color="transparent")
        course_row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(course_row, text="Course:", text_color="#94a3b8", width=80, anchor="w").pack(side="left")
        self.course_entry = ctk.CTkEntry(course_row, placeholder_text="e.g. ENGL 101 - Academic Writing")
        self.course_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.course_entry.insert(0, self.project.course_name)

        self.course_menu = ctk.CTkOptionMenu(
            course_row,
            values=self._get_course_menu_values(),
            command=self._on_course_selected,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            button_color="#3f3f46",
            button_hover_color="#52525b"
        )
        self.course_menu.set("📂 Load ▾")
        self.course_menu.pack(side="left", padx=(0, 4))

        self.course_save_btn = ctk.CTkButton(
            course_row,
            text="💾 Save",
            command=self._save_course_action,
            width=54,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669"
        )
        self.course_save_btn.pack(side="left", padx=(0, 4))

        self.course_del_btn = ctk.CTkButton(
            course_row,
            text="🗑️",
            command=self._delete_course_action,
            width=32,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#ef4444",
            hover_color="#dc2626"
        )
        self.course_del_btn.pack(side="left")

        # 3. Professor / Instructor Name
        inst_row = ctk.CTkFrame(left_col, fg_color="transparent")
        inst_row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(inst_row, text="Professor:", text_color="#94a3b8", width=80, anchor="w").pack(side="left")
        self.instructor_entry = ctk.CTkEntry(inst_row, placeholder_text="e.g. Dr. Robert Vance")
        self.instructor_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.instructor_entry.insert(0, self.project.instructor_name)

        self.instructor_menu = ctk.CTkOptionMenu(
            inst_row,
            values=self._get_instructor_menu_values(),
            command=self._on_instructor_selected,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#27272a",
            button_color="#3f3f46",
            button_hover_color="#52525b"
        )
        self.instructor_menu.set("📂 Load ▾")
        self.instructor_menu.pack(side="left", padx=(0, 4))

        self.instructor_save_btn = ctk.CTkButton(
            inst_row,
            text="💾 Save",
            command=self._save_instructor_action,
            width=54,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669"
        )
        self.instructor_save_btn.pack(side="left", padx=(0, 4))

        self.instructor_del_btn = ctk.CTkButton(
            inst_row,
            text="🗑️",
            command=self._delete_instructor_action,
            width=32,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#ef4444",
            hover_color="#dc2626"
        )
        self.instructor_del_btn.pack(side="left")

        # Source Materials List
        s_sep = ctk.CTkFrame(left_col, height=1, fg_color="#27272a")
        s_sep.pack(fill="x", padx=16, pady=10)

        s_head = ctk.CTkFrame(left_col, fg_color="transparent")
        s_head.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(s_head, text="📚 Source Materials", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc").pack(side="left")

        add_web_btn = ctk.CTkButton(
            s_head,
            text="🌐 + Web Link",
            command=self._prompt_add_web_source,
            width=90,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1"
        )
        add_web_btn.pack(side="right", padx=4)

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
            width=85,
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
        self.rubric_raw_textbox.bind("<KeyRelease>", lambda e: self._auto_detect_word_requirements())

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
        self.stage_1_rubric_viewer = RubricViewer(
            right_col,
            criteria=self.project.rubric_criteria,
            on_criteria_changed=self._on_rubric_criteria_changed
        )
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

    # -------------------------------------------------------------------------
    # Academic Metadata Presets: Author, Course, Professor
    # (Saved, Loaded, and Deleted all separately)
    # -------------------------------------------------------------------------

    # --- Author Presets ---
    def _get_author_menu_values(self) -> List[str]:
        saved = self.metadata_mgr.get_authors() if hasattr(self, "metadata_mgr") else []
        items = ["📂 Load ▾"]
        if saved:
            for a in saved:
                items.append(a)
            items.append("🗑️ Manage / Delete...")
        else:
            items.append("(No saved authors)")
        return items

    def _refresh_author_menu(self):
        if hasattr(self, "author_menu"):
            self.author_menu.configure(values=self._get_author_menu_values())
            self.author_menu.set("📂 Load ▾")

    def _on_author_selected(self, choice: str):
        self.author_menu.set("📂 Load ▾")
        if choice == "🗑️ Manage / Delete...":
            self._open_delete_modal("Author", self.metadata_mgr.get_authors(), self._delete_author)
        elif choice not in ("📂 Load ▾", "(No saved authors)"):
            self.author_entry.delete(0, "end")
            self.author_entry.insert(0, choice)
            self.project.author_name = choice

    def _save_author_action(self):
        val = self.author_entry.get().strip()
        if not val:
            messagebox.showwarning("Empty Author", "Please enter an Author Name before saving.", parent=self)
            return
        self.metadata_mgr.save_author(val)
        self._refresh_author_menu()
        messagebox.showinfo("Author Saved", f"Author Name '{val}' saved to presets!", parent=self)

    def _delete_author_action(self):
        saved = self.metadata_mgr.get_authors()
        if not saved:
            messagebox.showinfo("No Saved Authors", "You don't have any saved author names yet.", parent=self)
            return
        current = self.author_entry.get().strip()
        if current and current in saved:
            if messagebox.askyesno("Delete Saved Author", f"Remove '{current}' from saved authors?", parent=self):
                self._delete_author(current)
                messagebox.showinfo("Deleted", f"Removed '{current}' from saved authors.", parent=self)
        else:
            self._open_delete_modal("Author", saved, self._delete_author)

    def _delete_author(self, name: str):
        self.metadata_mgr.delete_author(name)
        self._refresh_author_menu()
        if self.author_entry.get().strip() == name:
            self.author_entry.delete(0, "end")
            self.project.author_name = ""

    # --- Course Presets ---
    def _get_course_menu_values(self) -> List[str]:
        saved = self.metadata_mgr.get_courses() if hasattr(self, "metadata_mgr") else []
        items = ["📂 Load ▾"]
        if saved:
            for c in saved:
                items.append(c)
            items.append("🗑️ Manage / Delete...")
        else:
            items.append("(No saved courses)")
        return items

    def _refresh_course_menu(self):
        if hasattr(self, "course_menu"):
            self.course_menu.configure(values=self._get_course_menu_values())
            self.course_menu.set("📂 Load ▾")

    def _on_course_selected(self, choice: str):
        self.course_menu.set("📂 Load ▾")
        if choice == "🗑️ Manage / Delete...":
            self._open_delete_modal("Course", self.metadata_mgr.get_courses(), self._delete_course)
        elif choice not in ("📂 Load ▾", "(No saved courses)"):
            self.course_entry.delete(0, "end")
            self.course_entry.insert(0, choice)
            self.project.course_name = choice

    def _save_course_action(self):
        val = self.course_entry.get().strip()
        if not val:
            messagebox.showwarning("Empty Course", "Please enter a Course Title before saving.", parent=self)
            return
        self.metadata_mgr.save_course(val)
        self._refresh_course_menu()
        messagebox.showinfo("Course Saved", f"Course Title '{val}' saved to presets!", parent=self)

    def _delete_course_action(self):
        saved = self.metadata_mgr.get_courses()
        if not saved:
            messagebox.showinfo("No Saved Courses", "You don't have any saved courses yet.", parent=self)
            return
        current = self.course_entry.get().strip()
        if current and current in saved:
            if messagebox.askyesno("Delete Saved Course", f"Remove '{current}' from saved courses?", parent=self):
                self._delete_course(current)
                messagebox.showinfo("Deleted", f"Removed '{current}' from saved courses.", parent=self)
        else:
            self._open_delete_modal("Course", saved, self._delete_course)

    def _delete_course(self, name: str):
        self.metadata_mgr.delete_course(name)
        self._refresh_course_menu()
        if self.course_entry.get().strip() == name:
            self.course_entry.delete(0, "end")
            self.project.course_name = ""

    # --- Professor Presets ---
    def _get_instructor_menu_values(self) -> List[str]:
        saved = self.metadata_mgr.get_professors() if hasattr(self, "metadata_mgr") else []
        items = ["📂 Load ▾"]
        if saved:
            for p in saved:
                items.append(p)
            items.append("🗑️ Manage / Delete...")
        else:
            items.append("(No saved professors)")
        return items

    def _refresh_instructor_menu(self):
        if hasattr(self, "instructor_menu"):
            self.instructor_menu.configure(values=self._get_instructor_menu_values())
            self.instructor_menu.set("📂 Load ▾")

    def _on_instructor_selected(self, choice: str):
        self.instructor_menu.set("📂 Load ▾")
        if choice == "🗑️ Manage / Delete...":
            self._open_delete_modal("Professor", self.metadata_mgr.get_professors(), self._delete_professor)
        elif choice not in ("📂 Load ▾", "(No saved professors)"):
            self.instructor_entry.delete(0, "end")
            self.instructor_entry.insert(0, choice)
            self.project.instructor_name = choice

    def _save_instructor_action(self):
        val = self.instructor_entry.get().strip()
        if not val:
            messagebox.showwarning("Empty Professor", "Please enter a Professor/Instructor Name before saving.", parent=self)
            return
        self.metadata_mgr.save_professor(val)
        self._refresh_instructor_menu()
        messagebox.showinfo("Professor Saved", f"Professor Name '{val}' saved to presets!", parent=self)

    def _delete_instructor_action(self):
        saved = self.metadata_mgr.get_professors()
        if not saved:
            messagebox.showinfo("No Saved Professors", "You don't have any saved professors yet.", parent=self)
            return
        current = self.instructor_entry.get().strip()
        if current and current in saved:
            if messagebox.askyesno("Delete Saved Professor", f"Remove '{current}' from saved professors?", parent=self):
                self._delete_professor(current)
                messagebox.showinfo("Deleted", f"Removed '{current}' from saved professors.", parent=self)
        else:
            self._open_delete_modal("Professor", saved, self._delete_professor)

    def _delete_professor(self, name: str):
        self.metadata_mgr.delete_professor(name)
        self._refresh_instructor_menu()
        if self.instructor_entry.get().strip() == name:
            self.instructor_entry.delete(0, "end")
            self.project.instructor_name = ""

    # --- Common Delete Modal ---
    def _open_delete_modal(self, category: str, items: List[str], on_delete_callback):
        """Opens a management dialog listing all saved presets with individual delete buttons."""
        if not items:
            messagebox.showinfo("No Saved Items", f"No saved {category.lower()}s found to delete.", parent=self)
            return

        modal = ctk.CTkToplevel(self)
        modal.title(f"Manage Saved {category}s")
        modal.geometry("440x360")
        modal.transient(self)
        modal.grab_set()

        head = ctk.CTkFrame(modal, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            head,
            text=f"🗑️ Manage Saved {category} Presets",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f8fafc"
        ).pack(side="left")

        scroll = ctk.CTkScrollableFrame(modal, fg_color="#09090b")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        def populate():
            for child in scroll.winfo_children():
                child.destroy()

            current_items = []
            if category == "Author":
                current_items = self.metadata_mgr.get_authors()
            elif category == "Course":
                current_items = self.metadata_mgr.get_courses()
            elif category == "Professor":
                current_items = self.metadata_mgr.get_professors()

            if not current_items:
                ctk.CTkLabel(
                    scroll,
                    text=f"No saved {category.lower()}s remaining.",
                    text_color="#71717a",
                    font=ctk.CTkFont(size=12)
                ).pack(pady=20)
                return

            for itm in current_items:
                row = ctk.CTkFrame(scroll, fg_color="#18181b", corner_radius=6, border_width=1, border_color="#27272a")
                row.pack(fill="x", pady=3, padx=2)

                ctk.CTkLabel(
                    row,
                    text=itm,
                    text_color="#f8fafc",
                    font=ctk.CTkFont(size=12),
                    anchor="w"
                ).pack(side="left", padx=12, pady=8, fill="x", expand=True)

                def make_del_cmd(val=itm):
                    return lambda: do_delete(val)

                ctk.CTkButton(
                    row,
                    text="Delete",
                    command=make_del_cmd(itm),
                    width=65,
                    height=26,
                    font=ctk.CTkFont(size=11),
                    fg_color="#ef4444",
                    hover_color="#dc2626"
                ).pack(side="right", padx=10, pady=6)

        def do_delete(val):
            on_delete_callback(val)
            populate()

        populate()

        close_btn = ctk.CTkButton(
            modal,
            text="Done",
            command=modal.destroy,
            width=100,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        close_btn.pack(pady=(0, 16))

    def _on_topic_changed(self):
        self.project.topic_description = self.topic_textbox.get("1.0", "end").strip()
        self._auto_detect_word_requirements()
        self._auto_ingest_embedded_youtube(self.project.topic_description)

    def _on_rubric_criteria_changed(self, criteria: List[RubricCriterion]):
        self.project.rubric_criteria = criteria
        if hasattr(self, "stage_2_rubric_viewer"):
            self.stage_2_rubric_viewer.set_criteria(criteria)
        logger.info(f"Rubric criteria live-synced: {len(criteria)} criteria")
        self._auto_detect_word_requirements()

    def _auto_detect_word_requirements(self):
        topic_text = self.topic_textbox.get("1.0", "end").strip()
        rubric_text = self.rubric_raw_textbox.get("1.0", "end").strip()
        if rubric_text.startswith("Paste rubric text here"):
            rubric_text = ""
        combined = f"{topic_text}\n{rubric_text}".strip()
        if not combined:
            return

        crit_count = len(self.project.rubric_criteria) if getattr(self.project, "rubric_criteria", None) else None
        constraints = WrittenSolver.extract_detailed_word_constraints(combined, item_count=crit_count)
        detected_target = constraints.get("total_min_words")
        num_items = constraints.get("num_items")
        per_item = constraints.get("per_item_words")

        if not detected_target and per_item:
            if crit_count and crit_count > 1:
                detected_target = per_item * crit_count
                num_items = crit_count

        if not detected_target and not per_item:
            detected_target = constraints.get("min_words")

        if detected_target and detected_target > 0:
            current_val = self.words_entry.get().strip()
            # If current_val is default 1000 or empty or matches current target
            if current_val in ("1000", "", str(self.project.target_total_words)):
                self.words_entry.delete(0, "end")
                self.words_entry.insert(0, str(detected_target))
                self.project.target_total_words = detected_target

            if num_items and per_item:
                msg = f"✨ Detected: {num_items} points × {per_item}w/point = {detected_target}w total (Target: ~{int(per_item * 1.1)}w each)"
            else:
                msg = f"✨ Detected: {detected_target}w requirement (Target: {detected_target}–{int(detected_target * 1.2)}w)"
            self.detected_words_label.configure(text=msg)
        elif per_item:
            msg = f"✨ Detected: {per_item}w PER POINT (Total will be calculated once points/criteria are set)"
            self.detected_words_label.configure(text=msg)

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
            self._auto_ingest_embedded_youtube(content)
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
                self._auto_ingest_embedded_youtube(text)
            sub_win.destroy()

        btn = ctk.CTkButton(sub_win, text="Save Notes Source", command=save_notes, fg_color="#2563eb")
        btn.pack(pady=(0, 16))

    def _prompt_add_web_source(self):
        sub_win = ctk.CTkToplevel(self)
        sub_win.title("Add Web Article or YouTube Source")
        sub_win.geometry("560x300")
        sub_win.transient(self)
        sub_win.grab_set()

        ctk.CTkLabel(
            sub_win,
            text="🌐 Ingest Web Article or ▶️ YouTube Video",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#38bdf8"
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            sub_win,
            text="Paste an article URL or YouTube link. Ava will fetch metadata, summarize the content, and generate a citation.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkLabel(sub_win, text="URL / Link:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20, pady=(4, 2))
        url_entry = ctk.CTkEntry(sub_win, placeholder_text="https://www.youtube.com/watch?v=... or https://example.com/article")
        url_entry.pack(fill="x", padx=20, pady=(0, 8))

        status_lbl = ctk.CTkLabel(sub_win, text="", font=ctk.CTkFont(size=11), text_color="#38bdf8")
        status_lbl.pack(anchor="w", padx=20, pady=(0, 6))

        def fetch_task():
            url = url_entry.get().strip()
            if not url:
                status_lbl.configure(text="Please enter a valid URL.", text_color="#ef4444")
                return
            fetch_btn.configure(state="disabled", text="⏳ Ingesting & Summarizing...")
            status_lbl.configure(text="Fetching metadata and AI summary...", text_color="#38bdf8")

            def worker():
                try:
                    result = WebSourceIngestor.fetch(url, ai_client=self.ai_client)
                    if not result.get("success"):
                        err = result.get("error", "Failed to fetch URL")
                        self.after(0, lambda: status_lbl.configure(text=f"Error: {err}", text_color="#ef4444"))
                        self.after(0, lambda: fetch_btn.configure(state="normal", text="Fetch & Add Source"))
                        return

                    stype = "youtube" if result.get("is_youtube") else "web"
                    src = SourceItem(
                        name=result.get("title", url),
                        source_type=stype,
                        content=result.get("summary_content", ""),
                        file_path=url
                    )
                    self.project.sources.append(src)

                    try:
                        citation = CitationGenerator.generate(
                            result,
                            style=self.project.formatting_preset,
                            format_style=self.project.formatting_preset,
                        )
                        if citation and citation not in self.project.bibliography_entries:
                            self.project.bibliography_entries.append(citation)
                    except Exception as cite_err:
                        logger.warning(f"Could not generate citation for {url}: {cite_err}")

                    self.after(0, lambda: self._finish_web_ingest(sub_win, src))
                except Exception as e:
                    logger.error(f"Error fetching web source: {e}")
                    self.after(0, lambda: status_lbl.configure(text=f"Exception: {e}", text_color="#ef4444"))
                    self.after(0, lambda: fetch_btn.configure(state="normal", text="Fetch & Add Source"))

            threading.Thread(target=worker, daemon=True).start()

        fetch_btn = ctk.CTkButton(
            sub_win,
            text="Fetch & Add Source",
            command=fetch_task,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        fetch_btn.pack(fill="x", padx=20, pady=(8, 16))

    def _finish_web_ingest(self, modal, src: SourceItem):
        try:
            modal.destroy()
        except Exception:
            pass
        self._render_sources_list()
        messagebox.showinfo("Source Ingested", f"Successfully ingested source:\n{src.name}\nType: {src.source_type.upper()}")

    def _auto_ingest_embedded_youtube(self, text: str):
        if not text:
            return
        yt_urls = WebSourceIngestor.extract_youtube_urls(text)
        for url in yt_urls:
            if any(s.file_path == url for s in self.project.sources):
                continue
            logger.info(f"Auto-importing embedded YouTube source: {url}")
            def worker(u=url):
                try:
                    res = WebSourceIngestor.fetch(u, ai_client=self.ai_client)
                    if res.get("success"):
                        src = SourceItem(
                            name=res.get("title", u),
                            source_type="youtube",
                            content=res.get("summary_content", ""),
                            file_path=u
                        )
                        self.project.sources.append(src)
                        try:
                            cit = CitationGenerator.generate(
                                res,
                                style=self.project.formatting_preset,
                                format_style=self.project.formatting_preset,
                            )
                            if cit and cit not in self.project.bibliography_entries:
                                self.project.bibliography_entries.append(cit)
                        except Exception as cite_err:
                            logger.warning(f"Could not generate citation for auto-imported YouTube link {u}: {cite_err}")
                        self.after(0, self._render_sources_list)
                except Exception as ex:
                    logger.warning(f"Could not auto-import youtube link {u}: {ex}")
            threading.Thread(target=worker, daemon=True).start()

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

            if src.source_type in ["youtube", "video"]:
                icon = "▶️"
            elif src.source_type in ["web", "url"]:
                icon = "🌐"
            elif src.source_type in ["pdf", "docx", "doc"]:
                icon = "📄"
            else:
                icon = "📝"
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
            self._auto_detect_word_requirements()
            self._parse_rubric_action()
            self._auto_ingest_embedded_youtube(content)
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
        self._auto_detect_word_requirements()
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
        self._auto_detect_word_requirements()

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

        self.gen_out_btn = ctk.CTkButton(
            o_header,
            text="⚡ AI Auto-Generate Outline",
            command=self._generate_outline_action,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb"
        )
        self.gen_out_btn.pack(side="right", padx=4)

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
        right_col = ctk.CTkFrame(grid, width=340, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        right_col.pack(side="right", fill="both", padx=(8, 0))

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
        self._auto_detect_word_requirements()
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
        """Opens a clarification pop-up modal allowing the user to clarify structure, section count, and notes before AI generation."""
        self._show_outline_clarification_dialog()

    def _show_outline_clarification_dialog(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Clarify Document Structure & Outline Preferences")
        modal.geometry("620x660")
        modal.minsize(560, 580)
        modal.configure(fg_color="#09090b")
        modal.transient(self)

        # Apply cloaking if enabled
        if self.is_cloaked and is_anti_capture_supported():
            apply_anti_capture(modal)

        # Header Frame
        hdr = ctk.CTkFrame(modal, fg_color="#18181b", corner_radius=0)
        hdr.pack(fill="x")

        ctk.CTkLabel(
            hdr,
            text="⚡ Clarify Outline Structure & Personalization",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#38bdf8"
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            hdr,
            text="Clarify how Ava should organize your sections, question breakdown, and style before generating the outline.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            wraplength=570,
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # Main scrollable content
        content = ctk.CTkScrollableFrame(modal, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=12)

        # 1. Structure Style Preset
        ctk.CTkLabel(content, text="Structure Style Preset:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(4, 2))
        structure_presets = [
            "Auto-Detect from Rubric & Topic (Recommended)",
            "Standard Academic Essay (Intro, Body Paragraphs, Conclusion)",
            "Multi-Question / Multi-Part Assignment (Q1, Q2, Q3...)",
            "Scientific / IMRAD (Intro, Methods, Results, Discussion)",
            "Comparative Analysis (Thesis, Subject A, Subject B, Synthesis)",
            "Argumentative / Persuasive (Claim, Evidence, Counterargument, Rebuttal)",
        ]
        structure_menu = ctk.CTkOptionMenu(
            content,
            values=structure_presets,
            fg_color="#27272a",
            button_color="#3f3f46",
            height=34,
        )
        structure_menu.set(structure_presets[0])
        structure_menu.pack(fill="x", pady=(0, 12))

        # 2. Section Count & Total Word Target Row
        grid_row = ctk.CTkFrame(content, fg_color="transparent")
        grid_row.pack(fill="x", pady=(0, 12))

        left_sub = ctk.CTkFrame(grid_row, fg_color="transparent")
        left_sub.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkLabel(left_sub, text="Target Section Count:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(0, 2))
        section_counts = [
            "Auto (Decided by Rubric & Topic)",
            "3 Sections (Short Paper / 3-Part)",
            "4 Sections",
            "5 Sections (Standard 5-Part / 5 Questions)",
            "6 Sections",
            "7 Sections",
            "8 Sections (Comprehensive)",
        ]
        count_menu = ctk.CTkOptionMenu(
            left_sub,
            values=section_counts,
            fg_color="#27272a",
            button_color="#3f3f46",
            height=34,
        )
        count_menu.set(section_counts[0])
        count_menu.pack(fill="x")

        right_sub = ctk.CTkFrame(grid_row, fg_color="transparent")
        right_sub.pack(side="right", fill="x", expand=True, padx=(6, 0))

        ctk.CTkLabel(right_sub, text="Total Document Target Words:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(0, 2))
        words_entry = ctk.CTkEntry(right_sub, height=34)
        words_entry.insert(0, str(self.project.target_total_words))
        words_entry.pack(fill="x")

        # 3. Section Heading Naming Style
        ctk.CTkLabel(content, text="Heading & Title Style:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(4, 2))
        heading_styles = [
            "Descriptive Academic Titles (e.g. 'Historical Context & Evolution')",
            "Numbered Headings (e.g. '1. Introduction', '2. Analysis')",
            "Question Headings (e.g. 'Question 1: ...', 'Question 2: ...')",
            "Roman Numerals (e.g. 'I. Introduction', 'II. Context')",
        ]
        heading_menu = ctk.CTkOptionMenu(
            content,
            values=heading_styles,
            fg_color="#27272a",
            button_color="#3f3f46",
            height=34,
        )
        heading_menu.set(heading_styles[0])
        heading_menu.pack(fill="x", pady=(0, 12))

        # 4. Student Notes / Specific Guidance Textbox
        ctk.CTkLabel(content, text="Specific Personal Instructions or Focus Areas (Optional):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(4, 2))
        ctk.CTkLabel(
            content,
            text="Clarify any specific angles, mandatory arguments, counterarguments, or questions you want covered in each section.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(anchor="w", pady=(0, 4))
        notes_box = ctk.CTkTextbox(content, height=110, fg_color="#18181b", font=ctk.CTkFont(size=12))
        notes_box.pack(fill="x", pady=(0, 10))

        # Bottom Action Bar
        btn_bar = ctk.CTkFrame(modal, fg_color="#18181b", height=56)
        btn_bar.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            btn_bar,
            text="Cancel",
            command=modal.destroy,
            fg_color="#27272a",
            hover_color="#3f3f46",
            width=100,
            height=36,
        )
        cancel_btn.pack(side="left", padx=16, pady=10)

        def on_confirm():
            # Update word count if edited in modal
            try:
                val = int(words_entry.get().strip())
                if val > 0:
                    self.project.target_total_words = val
                    self.outline_stats_bar.configure(text=f"Total Outline Words: 0 / Target: {val}")
            except ValueError:
                pass

            customization = {
                "structure_preset": structure_menu.get(),
                "section_count": count_menu.get(),
                "heading_style": heading_menu.get(),
                "user_notes": notes_box.get("1.0", "end").strip(),
            }

            modal.destroy()
            self._start_outline_generation(customization)

        generate_btn = ctk.CTkButton(
            btn_bar,
            text="⚡ Generate Outline with Custom Structure",
            command=on_confirm,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
        )
        generate_btn.pack(side="right", padx=16, pady=10)

    def _start_outline_generation(self, customization: Optional[Dict[str, Any]] = None):
        if hasattr(self, "gen_out_btn") and self.gen_out_btn:
            self.gen_out_btn.configure(text="⏳ Generating Outline...", state="disabled")

        def task():
            try:
                sections = self.engine.generate_outline(self.project, customization=customization)
                self.after(0, lambda: self._finish_outline_gen(sections))
            except Exception as e:
                logger.error(f"Error generating outline: {e}", exc_info=True)
                self.after(0, lambda: self._on_outline_gen_failed(str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _finish_outline_gen(self, sections: List[SectionDraft]):
        if hasattr(self, "gen_out_btn") and self.gen_out_btn:
            self.gen_out_btn.configure(text="⚡ AI Auto-Generate Outline", state="normal")
        self.project.sections = sections
        self._render_outline_list()

    def _on_outline_gen_failed(self, err_msg: str):
        if hasattr(self, "gen_out_btn") and self.gen_out_btn:
            self.gen_out_btn.configure(text="⚡ AI Auto-Generate Outline", state="normal")
        messagebox.showerror("Outline Generation Error", f"Failed to generate outline:\n{err_msg}")

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
        self.sec_word_label.pack(side="right", padx=(8, 0))

        self.trim_btn = ctk.CTkButton(
            self.sec_info_bar,
            text="✂️ Believable Trim (10-20%)",
            command=self._trim_active_section,
            width=165,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#27272a",
            hover_color="#3f3f46"
        )
        self.trim_btn.pack(side="right", padx=(0, 8))

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
        self._update_sec_word_stats(sec, sec.get_active_text())

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
        self._update_sec_word_stats(sec, text)

    def _update_sec_word_stats(self, sec: SectionDraft, text: str):
        words = len(text.split()) if text.strip() else 0
        target = sec.target_word_count or 250
        max_allowed = int(target * 1.20)

        if words == 0:
            self.sec_word_label.configure(
                text=f"Words: 0 / {target} (Target: {target}–{max_allowed}w)",
                text_color="#94a3b8"
            )
        elif words < target:
            self.sec_word_label.configure(
                text=f"Words: {words} / {target} (Under min by {target - words}w)",
                text_color="#f59e0b"
            )
        elif target <= words <= max_allowed:
            pct_over = int(((words - target) / target) * 100) if target > 0 else 0
            self.sec_word_label.configure(
                text=f"Words: {words} / {target} (Target: {target}–{max_allowed}w • Believable +{pct_over}%)",
                text_color="#34d399"
            )
        else:
            pct_over = int(((words - target) / target) * 100) if target > 0 else 0
            self.sec_word_label.configure(
                text=f"Words: {words} / {target} (Max: {max_allowed}w • Over by +{words - max_allowed}w / +{pct_over}%)",
                text_color="#ef4444"
            )

    def _trim_active_section(self):
        if not self.project.sections or self.current_section_idx >= len(self.project.sections):
            return
        sec = self.project.sections[self.current_section_idx]
        current_text = self.final_text_box.get("1.0", "end").strip()
        if not current_text:
            return
        min_words = sec.target_word_count or 250
        max_allowed = int(min_words * 1.20)
        trimmed = WrittenSolver.apply_word_limits(current_text, min_words=min_words, max_words=max_allowed)
        sec.final_text = trimmed
        self.final_text_box.delete("1.0", "end")
        self.final_text_box.insert("1.0", trimmed)
        self._update_sec_word_stats(sec, trimmed)

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

        # Right Column: Export Settings, Teacher Evaluation & Works Cited
        right_col = ctk.CTkFrame(grid, width=380, fg_color="#18181b", corner_radius=10, border_width=1, border_color="#27272a")
        right_col.pack(side="right", fill="both", padx=(8, 0))

        right_scroll = ctk.CTkScrollableFrame(right_col, fg_color="transparent")
        right_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        e_head = ctk.CTkLabel(right_scroll, text="⚙️ Export & Academic Review", font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc")
        e_head.pack(anchor="w", padx=12, pady=(10, 8))

        # Stats summary card
        self.export_stats_frame = ctk.CTkFrame(right_scroll, fg_color="#09090b", corner_radius=8)
        self.export_stats_frame.pack(fill="x", padx=12, pady=(0, 10))

        self.export_words_lbl = ctk.CTkLabel(self.export_stats_frame, text="Total Words: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8")
        self.export_words_lbl.pack(anchor="w", padx=12, pady=(8, 2))

        self.export_criteria_lbl = ctk.CTkLabel(self.export_stats_frame, text="Rubric Criteria Met: 0 / 0", font=ctk.CTkFont(size=12), text_color="#34d399")
        self.export_criteria_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        # Teacher AI Grading Card
        self.teacher_card = ctk.CTkFrame(right_scroll, fg_color="#0f172a", corner_radius=8, border_width=1, border_color="#312e81")
        self.teacher_card.pack(fill="x", padx=12, pady=(0, 10))

        t_header = ctk.CTkLabel(self.teacher_card, text="🎓 Unbiased Teacher Grading", font=ctk.CTkFont(size=13, weight="bold"), text_color="#a5b4fc")
        t_header.pack(anchor="w", padx=12, pady=(10, 4))

        self.teacher_grade_badge = ctk.CTkLabel(
            self.teacher_card,
            text="Not Graded Yet",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#94a3b8"
        )
        self.teacher_grade_badge.pack(anchor="w", padx=12, pady=(0, 4))

        self.teacher_comment_lbl = ctk.CTkLabel(
            self.teacher_card,
            text="Have an independent AI teacher evaluate your paper against the rubric.",
            font=ctk.CTkFont(size=11),
            text_color="#cbd5e1",
            wraplength=310,
            justify="left"
        )
        self.teacher_comment_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        t_btns = ctk.CTkFrame(self.teacher_card, fg_color="transparent")
        t_btns.pack(fill="x", padx=12, pady=(0, 10))

        self.grade_teacher_btn = ctk.CTkButton(
            t_btns,
            text="🎓 Grade with Teacher AI",
            command=self._grade_with_teacher_action,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.grade_teacher_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.view_rubric_breakdown_btn = ctk.CTkButton(
            t_btns,
            text="🔍 Details",
            command=self._show_teacher_breakdown_dialog,
            fg_color="#27272a",
            hover_color="#3f3f46",
            width=65,
            height=32,
            font=ctk.CTkFont(size=11),
            state="disabled"
        )
        self.view_rubric_breakdown_btn.pack(side="right")

        # Checkbox for export inclusion
        self.include_teacher_report_cb = ctk.CTkCheckBox(
            right_scroll,
            text="Include Teacher Evaluation in .docx",
            font=ctk.CTkFont(size=12),
            fg_color="#6366f1",
            hover_color="#4f46e5"
        )
        self.include_teacher_report_cb.pack(anchor="w", padx=14, pady=(2, 10))
        self.include_teacher_report_cb.select()

        # Format Style selector
        ctk.CTkLabel(right_scroll, text="Document Formatting Preset:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(4, 2))
        self.stage_4_format_menu = ctk.CTkOptionMenu(
            right_scroll,
            values=["MLA", "APA", "Standard Report"],
            command=self._on_format_changed,
            fg_color="#27272a"
        )
        self.stage_4_format_menu.set(self.project.formatting_preset)
        self.stage_4_format_menu.pack(fill="x", padx=12, pady=(0, 10))

        # Bibliography / Works Cited entries
        ctk.CTkLabel(right_scroll, text="Works Cited / References:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(4, 2))
        self.biblio_textbox = ctk.CTkTextbox(right_scroll, height=110, fg_color="#09090b", font=ctk.CTkFont(size=11))
        self.biblio_textbox.pack(fill="x", padx=12, pady=(0, 10))
        self.biblio_textbox.insert("1.0", "Paste MLA/APA citations here (one per line)...")

        # Big Export Button
        export_docx_btn = ctk.CTkButton(
            right_scroll,
            text="📥 Export to Word Document (.docx)",
            command=self._export_to_docx_action,
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        export_docx_btn.pack(fill="x", padx=12, pady=(8, 12))

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

        # Sync bibliography entries if present
        if self.project.bibliography_entries:
            current_bib = self.biblio_textbox.get("1.0", "end").strip()
            if not current_bib or current_bib.startswith("Paste MLA"):
                self.biblio_textbox.delete("1.0", "end")
                self.biblio_textbox.insert("1.0", "\n\n".join(self.project.bibliography_entries))

        # Sync teacher evaluation card
        self._sync_teacher_grade_ui()

    def _sync_teacher_grade_ui(self):
        report = self.project.teacher_grade_report
        if not report:
            self.teacher_grade_badge.configure(
                text="Not Graded Yet",
                text_color="#94a3b8"
            )
            self.teacher_comment_lbl.configure(
                text="Have an independent AI teacher evaluate your paper against the rubric."
            )
            self.view_rubric_breakdown_btn.configure(state="disabled")
            return

        letter = report.get("letter_grade", "N/A")
        score = report.get("numerical_score", 0)
        pct = report.get("percentage", float(score))
        badge_color = "#34d399" if pct >= 80 else ("#fbbf24" if pct >= 70 else "#f87171")

        self.teacher_grade_badge.configure(
            text=f"Grade: {letter} ({score}/100 • {pct:.1f}%)",
            text_color=badge_color
        )
        summary = report.get("summary", "").strip() or report.get("overall_feedback", "")[:120] + "..."
        self.teacher_comment_lbl.configure(text=summary)
        self.view_rubric_breakdown_btn.configure(state="normal")

    def _grade_with_teacher_action(self):
        full_text = self.project.get_full_document_text()
        if not full_text.strip():
            messagebox.showwarning("Empty Document", "Please write and approve section drafts before requesting a teacher grade.")
            return

        self.grade_teacher_btn.configure(text="⏳ Grading with Teacher AI...", state="disabled")

        def task():
            try:
                report = self.teacher_evaluator.grade_document(self.project)
                TeacherEvaluator.apply_to_project(report, self.project)
                self.after(0, lambda: self._on_teacher_grading_finished(report))
            except Exception as e:
                logger.error(f"Teacher grading error: {e}", exc_info=True)
                self.after(0, lambda: self._on_teacher_grading_failed(str(e)))

        threading.Thread(target=task, daemon=True).start()

    def _on_teacher_grading_finished(self, report: Dict[str, Any]):
        self.grade_teacher_btn.configure(text="🔄 Re-Grade with Teacher AI", state="normal")
        self._sync_teacher_grade_ui()

        # Update criteria counter in Stage 4
        fulfilled = sum(1 for c in self.project.rubric_criteria if c.fulfilled)
        self.export_criteria_lbl.configure(text=f"Rubric Criteria Met: {fulfilled} / {len(self.project.rubric_criteria)}")

        letter = report.get("letter_grade", "N/A")
        score = report.get("numerical_score", 0)
        summary = report.get("summary", "")
        messagebox.showinfo(
            "Teacher Evaluation Complete",
            f"Official Teacher Grade: {letter} ({score}%)\n\n{summary}\n\n"
            "Click 'Details' to inspect the full rubric critique and strengths/weaknesses breakdown."
        )

    def _on_teacher_grading_failed(self, err_msg: str):
        self.grade_teacher_btn.configure(text="🎓 Grade with Teacher AI", state="normal")
        messagebox.showerror("Grading Error", f"Failed to complete teacher grading:\n{err_msg}")

    def _show_teacher_breakdown_dialog(self):
        report = self.project.teacher_grade_report
        if not report:
            messagebox.showinfo("No Grade Available", "Document has not been graded yet.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Teacher AI Rubric Evaluation & Critique")
        dlg.geometry("780x620")
        dlg.minsize(680, 500)
        dlg.configure(fg_color="#09090b")
        dlg.transient(self)

        # Apply cloaking if supported
        if self.is_cloaked and is_anti_capture_supported():
            apply_anti_capture(dlg)

        # Header banner
        header_frame = ctk.CTkFrame(dlg, fg_color="#18181b", corner_radius=0)
        header_frame.pack(fill="x")

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🎓 Official Teacher Evaluation Report",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f8fafc"
        )
        title_lbl.pack(side="left", padx=20, pady=16)

        letter = report.get("letter_grade", "N/A")
        score = report.get("numerical_score", 0)
        pct = report.get("percentage", float(score))
        badge_color = "#34d399" if pct >= 80 else ("#fbbf24" if pct >= 70 else "#f87171")

        grade_badge = ctk.CTkLabel(
            header_frame,
            text=f"Score: {letter} ({score}/100 • {pct:.1f}%)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=badge_color
        )
        grade_badge.pack(side="right", padx=20, pady=16)

        # Main scrollable body
        body_scroll = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        body_scroll.pack(fill="both", expand=True, padx=20, pady=16)

        # Summary & Feedback Card
        fb_card = ctk.CTkFrame(body_scroll, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
        fb_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(fb_card, text="Instructor Commentary", font=ctk.CTkFont(size=13, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=16, pady=(12, 4))
        
        fb_text = report.get("overall_feedback", "") or report.get("summary", "No commentary recorded.")
        fb_lbl = ctk.CTkLabel(fb_card, text=fb_text, font=ctk.CTkFont(size=12), text_color="#cbd5e1", wraplength=700, justify="left")
        fb_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # Strengths & Improvements Grid
        strengths = report.get("strengths", [])
        improvements = report.get("areas_for_improvement", [])
        if strengths or improvements:
            grid_cols = ctk.CTkFrame(body_scroll, fg_color="transparent")
            grid_cols.pack(fill="x", pady=(0, 12))

            # Left: Strengths
            str_col = ctk.CTkFrame(grid_cols, fg_color="#064e3b", corner_radius=8, border_width=1, border_color="#047857")
            str_col.pack(side="left", fill="both", expand=True, padx=(0, 6))

            ctk.CTkLabel(str_col, text="✓ Key Strengths", font=ctk.CTkFont(size=12, weight="bold"), text_color="#6ee7b7").pack(anchor="w", padx=12, pady=(10, 6))
            for s in strengths:
                ctk.CTkLabel(str_col, text=f"• {s}", font=ctk.CTkFont(size=11), text_color="#e2e8f0", wraplength=310, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
            ctk.CTkLabel(str_col, text="").pack(pady=2)

            # Right: Areas for Improvement
            imp_col = ctk.CTkFrame(grid_cols, fg_color="#451a03", corner_radius=8, border_width=1, border_color="#b45309")
            imp_col.pack(side="right", fill="both", expand=True, padx=(6, 0))

            ctk.CTkLabel(imp_col, text="⚠️ Areas for Improvement", font=ctk.CTkFont(size=12, weight="bold"), text_color="#fcd34d").pack(anchor="w", padx=12, pady=(10, 6))
            for imp in improvements:
                ctk.CTkLabel(imp_col, text=f"• {imp}", font=ctk.CTkFont(size=11), text_color="#e2e8f0", wraplength=310, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
            ctk.CTkLabel(imp_col, text="").pack(pady=2)

        # Rubric Criteria Breakdown
        crit_evals = report.get("criteria_evaluations", [])
        if crit_evals:
            ctk.CTkLabel(body_scroll, text="Rubric Criteria Breakdown", font=ctk.CTkFont(size=13, weight="bold"), text_color="#f8fafc").pack(anchor="w", pady=(8, 6))

            for ev in crit_evals:
                crit_card = ctk.CTkFrame(body_scroll, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
                crit_card.pack(fill="x", pady=(0, 8))

                top_bar = ctk.CTkFrame(crit_card, fg_color="transparent")
                top_bar.pack(fill="x", padx=14, pady=(10, 4))

                title = ev.get("title", "Requirement")
                ctk.CTkLabel(top_bar, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color="#f8fafc").pack(side="left")

                is_ful = ev.get("fulfilled", False)
                status_color = "#34d399" if is_ful else "#f59e0b"
                status_text = "✓ Fulfilled" if is_ful else "Developing"

                score_info = f"[{ev.get('score', '')}/{ev.get('max_score', '')} pts]" if "score" in ev and "max_score" in ev else ""
                badge_text = f"{status_text}  {score_info}".strip()

                ctk.CTkLabel(top_bar, text=badge_text, font=ctk.CTkFont(size=11, weight="bold"), text_color=status_color).pack(side="right")

                fb = ev.get("feedback", "").strip()
                if fb:
                    ctk.CTkLabel(crit_card, text=fb, font=ctk.CTkFont(size=11), text_color="#94a3b8", wraplength=690, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

        # Close button bottom bar
        btn_bar = ctk.CTkFrame(dlg, fg_color="#18181b", height=50)
        btn_bar.pack(fill="x")

        close_btn = ctk.CTkButton(btn_bar, text="Close Report", command=dlg.destroy, width=120, height=34, fg_color="#27272a", hover_color="#3f3f46")
        close_btn.pack(side="right", padx=16, pady=8)

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

        include_teacher = getattr(self, "include_teacher_report_cb", None) and self.include_teacher_report_cb.get() == 1
        teacher_report = self.project.teacher_grade_report if include_teacher else None

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
                teacher_grade_report=teacher_report,
            )
            messagebox.showinfo("Export Successful", f"Document exported successfully to:\n{exported_path}")
            # Highlight in Windows Explorer
            os.system(f'explorer /select,"{exported_path}"')
        except Exception as e:
            logger.error(f"Failed to export docx: {e}")
            messagebox.showerror("Export Failed", f"Could not create .docx document:\n{e}")

    # -------------------------------------------------------------------------
    # Save, Open, Recent Projects & Start Over
    # -------------------------------------------------------------------------

    def _get_recent_projects_list(self) -> List[str]:
        items = ["📂 Open Recent ▾"]
        proj_dir = os.path.join(os.getcwd(), "projects")
        if os.path.exists(proj_dir):
            try:
                files = [f for f in os.listdir(proj_dir) if f.endswith(".avaproj")]
                files.sort(key=lambda f: os.path.getmtime(os.path.join(proj_dir, f)), reverse=True)
                for f in files[:10]:
                    items.append(f)
            except Exception as e:
                logger.warning(f"Error listing recent projects: {e}")
        items.append("📁 Browse file from disk...")
        return items

    def _refresh_recent_projects_menu(self):
        if hasattr(self, "open_recent_menu"):
            vals = self._get_recent_projects_list()
            self.open_recent_menu.configure(values=vals)
            self.open_recent_menu.set("📂 Open Recent ▾")

    def _on_recent_project_selected(self, choice: str):
        if choice == "📁 Browse file from disk...":
            self.open_recent_menu.set("📂 Open Recent ▾")
            self._open_project_dialog()
        elif choice != "📂 Open Recent ▾":
            path = os.path.join(os.getcwd(), "projects", choice)
            if os.path.isfile(path):
                self._load_project_file(path)
            self.open_recent_menu.set("📂 Open Recent ▾")

    def _start_over_dialog(self):
        confirm = messagebox.askyesno(
            "Start Over",
            "Are you sure you want to start over? Any unsaved progress in the current project will be lost.",
            parent=self
        )
        if not confirm:
            return

        self.project = PlaygroundProject()
        self.current_file_path = None
        self.current_section_idx = 0

        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, self.project.title)
        self.title_display.configure(text=self.project.title)

        self.topic_textbox.delete("1.0", "end")
        self.words_entry.delete(0, "end")
        self.words_entry.insert(0, str(self.project.target_total_words))
        self.detected_words_label.configure(text="")

        self.author_entry.delete(0, "end")
        self.course_entry.delete(0, "end")
        self.instructor_entry.delete(0, "end")

        self.format_menu.set(self.project.formatting_preset)
        self._render_sources_list()
        self.stage_1_rubric_viewer.set_criteria([])
        self.rubric_raw_textbox.delete("1.0", "end")
        self.rubric_raw_textbox.insert("1.0", "Paste rubric text here or use Screen-Snip / Upload...")

        if hasattr(self, "stage_2_rubric_viewer"):
            self.stage_2_rubric_viewer.set_criteria([])
        self._render_outline_list()

        self.show_step(1)
        messagebox.showinfo("New Project", "Started a new blank project.", parent=self)

    def _save_project_dialog(self):
        os.makedirs("projects", exist_ok=True)
        if not self.current_file_path:
            default_name = f"{self.project.title.replace(' ', '_')}.avaproj"
            self.current_file_path = filedialog.asksaveasfilename(
                title="Save Playground Project",
                initialdir=os.path.join(os.getcwd(), "projects"),
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

            if hasattr(self, "biblio_textbox"):
                bib_raw = self.biblio_textbox.get("1.0", "end").strip()
                if bib_raw and not bib_raw.startswith("Paste MLA"):
                    self.project.bibliography_entries = [l.strip() for l in bib_raw.splitlines() if l.strip()]

            self.project.save_to_file(path)
            self._refresh_recent_projects_menu()
            messagebox.showinfo("Saved", f"Project saved to:\n{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save project:\n{e}")

    def _open_project_dialog(self):
        proj_dir = os.path.join(os.getcwd(), "projects")
        path = filedialog.askopenfilename(
            title="Open Playground Project",
            initialdir=proj_dir if os.path.exists(proj_dir) else os.getcwd(),
            filetypes=[("AVA Project", "*.avaproj"), ("JSON File", "*.json")]
        )
        if path:
            self._load_project_file(path)

    def _load_project_file(self, path: str):
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
            if hasattr(self, "stage_2_rubric_viewer"):
                self.stage_2_rubric_viewer.set_criteria(self.project.rubric_criteria)

            self._render_outline_list()
            self._refresh_recent_projects_menu()

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
