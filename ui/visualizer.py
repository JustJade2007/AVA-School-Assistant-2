"""
Cloaked Screen Target Visualizer for AVA School Assistant 2.
Draws temporary on-screen target highlights, click markers, and drag arrows
directly over target elements.
Fully cloaked via WDA_EXCLUDEFROMCAPTURE so screen recorders never capture the markers.
"""

import sys
import tkinter as tk
from typing import List, Dict, Any, Optional

from core.cloaking import apply_anti_capture, make_window_click_through


class CloakedVisualizer:
    """A full-screen transparent canvas that renders action target markers."""

    def __init__(self, master=None):
        self.master = master
        self.window: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self._clear_timer = None

    def _ensure_window(self):
        if self.window is not None and self.window.winfo_exists():
            return

        self.window = tk.Toplevel(self.master)
        self.window.title("AVA_Visualizer_Cloaked")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        # Transparent background setup for Windows
        # Use a chroma key color (e.g., magenta #ff00ff)
        chroma_key = "#010101"
        self.window.config(bg=chroma_key)
        self.window.attributes("-transparentcolor", chroma_key)

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        self.window.geometry(f"{screen_w}x{screen_h}+0+0")

        self.canvas = tk.Canvas(
            self.window,
            width=screen_w,
            height=screen_h,
            bg=chroma_key,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Apply anti-screen capture affinity and make window click-through
        self.window.update()
        apply_anti_capture(self.window)
        make_window_click_through(self.window)

    def draw_actions(
        self,
        actions: List[Dict[str, Any]],
        next_button: Optional[Dict[str, Any]] = None,
        check_button: Optional[Dict[str, Any]] = None,
        auto_clear_sec: float = 6.0
    ):
        """Draws circles, numbers, arrows, and button markers over proposed action coordinates."""
        self._ensure_window()
        self.canvas.delete("all")
        # Ensure click-through remains active after redraw
        make_window_click_through(self.window)

        step = 1
        for action in actions:
            x = action.get("screen_x", action.get("x"))
            y = action.get("screen_y", action.get("y"))
            action_type = action.get("type", "click")

            if x is not None and y is not None:
                x, y = int(x), int(y)

                # If bounding box is known (e.g. from fill-in box detection or box_2d), highlight the full box outline
                box_screen = action.get("box_screen")
                if box_screen and len(box_screen) == 4:
                    bx1, by1, bx2, by2 = int(box_screen[0]), int(box_screen[1]), int(box_screen[2]), int(box_screen[3])
                    self.canvas.create_rectangle(
                        bx1, by1, bx2, by2,
                        outline="#00ffcc", width=2, dash=(4, 2)
                    )

                # Outer glowing ring
                self.canvas.create_oval(
                    x - 22, y - 22, x + 22, y + 22,
                    outline="#00ffcc", width=3
                )
                self.canvas.create_oval(
                    x - 16, y - 16, x + 16, y + 16,
                    fill="#00ffcc", outline="#ffffff", width=1
                )
                # Step number text
                self.canvas.create_text(
                    x, y, text=str(step),
                    fill="#000000", font=("Arial", 11, "bold")
                )
                # Label
                desc = action.get("description", action_type)
                self.canvas.create_text(
                    x, y + 32, text=desc,
                    fill="#00ffcc", font=("Arial", 9, "bold")
                )
                step += 1

            elif action_type == "drag":
                fx = action.get("screen_from_x", action.get("from_x"))
                fy = action.get("screen_from_y", action.get("from_y"))
                tx = action.get("screen_to_x", action.get("to_x"))
                ty = action.get("screen_to_y", action.get("to_y"))
                if all(v is not None for v in [fx, fy, tx, ty]):
                    fx, fy, tx, ty = int(fx), int(fy), int(tx), int(ty)
                    # Line with arrow
                    self.canvas.create_line(
                        fx, fy, tx, ty,
                        arrow=tk.LAST, fill="#ffcc00", width=4, arrowshape=(14, 18, 6)
                    )
                    self.canvas.create_oval(fx - 10, fy - 10, fx + 10, fy + 10, fill="#ffcc00")

        # Check Answer button highlight (amber)
        if check_button and isinstance(check_button, dict):
            cx = check_button.get("screen_x", check_button.get("x"))
            cy = check_button.get("screen_y", check_button.get("y"))
            if cx is not None and cy is not None:
                cx, cy = int(cx), int(cy)
                c_box = check_button.get("box_screen")
                if c_box and len(c_box) == 4:
                    cbx1, cby1, cbx2, cby2 = int(c_box[0]), int(c_box[1]), int(c_box[2]), int(c_box[3])
                else:
                    cbx1, cby1, cbx2, cby2 = cx - 55, cy - 18, cx + 55, cy + 18

                self.canvas.create_rectangle(
                    cbx1, cby1, cbx2, cby2,
                    outline="#f59e0b", width=3
                )
                self.canvas.create_text(
                    cx, cby1 - 10, text="[CHECK ANSWER]",
                    fill="#f59e0b", font=("Arial", 9, "bold")
                )

        # Next button highlight (magenta)
        if next_button and isinstance(next_button, dict):
            nx = next_button.get("screen_x", next_button.get("x"))
            ny = next_button.get("screen_y", next_button.get("y"))
            if nx is not None and ny is not None:
                nx, ny = int(nx), int(ny)
                n_box = next_button.get("box_screen")
                if n_box and len(n_box) == 4:
                    nbx1, nby1, nbx2, nby2 = int(n_box[0]), int(n_box[1]), int(n_box[2]), int(n_box[3])
                else:
                    nbx1, nby1, nbx2, nby2 = nx - 45, ny - 18, nx + 45, ny + 18

                self.canvas.create_rectangle(
                    nbx1, nby1, nbx2, nby2,
                    outline="#ff0055", width=3
                )
                self.canvas.create_text(
                    nx, nby1 - 10, text="[NEXT BUTTON]",
                    fill="#ff0055", font=("Arial", 9, "bold")
                )

        # Auto clear after timeout
        if self._clear_timer is not None:
            self.window.after_cancel(self._clear_timer)
        self._clear_timer = self.window.after(int(auto_clear_sec * 1000), self.clear)

    def clear(self):
        """Clears all drawn target highlights."""
        if self.canvas is not None:
            self.canvas.delete("all")
        if self.window is not None and self.window.winfo_exists():
            self.window.withdraw()

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()

    def hide(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.withdraw()
