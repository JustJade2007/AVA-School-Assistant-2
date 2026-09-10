"""
Snip Box & Solve Overlay for AVA School Assistant 2.
Allows user to drag-select any tricky or nested question box on screen with pixel precision.
The selected sub-region is captured and solved directly by the AI pipeline.
Fully cloaked via WDA_EXCLUDEFROMCAPTURE so screen recorders never capture the snip UI.
"""

import logging
import tkinter as tk
from typing import Callable, Optional, Tuple
from core.cloaking import apply_anti_capture

logger = logging.getLogger(__name__)


class SnippingOverlay:
    """Fullscreen cloaked drag-selection overlay for snipping question boxes."""

    def __init__(self, master=None, on_snip_complete: Optional[Callable[[Tuple[int, int, int, int]], None]] = None):
        self.master = master
        self.on_snip_complete = on_snip_complete
        self.window: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None

        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.text_id = None
        self.badge_id = None

    def start(self):
        """Opens the fullscreen snipping overlay."""
        if self.window is not None and self.window.winfo_exists():
            try:
                self.window.lift()
                self.window.focus_force()
            except Exception:
                pass
            return

        self.window = tk.Toplevel(self.master)
        self.window.title("AVA_Snip_Tool_Cloaked")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.35)
        self.window.config(bg="#050811")
        self.window.config(cursor="crosshair")

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        self.window.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self.window,
            width=screen_w,
            height=screen_h,
            bg="#050811",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Apply anti-screen capture affinity
        self.window.update()
        apply_anti_capture(self.window)

        # Draw banner / instruction hint
        hint_text = "✂️ AVA Snip Mode: Drag a box around any question or sub-box  •  [Esc] to Cancel"
        self.canvas.create_rectangle(
            screen_w // 2 - 280, 24, screen_w // 2 + 280, 68,
            fill="#0f172a", outline="#38bdf8", width=2
        )
        self.canvas.create_text(
            screen_w // 2, 46,
            text=hint_text,
            fill="#f8fafc",
            font=("Segoe UI", 12, "bold")
        )

        # Key and mouse bindings
        self.window.bind("<ButtonPress-1>", self._on_button_press)
        self.window.bind("<B1-Motion>", self._on_move_press)
        self.window.bind("<ButtonRelease-1>", self._on_button_release)
        self.window.bind("<Escape>", self._on_cancel)
        self.window.focus_set()

    def _on_button_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root

        # Reset drawn rectangle
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        if self.text_id:
            self.canvas.delete(self.text_id)
            self.text_id = None

        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#38bdf8", width=2, dash=(6, 4), fill="#38bdf8", stipple="gray25"
        )

    def _on_move_press(self, event):
        cur_x = event.x_root
        cur_y = event.y_root

        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

        # Dimension badge
        w = abs(cur_x - self.start_x)
        h = abs(cur_y - self.start_y)
        badge_x = max(self.start_x, cur_x) + 10
        badge_y = max(self.start_y, cur_y) + 10

        if not self.text_id:
            self.text_id = self.canvas.create_text(
                badge_x, badge_y,
                text=f"{w} × {h} px",
                fill="#38bdf8",
                font=("Consolas", 10, "bold"),
                anchor="nw"
            )
        else:
            self.canvas.coords(self.text_id, badge_x, badge_y)
            self.canvas.itemconfig(self.text_id, text=f"{w} × {h} px")

    def _on_button_release(self, event):
        end_x = event.x_root
        end_y = event.y_root

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        w = x2 - x1
        h = y2 - y1

        self._close()

        if w >= 25 and h >= 25:
            logger.info(f"Snip selected region: ({x1}, {y1}) to ({x2}, {y2}) [{w}x{h}]")
            if self.on_snip_complete:
                self.on_snip_complete((x1, y1, x2, y2))
        else:
            logger.info("Snip cancelled or region too small (< 25px).")

    def _on_cancel(self, event=None):
        logger.info("Snip cancelled by user via Escape.")
        self._close()

    def _close(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
            self.canvas = None
            self.rect_id = None
            self.text_id = None
