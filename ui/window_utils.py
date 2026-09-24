"""
Window Utilities for AVA School Assistant 2.
Provides cross-platform and Win32 helpers for:
1. Ensuring Windows Taskbar and Alt-Tab presence (WS_EX_APPWINDOW).
2. Clean minimization and restore event handling without DWM thumbnail or taskbar dropout.
3. Native WM_SETICON registration for both small and large titlebar/taskbar icons.
"""

import sys
import os
import ctypes
from typing import Optional, Callable
from core.logger import get_logger
from core.cloaking import get_window_hwnd, apply_anti_capture, is_windows

logger = get_logger("ui.window_utils")

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_NOACTIVATE = 0x0010

WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040


def ensure_taskbar_presence(window) -> bool:
    """
    Ensures a Tkinter/CustomTkinter window has the WS_EX_APPWINDOW style and lacks
    WS_EX_TOOLWINDOW. This guarantees that the window appears on the Windows Taskbar
    and in the Alt+Tab application switcher both when visible and when minimized.
    """
    if not is_windows():
        return False

    hwnd = get_window_hwnd(window)
    if not hwnd:
        return False

    try:
        user32 = ctypes.windll.user32
        current_exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_exstyle = (current_exstyle & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW

        GWL_STYLE = -16
        WS_MINIMIZEBOX = 0x00020000
        WS_SYSMENU = 0x00080000
        WS_CAPTION = 0x00C00000
        current_style = user32.GetWindowLongW(hwnd, GWL_STYLE)

        # If borderless overrideredirect window, strip WS_CAPTION while ensuring WS_MINIMIZEBOX
        is_borderless = False
        try:
            if hasattr(window, "wm_overrideredirect") and str(window.wm_overrideredirect()) in ("1", "True"):
                is_borderless = True
        except Exception:
            pass

        if is_borderless:
            new_style = (current_style | WS_MINIMIZEBOX | WS_SYSMENU) & ~WS_CAPTION
        else:
            new_style = current_style | WS_MINIMIZEBOX | WS_SYSMENU

        changed = False
        if new_exstyle != current_exstyle:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_exstyle)
            changed = True
        if new_style != current_style:
            user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
            changed = True

        if changed:
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE
            )
            logger.debug(f"Taskbar presence styles updated for HWND {hwnd}")
        return True
    except Exception as e:
        logger.debug(f"Failed to set WS_EX_APPWINDOW for HWND {hwnd}: {e}")
        return False


def set_native_window_icon(window, ico_path: Optional[str] = None) -> bool:
    """
    Explicitly registers 16x16 and 32x32 icons with the Win32 window manager via WM_SETICON.
    This ensures that borderless, overrideredirect, or custom-decorated windows maintain
    their custom branding in the Windows Taskbar and Alt+Tab switcher.
    """
    if not is_windows() or not ico_path or not os.path.exists(ico_path):
        return False

    hwnd = get_window_hwnd(window)
    if not hwnd:
        return False

    try:
        user32 = ctypes.windll.user32
        # Load big icon (32x32)
        h_icon_big = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
        )
        # Load small icon (16x16)
        h_icon_small = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )

        if h_icon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
        if h_icon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)

        logger.debug(f"Native Win32 icons set for HWND {hwnd}")
        return True
    except Exception as e:
        logger.debug(f"Failed to set native window icon: {e}")
        return False


def attach_minimize_restore_handlers(
    window,
    is_cloaked_getter: Optional[Callable[[], bool]] = None,
    on_minimize: Optional[Callable[[], None]] = None,
    on_restore: Optional[Callable[[], None]] = None
) -> None:
    """
    Attaches event handlers to manage display affinity transitions during minimize/restore.
    When a window with WDA_EXCLUDEFROMCAPTURE is minimized, DWM cannot render a live thumbnail,
    which can cause shell taskbar / Alt-Tab enumeration glitches. By temporarily lifting
    capture exclusion while minimized and seamlessly re-applying it when restored, the window
    minimizes and restores normally without leaving the taskbar or switcher.
    """
    last_state = {"state": "normal"}

    def _check_state_change(event=None):
        try:
            if not window.winfo_exists():
                return

            hwnd = get_window_hwnd(window)
            if not hwnd:
                return

            user32 = ctypes.windll.user32
            is_iconic = bool(user32.IsIconic(hwnd))

            if is_iconic and last_state["state"] != "iconic":
                # Window just transitioned to MINIMIZED
                last_state["state"] = "iconic"
                logger.debug(f"Window {hwnd} minimized. Pausing anti-capture for clean DWM taskbar display.")
                # Pause capture exclusion so DWM handles taskbar icon cleanly
                apply_anti_capture(hwnd, enable=False)
                if on_minimize:
                    try:
                        on_minimize()
                    except Exception as ex:
                        logger.debug(f"on_minimize callback error: {ex}")

            elif not is_iconic and last_state["state"] == "iconic":
                # Window just RESTORED from minimize
                last_state["state"] = "normal"
                logger.debug(f"Window {hwnd} restored. Re-applying taskbar presence and anti-capture.")
                ensure_taskbar_presence(window)

                # Re-apply cloaking if the window was configured as cloaked
                should_cloak = True
                if is_cloaked_getter:
                    try:
                        should_cloak = is_cloaked_getter()
                    except Exception:
                        should_cloak = True

                if should_cloak:
                    apply_anti_capture(hwnd, enable=True)

                if on_restore:
                    try:
                        on_restore()
                    except Exception as ex:
                        logger.debug(f"on_restore callback error: {ex}")

        except Exception as e:
            logger.debug(f"Error in state change check: {e}")

    try:
        # Bind Unmap (occurs when window is minimized or withdrawn)
        window.bind("<Unmap>", lambda e: window.after(10, _check_state_change) if e.widget == window else None, add="+")
        # Bind Map (occurs when window is restored / mapped to display)
        window.bind("<Map>", lambda e: window.after(10, _check_state_change) if e.widget == window else None, add="+")
    except Exception as e:
        logger.debug(f"Could not bind state change events on {window}: {e}")
