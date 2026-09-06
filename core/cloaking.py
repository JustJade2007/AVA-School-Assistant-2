"""
Anti-Screen Capture Cloaking module for Windows.
Hides designated overlay and UI windows from screen recording, screen sharing,
and screen grab tools using Windows 10/11 SetWindowDisplayAffinity.
"""

import sys
import ctypes
from typing import Union, Optional

from core.logger import get_logger

logger = get_logger("cloaking")

# Win32 Constants
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+ and Windows 11
GA_ROOT = 2


def is_windows() -> bool:
    return sys.platform == "win32"


def get_window_hwnd(window) -> Optional[int]:
    """
    Extracts the root HWND (top-level window handle) from a Tkinter or CustomTkinter window.
    """
    if isinstance(window, int):
        return window

    try:
        # Ensure window is updated so Win32 handles are created
        if hasattr(window, "update_idletasks"):
            window.update_idletasks()

        if hasattr(window, "winfo_id"):
            raw_id = window.winfo_id()
            if is_windows():
                # GA_ROOT retrieves the root window handle by walking the parent chain
                root_hwnd = ctypes.windll.user32.GetAncestor(raw_id, GA_ROOT)
                if root_hwnd != 0:
                    return root_hwnd
            return raw_id
    except Exception as e:
        logger.error(f"Error getting HWND: {e}")

    return None


def apply_anti_capture(window_or_hwnd: Union[object, int], enable: bool = True) -> bool:
    """
    Applies or removes WDA_EXCLUDEFROMCAPTURE display affinity on the target window.
    When enabled, screen sharing (Discord, Zoom, Google Meet, Teams, LockDown Browser,
    OBS, screen recorders, and PrintScreen) will see right through the window.

    :param window_or_hwnd: Tkinter window, CustomTkinter window, or integer HWND
    :param enable: True to hide from screen capture, False to make visible to capture
    :return: True if successfully applied, False otherwise
    """
    if not is_windows():
        logger.warning("Anti-capture affinity is only supported on Windows.")
        return False

    hwnd = get_window_hwnd(window_or_hwnd)
    if not hwnd:
        logger.warning("Invalid HWND. Cannot apply display affinity.")
        return False

    affinity = WDA_EXCLUDEFROMCAPTURE if enable else WDA_NONE

    try:
        # Check if SetWindowDisplayAffinity is available
        user32 = ctypes.windll.user32
        if not hasattr(user32, "SetWindowDisplayAffinity"):
            logger.warning("SetWindowDisplayAffinity not available on this Windows version.")
            return False

        # Attempt WDA_EXCLUDEFROMCAPTURE first
        result = user32.SetWindowDisplayAffinity(hwnd, affinity)
        if result:
            state_str = "ENABLED (EXCLUDEFROMCAPTURE)" if enable else "DISABLED"
            logger.info(f"Anti-capture successfully {state_str} for HWND {hwnd}")
            return True

        # Fallback to WDA_MONITOR if WDA_EXCLUDEFROMCAPTURE failed (older Windows 10)
        if enable:
            logger.debug("ExcludeFromCapture returned false; falling back to WDA_MONITOR.")
            result_fallback = user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
            if result_fallback:
                logger.info(f"Anti-capture ENABLED (MONITOR fallback) for HWND {hwnd}")
                return True

        last_error = ctypes.GetLastError()
        logger.warning(f"SetWindowDisplayAffinity failed with error code: {last_error}")
        return False
    except Exception as e:
        logger.error(f"Exception applying display affinity: {e}")
        return False


def is_anti_capture_supported() -> bool:
    """Checks if the current operating system supports SetWindowDisplayAffinity."""
    if not is_windows():
        return False
    return hasattr(ctypes.windll.user32, "SetWindowDisplayAffinity")
