"""
Formatted Changelog Viewer for AVA School Assistant 2.
Parses and renders CHANGELOG.md in a modern, cloaked UI dialog with version badges,
categorized updates (Added, Fixed, Changed), bullet highlighting, search filtering,
and raw markdown inspection.
"""

import os
import sys
import re
from typing import List, Dict, Any, Optional
import customtkinter as ctk

from core.logger import get_logger
from core.cloaking import apply_anti_capture, is_anti_capture_supported

logger = get_logger("ui.changelog_viewer")


def get_changelog_path() -> str:
    """Resolves CHANGELOG.md location across dev, package, and PyInstaller frozen bundles."""
    # 1. PyInstaller MEIPASS bundle directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_path = os.path.join(sys._MEIPASS, "CHANGELOG.md")
        if os.path.exists(meipass_path):
            return meipass_path

    # 2. Relative to repository root
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    root_path = os.path.abspath(os.path.join(curr_dir, "..", "CHANGELOG.md"))
    if os.path.exists(root_path):
        return root_path

    # 3. Current working directory
    if os.path.exists("CHANGELOG.md"):
        return os.path.abspath("CHANGELOG.md")

    return ""


class ChangelogViewer(ctk.CTkToplevel):
    """Modern modal dialog displaying the formatted version changelog."""

    def __init__(self, master, is_cloaked: bool = True):
        super().__init__(master)
        self.is_cloaked = is_cloaked
        self.raw_markdown = ""
        self.parsed_releases: List[Dict[str, Any]] = []
        self.current_view_mode = "formatted"  # "formatted" or "raw"

        self._setup_window()
        self._load_changelog()
        self._build_ui()

        if self.is_cloaked and is_anti_capture_supported():
            apply_anti_capture(self)

    def _setup_window(self):
        self.title("AVA School Assistant • Version Changelog")
        self.geometry("820x680+150+90")
        self.minsize(700, 540)
        self.configure(fg_color="#09090b")
        self.transient(self.master)

    def _load_changelog(self):
        path = get_changelog_path()
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.raw_markdown = f.read()
                self.parsed_releases = self._parse_markdown(self.raw_markdown)
            except Exception as e:
                logger.error(f"Error reading changelog from {path}: {e}")
                self.raw_markdown = f"# Changelog\n\nCould not load changelog: {e}"
        else:
            self.raw_markdown = (
                "# Changelog\n\n"
                "CHANGELOG.md not found in bundle or workspace directory.\n\n"
                "Please ensure CHANGELOG.md is placed in the project root."
            )

    def _parse_markdown(self, text: str) -> List[Dict[str, Any]]:
        """Parses CHANGELOG.md into structured release objects."""
        releases = []
        current_rel = None
        current_cat = None

        lines = text.splitlines()
        for line in lines:
            line_str = line.strip()

            # Match release header: ## [2.1.2.a] - 2026-09-20
            rel_match = re.match(r"^##\s*\[([^\]]+)\](?:\s*-\s*(\S+))?", line_str)
            if rel_match:
                if current_rel:
                    releases.append(current_rel)
                ver = rel_match.group(1).strip()
                dt = rel_match.group(2).strip() if rel_match.group(2) else ""
                current_rel = {
                    "version": ver,
                    "date": dt,
                    "categories": {},
                }
                current_cat = None
                continue

            # Match category header: ### Added / ### Fixed / ### Changed / etc.
            cat_match = re.match(r"^###\s+(.+)$", line_str)
            if cat_match and current_rel is not None:
                current_cat = cat_match.group(1).strip()
                if current_cat not in current_rel["categories"]:
                    current_rel["categories"][current_cat] = []
                continue

            # Match bullet items
            if current_rel is not None and current_cat is not None:
                if line.startswith("- ") or line.startswith("* "):
                    current_rel["categories"][current_cat].append({
                        "text": line[2:].strip(),
                        "sub_items": [],
                    })
                elif (line.startswith("  - ") or line.startswith("  * ") or line.startswith("    - ")) and current_rel["categories"][current_cat]:
                    # Sub-bullet
                    sub_text = re.sub(r"^\s*[-*]\s*", "", line).strip()
                    current_rel["categories"][current_cat][-1]["sub_items"].append(sub_text)

        if current_rel:
            releases.append(current_rel)

        return releases

    def _build_ui(self):
        # 1. Header Frame
        hdr_frame = ctk.CTkFrame(self, fg_color="#121215", corner_radius=0, height=64)
        hdr_frame.pack(fill="x", side="top")

        left_hdr = ctk.CTkFrame(hdr_frame, fg_color="transparent")
        left_hdr.pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            left_hdr,
            text="📜 Version Changelog & History",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38bdf8"
        ).pack(anchor="w")

        ctk.CTkLabel(
            left_hdr,
            text="Version format: 1.2.3.a (1: Major completion • 2: Major rework • 3: New features • a: Bug fixes)",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        ).pack(anchor="w")

        # Right: Toggle Raw / Formatted button
        self.toggle_view_btn = ctk.CTkButton(
            hdr_frame,
            text="📝 Raw Markdown",
            command=self._toggle_view_mode,
            width=120,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#18181b",
            hover_color="#27272a",
            text_color="#94a3b8",
            border_width=1,
            border_color="#3f3f46"
        )
        self.toggle_view_btn.pack(side="right", padx=20, pady=16)

        # 2. Filter & Search Bar
        filter_bar = ctk.CTkFrame(self, fg_color="#09090b", height=48)
        filter_bar.pack(fill="x", padx=20, pady=(10, 6))

        self.search_entry = ctk.CTkEntry(
            filter_bar,
            placeholder_text="🔍 Filter versions or features (e.g. playground, rubric, youtube, citations)...",
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_filter_changed())

        # 3. Main Container (Card scroll vs Raw textbox)
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Formatted scrollable list
        self.cards_scroll = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.cards_scroll.pack(fill="both", expand=True)

        # Raw textbox (hidden initially)
        self.raw_textbox = ctk.CTkTextbox(
            self.main_container,
            fg_color="#121215",
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none"
        )
        self.raw_textbox.insert("1.0", self.raw_markdown)
        self.raw_textbox.configure(state="disabled")

        # 4. Bottom Footer Bar
        footer = ctk.CTkFrame(self, fg_color="#121215", corner_radius=0, height=48)
        footer.pack(fill="x", side="bottom")

        # Active version badge at bottom
        latest_ver = self.parsed_releases[0]["version"] if self.parsed_releases else "2.1.2.a"
        ctk.CTkLabel(
            footer,
            text=f"Current Application Release: v{latest_ver}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#34d399"
        ).pack(side="left", padx=20, pady=10)

        close_btn = ctk.CTkButton(
            footer,
            text="Close",
            command=self.destroy,
            width=100,
            height=30,
            fg_color="#27272a",
            hover_color="#3f3f46",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        close_btn.pack(side="right", padx=20, pady=10)

        # Initial render
        self._render_cards()

    def _render_cards(self, query: str = ""):
        for w in self.cards_scroll.winfo_children():
            w.destroy()

        query_norm = query.lower().strip()
        matched_count = 0

        for rel in self.parsed_releases:
            ver = rel.get("version", "")
            date_str = rel.get("date", "")
            cats = rel.get("categories", {})

            # Filter check
            if query_norm:
                matches_ver = query_norm in ver.lower()
                matches_cat = any(query_norm in c.lower() for c in cats)
                matches_items = any(
                    query_norm in item["text"].lower() or any(query_norm in sub.lower() for sub in item["sub_items"])
                    for cat_items in cats.values()
                    for item in cat_items
                )
                if not (matches_ver or matches_cat or matches_items):
                    continue

            matched_count += 1
            card = ctk.CTkFrame(self.cards_scroll, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#27272a")
            card.pack(fill="x", pady=6)

            # Top bar: Version badge, Date, and Scope Badge
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=16, pady=(12, 6))

            # Version badge
            v_badge = ctk.CTkLabel(
                top_row,
                text=f"v{ver}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#38bdf8",
                fg_color="#082f49",
                corner_radius=6,
                padx=10,
                pady=4
            )
            v_badge.pack(side="left")

            if date_str:
                ctk.CTkLabel(
                    top_row,
                    text=f"Released {date_str}",
                    font=ctk.CTkFont(size=11),
                    text_color="#94a3b8"
                ).pack(side="left", padx=10)

            # Scope Tag based on 1.2.3.a rule
            scope_text, scope_bg, scope_fg = self._get_scope_badge(ver)
            s_badge = ctk.CTkLabel(
                top_row,
                text=scope_text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=scope_fg,
                fg_color=scope_bg,
                corner_radius=4,
                padx=6,
                pady=2
            )
            s_badge.pack(side="right")

            # Category sections
            for cat_name, items in cats.items():
                cat_color = self._get_category_color(cat_name)

                c_label = ctk.CTkLabel(
                    card,
                    text=f"◆ {cat_name.upper()}",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=cat_color
                )
                c_label.pack(anchor="w", padx=16, pady=(8, 2))

                for item in items:
                    txt = item["text"]
                    # Render primary bullet
                    item_frame = ctk.CTkFrame(card, fg_color="transparent")
                    item_frame.pack(fill="x", padx=20, pady=(2, 2))

                    clean_txt = self._format_bullet_text(txt)
                    b_lbl = ctk.CTkLabel(
                        item_frame,
                        text=f"• {clean_txt}",
                        font=ctk.CTkFont(size=12),
                        text_color="#e2e8f0",
                        wraplength=720,
                        justify="left"
                    )
                    b_lbl.pack(anchor="w")

                    # Render nested sub-bullets if present
                    for sub in item["sub_items"]:
                        clean_sub = self._format_bullet_text(sub)
                        sub_lbl = ctk.CTkLabel(
                            card,
                            text=f"    ↳ {clean_sub}",
                            font=ctk.CTkFont(size=11),
                            text_color="#94a3b8",
                            wraplength=700,
                            justify="left"
                        )
                        sub_lbl.pack(anchor="w", padx=26, pady=(0, 2))

            ctk.CTkLabel(card, text="").pack(pady=4)

        if matched_count == 0:
            no_match = ctk.CTkLabel(
                self.cards_scroll,
                text=f"No changelog entries matched '{query}'.",
                font=ctk.CTkFont(size=13),
                text_color="#71717a"
            )
            no_match.pack(pady=40)

    def _get_scope_badge(self, ver: str):
        parts = ver.split(".")
        if len(parts) >= 1 and parts[0] in ("1", "2") and len(parts) == 1:
            return "MAJOR RELEASE", "#450a0a", "#fecdd3"
        if len(parts) >= 2 and parts[1] != "0" and (len(parts) == 2 or parts[2] == "0"):
            return "MAJOR REWORK", "#312e81", "#c7d2fe"
        if len(parts) >= 3 and parts[2] != "0" and (len(parts) == 3 or parts[3] == "0"):
            return "FEATURE UPDATE", "#064e3b", "#a7f3d0"
        if len(parts) >= 4 and parts[3] in ("a", "b", "c", "d", "e", "f"):
            return "PATCH / BUG FIX", "#78350f", "#fde68a"
        return "RELEASE", "#18181b", "#94a3b8"

    def _get_category_color(self, cat_name: str) -> str:
        cn = cat_name.lower()
        if "add" in cn:
            return "#38bdf8"
        if "fix" in cn:
            return "#fbbf24"
        if "rework" in cn or "change" in cn:
            return "#34d399"
        if "security" in cn:
            return "#c084fc"
        return "#a1a1aa"

    def _format_bullet_text(self, text: str) -> str:
        """Strips markdown bold asterisks for clean label rendering."""
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        return clean

    def _on_filter_changed(self):
        query = self.search_entry.get().strip()
        self._render_cards(query)

    def _toggle_view_mode(self):
        if self.current_view_mode == "formatted":
            self.current_view_mode = "raw"
            self.cards_scroll.pack_forget()
            self.raw_textbox.pack(fill="both", expand=True)
            self.toggle_view_btn.configure(text="📋 Formatted View", text_color="#38bdf8")
        else:
            self.current_view_mode = "formatted"
            self.raw_textbox.pack_forget()
            self.cards_scroll.pack(fill="both", expand=True)
            self.toggle_view_btn.configure(text="📝 Raw Markdown", text_color="#94a3b8")
