"""
Asset and Icon Loader for AVA School Assistant 2.
Provides cross-platform path resolution for application assets, icons,
and window icon application for CustomTkinter / Tkinter windows.
"""

import os
import sys
import ctypes
from typing import Optional, Tuple
from PIL import Image
import customtkinter as ctk

from core.logger import get_logger

logger = get_logger("ui.asset_loader")

_APP_USER_MODEL_ID_SET = False


def set_windows_app_user_model_id(app_id: str = "avaschoolassistant.v2.app") -> None:
    """
    Sets the Windows AppUserModelID so the taskbar groups AVA under its own identity
    and displays the custom application icon instead of python.exe.
    """
    global _APP_USER_MODEL_ID_SET
    if _APP_USER_MODEL_ID_SET:
        return

    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            _APP_USER_MODEL_ID_SET = True
            logger.debug(f"Explicit AppUserModelID set: {app_id}")
        except Exception as e:
            logger.debug(f"Could not set AppUserModelID: {e}")


def get_asset_path(filename: str) -> Optional[str]:
    """
    Locates an asset file whether running in development or packaged via PyInstaller.
    """
    candidates = []

    # 1. PyInstaller temporary extraction directory (_MEIPASS)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "ui", "images", filename))
        candidates.append(os.path.join(sys._MEIPASS, filename))

    # 2. Relative to ui/images directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(current_dir, "images", filename))
    candidates.append(os.path.join(current_dir, filename))

    # 3. Relative to workspace or current working directory
    candidates.append(os.path.join(os.getcwd(), "ui", "images", filename))
    candidates.append(os.path.join(os.getcwd(), filename))

    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)

    return None


def get_icon_ico_path() -> Optional[str]:
    """Returns absolute path to icon.ico."""
    return get_asset_path("icon.ico")


def get_logo_image_path() -> Optional[str]:
    """Returns absolute path to primary logo image (JPEG or PNG)."""
    return get_asset_path("AVA-logo.jpeg") or get_asset_path("icon.png")


def get_logo_ctk_image(size: Tuple[int, int] = (32, 32)) -> Optional[ctk.CTkImage]:
    """
    Returns a high-DPI ctk.CTkImage for the AVA logo.
    """
    img_path = get_asset_path("icon.png") or get_asset_path("AVA-logo.jpeg")
    if not img_path:
        return None

    try:
        pil_img = Image.open(img_path)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
    except Exception as e:
        logger.warning(f"Failed to load CTkImage from {img_path}: {e}")
        return None


def apply_window_icon(window) -> None:
    """
    Applies the AVA icon to a Tk or CustomTkinter window (root or toplevel).
    Sets the icon for both the Windows OS title bar and the Windows taskbar.
    """
    set_windows_app_user_model_id()
    ico_path = get_icon_ico_path()

    if not ico_path or not os.path.exists(ico_path):
        return

    # Direct application
    try:
        window.iconbitmap(ico_path)
    except Exception as e:
        logger.debug(f"Immediate iconbitmap call failed: {e}")

    # Delayed safety re-apply to ensure Windows OS frame has been mapped
    try:
        if hasattr(window, "after"):
            window.after(100, lambda: _safe_reapply_icon(window, ico_path))
    except Exception:
        pass


def _safe_reapply_icon(window, ico_path: str) -> None:
    try:
        if window.winfo_exists():
            window.iconbitmap(ico_path)
    except Exception:
        pass
