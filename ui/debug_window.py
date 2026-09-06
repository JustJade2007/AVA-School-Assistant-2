"""
Anti-Capture Cloaked Debug Console & Error Diagnostic Window for AVA School Assistant 2.
Provides real-time log streaming, log level filtering, search querying,
full Python exception tracebacks, and copy-to-clipboard error diagnostics.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from typing import Optional, List, Dict, Any

from core.cloaking import apply_anti_capture
from core.logger import (
    get_logger,
    get_log_buffer,
    get_log_file_path,
    get_log_directory,
    clear_log_file,
    is_debug_mode,
    set_debug_mode,
    LogEntry
)
from core.error_handler import ErrorDiagnostic

logger = get_logger("debug_ui")


class DebugWindow(ctk.CTkToplevel):
    """Cloaked diagnostic and log console window for debug users."""

    def __init__(
        self,
        master=None,
        engine=None,
        open_error_tab: bool = False,
        initial_error: Optional[ErrorDiagnostic] = None
    ):
        super().__init__(master)
        self.engine = engine
        self.log_buffer = get_log_buffer()
        self.active_error: Optional[ErrorDiagnostic] = initial_error or (engine.last_error if engine else None)

        self.title("AVA Assistant - Debug & Diagnostics")
        self.geometry("780x620")
        self.minsize(650, 480)
        self.configure(fg_color="#18181b")

        # Window configuration
        self.attributes("-topmost", True)

        self._auto_scroll = True
        self._search_query = ""
        self._current_level = "ALL"

        self._build_ui()
        self._apply_anti_capture_cloak()

        # Populate logs and error
        self._refresh_logs_view()
        self._display_error_diagnostic(self.active_error)

        # Register real-time log listener
        self.log_buffer.add_listener(self._on_log_entry)
        if self.engine:
            self.engine.add_error_listener(self._on_engine_error)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if open_error_tab:
            self.tabs.set("⚠️ Error Diagnostics")

    def _apply_anti_capture_cloak(self):
        """Ensures the debug window is cloaked from screen recording."""
        self.after(150, lambda: apply_anti_capture(self, enable=True))

    def _build_ui(self):
        # Header banner
        header = ctk.CTkFrame(self, fg_color="#27272a", corner_radius=8, height=44)
        header.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            header,
            text="🐞 AVA SYSTEM LOGS & ERROR DIAGNOSTICS",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#60a5fa"
        ).pack(side="left", padx=12, pady=8)

        self.badge_cloak = ctk.CTkLabel(
            header,
            text="🛡️ CLOAKED",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#10b981"
        )
        self.badge_cloak.pack(side="left", padx=4)

        # Debug mode quick toggle
        self.switch_debug = ctk.CTkSwitch(
            header,
            text="Verbose Debug Mode",
            font=ctk.CTkFont(size=11),
            command=self._on_debug_toggle
        )
        self.switch_debug.pack(side="right", padx=12)
        if is_debug_mode():
            self.switch_debug.select()
        else:
            self.switch_debug.deselect()

        # Tabs: Live Logs & Error Diagnostics
        self.tabs = ctk.CTkTabview(
            self,
            fg_color="#27272a",
            segmented_button_selected_color="#2563eb",
            corner_radius=8
        )
        self.tabs.pack(fill="both", expand=True, padx=12, pady=6)

        self.tab_logs = self.tabs.add("📜 Live Log Console")
        self.tab_errors = self.tabs.add("⚠️ Error Diagnostics")

        self._build_logs_tab()
        self._build_errors_tab()

    # --- TAB 1: LIVE LOG CONSOLE ---
    def _build_logs_tab(self):
        f = self.tab_logs

        # Filter bar
        filter_bar = ctk.CTkFrame(f, fg_color="transparent")
        filter_bar.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(filter_bar, text="Level:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        self.combo_level = ctk.CTkComboBox(
            filter_bar,
            values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
            width=100,
            command=self._on_level_changed
        )
        self.combo_level.set("ALL")
        self.combo_level.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(filter_bar, text="Search:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(4, 4))
        self.entry_search = ctk.CTkEntry(filter_bar, placeholder_text="Filter logs...", width=180)
        self.entry_search.pack(side="left", padx=(0, 10))
        self.entry_search.bind("<KeyRelease>", self._on_search_typed)

        self.chk_autoscroll = ctk.CTkCheckBox(
            filter_bar,
            text="Auto-scroll",
            font=ctk.CTkFont(size=11),
            command=self._on_autoscroll_toggle
        )
        self.chk_autoscroll.select()
        self.chk_autoscroll.pack(side="left", padx=4)

        self.lbl_log_count = ctk.CTkLabel(
            filter_bar,
            text="0 entries",
            font=ctk.CTkFont(size=10),
            text_color="#9ca3af"
        )
        self.lbl_log_count.pack(side="right", padx=4)

        # Monospaced text console area
        console_frame = ctk.CTkFrame(f, fg_color="#18181b", corner_radius=6)
        console_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Using Tkinter Text for fast syntax tagging and smooth autoscroll
        self.text_console = tk.Text(
            console_frame,
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            font=("Consolas", 10),
            wrap="none",
            borderwidth=0,
            highlightthickness=0
        )
        self.scroll_y = tk.Scrollbar(console_frame, orient="vertical", command=self.text_console.yview)
        self.scroll_x = tk.Scrollbar(console_frame, orient="horizontal", command=self.text_console.xview)
        self.text_console.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)

        self.scroll_y.pack(side="right", fill="y")
        self.scroll_x.pack(side="bottom", fill="x")
        self.text_console.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        # Color tags
        self.text_console.tag_config("TIME", foreground="#64748b")
        self.text_console.tag_config("DEBUG", foreground="#38bdf8")
        self.text_console.tag_config("INFO", foreground="#10b981")
        self.text_console.tag_config("WARNING", foreground="#f59e0b")
        self.text_console.tag_config("ERROR", foreground="#ef4444", font=("Consolas", 10, "bold"))
        self.text_console.tag_config("LOGGER", foreground="#a78bfa")
        self.text_console.tag_config("TRACEBACK", foreground="#f87171")

        # Bottom actions bar
        action_bar = ctk.CTkFrame(f, fg_color="transparent")
        action_bar.pack(fill="x", padx=8, pady=(4, 8))

        ctk.CTkButton(
            action_bar,
            text="📋 Copy All",
            width=100,
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._copy_all_logs
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            action_bar,
            text="💾 Save Log As...",
            width=120,
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._save_logs_to_file
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            action_bar,
            text="📁 Open Logs Folder",
            width=130,
            height=28,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._open_logs_folder
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            action_bar,
            text="🧹 Clear Logs",
            width=100,
            height=28,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self._clear_logs
        ).pack(side="right", padx=4)

    # --- TAB 2: ERROR DIAGNOSTICS ---
    def _build_errors_tab(self):
        f = self.tab_errors

        # Scrollable container
        self.error_container = ctk.CTkScrollableFrame(f, fg_color="transparent")
        self.error_container.pack(fill="both", expand=True, padx=8, pady=8)

        # Status header card
        self.card_error_header = ctk.CTkFrame(self.error_container, fg_color="#18181b", corner_radius=8, border_width=1, border_color="#ef4444")
        self.card_error_header.pack(fill="x", pady=(0, 8))

        self.lbl_err_title = ctk.CTkLabel(
            self.card_error_header,
            text="No Errors Logged",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#10b981"
        )
        self.lbl_err_title.pack(anchor="w", padx=12, pady=(10, 2))

        self.lbl_err_meta = ctk.CTkLabel(
            self.card_error_header,
            text="System running normally. No active failure recorded.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#9ca3af"
        )
        self.lbl_err_meta.pack(anchor="w", padx=12, pady=(0, 10))

        # Full message card
        ctk.CTkLabel(self.error_container, text="Error Message:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(4, 2))
        self.card_err_msg = ctk.CTkFrame(self.error_container, fg_color="#18181b", corner_radius=6)
        self.card_err_msg.pack(fill="x", pady=(0, 8))

        self.lbl_err_msg = ctk.CTkLabel(
            self.card_err_msg,
            text="None",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#fca5a5",
            wraplength=700,
            justify="left"
        )
        self.lbl_err_msg.pack(anchor="w", padx=12, pady=10)

        # Troubleshooting recommendations card
        ctk.CTkLabel(self.error_container, text="Troubleshooting Recommendation:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(4, 2))
        self.card_err_hint = ctk.CTkFrame(self.error_container, fg_color="#1e293b", corner_radius=6, border_width=1, border_color="#3b82f6")
        self.card_err_hint.pack(fill="x", pady=(0, 8))

        self.lbl_err_hint = ctk.CTkLabel(
            self.card_err_hint,
            text="No action needed.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#93c5fd",
            wraplength=700,
            justify="left"
        )
        self.lbl_err_hint.pack(anchor="w", padx=12, pady=10)

        # Python Stack Trace Card
        ctk.CTkLabel(self.error_container, text="Python Exception Traceback:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(4, 2))
        self.card_err_tb = ctk.CTkFrame(self.error_container, fg_color="#0f172a", corner_radius=6)
        self.card_err_tb.pack(fill="both", expand=True, pady=(0, 8))

        self.text_err_tb = tk.Text(
            self.card_err_tb,
            bg="#0f172a",
            fg="#f87171",
            font=("Consolas", 10),
            height=12,
            wrap="none",
            borderwidth=0,
            highlightthickness=0
        )
        tb_scroll_y = tk.Scrollbar(self.card_err_tb, orient="vertical", command=self.text_err_tb.yview)
        self.text_err_tb.configure(yscrollcommand=tb_scroll_y.set)
        tb_scroll_y.pack(side="right", fill="y")
        self.text_err_tb.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        # Action buttons for error
        err_action_bar = ctk.CTkFrame(f, fg_color="transparent")
        err_action_bar.pack(fill="x", padx=8, pady=(0, 8))

        self.btn_copy_diagnostic = ctk.CTkButton(
            err_action_bar,
            text="📋 Copy Diagnostic Report",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=30,
            command=self._copy_diagnostic_report
        )
        self.btn_copy_diagnostic.pack(side="left", padx=4)

        ctk.CTkButton(
            err_action_bar,
            text="🔄 Refresh",
            width=100,
            height=30,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda: self._display_error_diagnostic(self.engine.last_error if self.engine else self.active_error)
        ).pack(side="left", padx=4)

    # --- Live Log Handling ---
    def _on_log_entry(self, entry: LogEntry):
        """Called asynchronously when any module logs a record."""
        self.after(0, lambda: self._append_single_log(entry))

    def _append_single_log(self, entry: LogEntry):
        if not self.winfo_exists():
            return

        # Check filter
        if self._current_level != "ALL":
            target_level_no = getattr(sys.modules.get("logging", None), self._current_level, 20)
            if entry.level_no < target_level_no:
                return

        if self._search_query:
            q = self._search_query.lower()
            if q not in entry.message.lower() and q not in entry.logger_name.lower():
                return

        self._render_entry_to_text(entry)

        if self._auto_scroll:
            self.text_console.see(tk.END)

        self._update_log_count_label()

    def _render_entry_to_text(self, entry: LogEntry):
        self.text_console.insert(tk.END, f"[{entry.formatted_time}] ", "TIME")
        self.text_console.insert(tk.END, f"[{entry.level_name:<7}] ", entry.level_name)
        self.text_console.insert(tk.END, f"[{entry.logger_name}] ", "LOGGER")
        self.text_console.insert(tk.END, f"{entry.message}\n")

        if entry.traceback:
            self.text_console.insert(tk.END, f"{entry.traceback}\n", "TRACEBACK")

    def _refresh_logs_view(self):
        """Re-populates the entire text console according to active filters."""
        self.text_console.delete("1.0", tk.END)
        entries = self.log_buffer.get_entries(
            level=self._current_level,
            search=self._search_query
        )

        for e in entries:
            self._render_entry_to_text(e)

        if self._auto_scroll:
            self.text_console.see(tk.END)

        self._update_log_count_label()

    def _update_log_count_label(self):
        visible = len(self.log_buffer.get_entries(level=self._current_level, search=self._search_query))
        total = len(self.log_buffer.get_entries())
        self.lbl_log_count.configure(text=f"{visible} / {total} entries")

    def _on_level_changed(self, level: str):
        self._current_level = level.upper()
        self._refresh_logs_view()

    def _on_search_typed(self, event=None):
        self._search_query = self.entry_search.get().strip()
        self._refresh_logs_view()

    def _on_autoscroll_toggle(self):
        self._auto_scroll = bool(self.chk_autoscroll.get())
        if self._auto_scroll:
            self.text_console.see(tk.END)

    def _on_debug_toggle(self):
        enabled = bool(self.switch_debug.get())
        set_debug_mode(enabled)
        if self.engine and hasattr(self.engine, "config_manager"):
            self.engine.config_manager.update(debug_mode=enabled)

    # --- Error Diagnostics Display ---
    def _on_engine_error(self, diagnostic: ErrorDiagnostic):
        """Dispatched when the engine catches an unhandled error."""
        self.active_error = diagnostic
        self.after(0, lambda: self._display_error_diagnostic(diagnostic))

    def _display_error_diagnostic(self, diagnostic: Optional[ErrorDiagnostic]):
        if not self.winfo_exists():
            return

        if not diagnostic:
            self.card_error_header.configure(border_color="#10b981")
            self.lbl_err_title.configure(text="✔ System Normal - No Errors Logged", text_color="#10b981")
            self.lbl_err_meta.configure(text="No active exceptions or failed operations.")
            self.lbl_err_msg.configure(text="No recent errors encountered.", text_color="#9ca3af")
            self.lbl_err_hint.configure(text="No action required.")
            self.text_err_tb.delete("1.0", tk.END)
            self.text_err_tb.insert(tk.END, "Traceback empty.")
            return

        self.card_error_header.configure(border_color="#ef4444")
        self.lbl_err_title.configure(
            text=f"✖ {diagnostic.title}",
            text_color="#ef4444"
        )
        meta_str = f"Timestamp: {diagnostic.timestamp}  |  Component: {diagnostic.component}  |  Type: {diagnostic.exception_type}"
        self.lbl_err_meta.configure(text=meta_str)

        self.lbl_err_msg.configure(text=diagnostic.message, text_color="#fca5a5")
        self.lbl_err_hint.configure(text=diagnostic.troubleshooting_hint)

        self.text_err_tb.delete("1.0", tk.END)
        self.text_err_tb.insert(tk.END, diagnostic.traceback_str or "No traceback attached.")

    # --- Action Buttons ---
    def _copy_all_logs(self):
        text = self.text_console.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", f"Copied {len(text.splitlines())} log lines to clipboard.")

    def _copy_diagnostic_report(self):
        diag = self.active_error or (self.engine.last_error if self.engine else None)
        if not diag:
            messagebox.showinfo("No Error", "No active error diagnostic report to copy.")
            return

        text = diag.to_clipboard_text()
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Report Copied", "Full error report and traceback copied to clipboard!")

    def _save_logs_to_file(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Log files", "*.log"), ("All files", "*.*")],
            initialfile=f"ava_debug_logs.txt"
        )
        if filepath:
            try:
                content = self.text_console.get("1.0", tk.END)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                messagebox.showinfo("Saved", f"Logs saved successfully to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Could not save logs: {e}")

    def _open_logs_folder(self):
        folder = get_log_directory()
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                messagebox.showinfo("Logs Directory", f"Logs folder location:\n{folder}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open directory: {e}")

    def _clear_logs(self):
        if messagebox.askyesno("Clear Logs", "Are you sure you want to clear in-memory logs?"):
            self.log_buffer.clear()
            self.text_console.delete("1.0", tk.END)
            self._update_log_count_label()

    def _on_close(self):
        # Remove listener on close
        self.log_buffer.remove_listener(self._on_log_entry)
        self.destroy()
