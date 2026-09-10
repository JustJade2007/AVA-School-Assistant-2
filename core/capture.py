"""
Screen Capture module for AVA School Assistant 2.
Provides high-DPI aware desktop screenshots, region-of-interest (ROI) cropping,
image compression, and coordinate translation.
"""

import io
import base64
import sys
import ctypes
from typing import Tuple, Optional, Dict, Any
from PIL import Image
import mss


from core.logger import get_logger

logger = get_logger("capture")


# Ensure High-DPI Awareness on Windows so coordinates match 1:1 with physical pixels
def set_dpi_awareness():
    if sys.platform == "win32":
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.debug("DPI Awareness set to PROCESS_PER_MONITOR_DPI_AWARE.")
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.debug("DPI Awareness set via SetProcessDPIAware fallback.")
            except Exception as e:
                logger.warning(f"Could not set DPI awareness: {e}")


set_dpi_awareness()


class ScreenCapture:
    """Handles multi-monitor screen capture and image encoding."""

    def __init__(self):
        try:
            if hasattr(mss, "MSS"):
                self.sct = mss.MSS()
            else:
                self.sct = mss.mss()
        except Exception:
            self.sct = None

    def get_screen_bounds(self, monitor_idx: int = 1) -> Dict[str, int]:
        """
        Returns bounding box for a monitor.
        Monitor 0 is the full virtual screen containing all monitors.
        Monitor 1 is the primary monitor.
        """
        if self.sct and monitor_idx < len(self.sct.monitors):
            return self.sct.monitors[monitor_idx]
        # Fallback to system metrics if mss monitors not accessible
        if sys.platform == "win32":
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            return {"top": 0, "left": 0, "width": w, "height": h}
        return {"top": 0, "left": 0, "width": 1920, "height": 1080}

    def capture_screen(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        monitor_idx: int = 1
    ) -> Image.Image:
        """
        Captures the screen or a specific region.
        :param region: (left, top, right, bottom) in global screen pixels, or None for whole monitor.
        :param monitor_idx: Monitor index (default 1 = primary monitor).
        :return: PIL Image (RGB format).
        """
        if region is not None:
            x1, y1, x2, y2 = region
            # Ensure coordinates are sorted
            left = min(x1, x2)
            top = min(y1, y2)
            width = max(abs(x2 - x1), 10)
            height = max(abs(y2 - y1), 10)
            bbox = {"top": top, "left": left, "width": width, "height": height}
        else:
            bbox = self.get_screen_bounds(monitor_idx)

        if not self.sct:
            if hasattr(mss, "MSS"):
                self.sct = mss.MSS()
            else:
                self.sct = mss.mss()

        try:
            sct_img = self.sct.grab(bbox)
            # Convert raw BGRA to PIL Image RGB
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception as e:
            # When running headless or locked screen, provide a clear error message
            raise RuntimeError(
                f"Unable to capture screen: {e}. "
                "Ensure your workstation screen is unlocked and AVA is running with desktop session access."
            ) from e

    def capture_and_encode(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        monitor_idx: int = 1,
        max_dimension: int = 1920,
        quality: int = 90
    ) -> Tuple[str, int, int, float, float, int, int]:
        """
        Captures the screen, optionally scales down for API transfer efficiency,
        and encodes as Base64 JPEG.

        :return: (
            base64_string,
            encoded_width,
            encoded_height,
            scale_x,
            scale_y,
            offset_x,
            offset_y
        )
        Where:
            real_x = (ai_x * scale_x) + offset_x
            real_y = (ai_y * scale_y) + offset_y
        """
        img = self.capture_screen(region=region, monitor_idx=monitor_idx)
        orig_w, orig_h = img.size

        if region is not None:
            offset_x = min(region[0], region[2])
            offset_y = min(region[1], region[3])
        else:
            bounds = self.get_screen_bounds(monitor_idx)
            offset_x = bounds["left"]
            offset_y = bounds["top"]

        # Scale down if larger than max_dimension and max_dimension > 0
        scale = 1.0
        if max_dimension > 0 and max(orig_w, orig_h) > max_dimension:
            scale = max_dimension / float(max(orig_w, orig_h))
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            img_resized = img

        curr_w, curr_h = img_resized.size
        # Multipliers to convert image pixel coordinates back to real screen coordinates
        scale_x = orig_w / float(curr_w)
        scale_y = orig_h / float(curr_h)

        # Compress to JPEG
        buffer = io.BytesIO()
        img_resized.save(buffer, format="JPEG", quality=quality)
        base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return base64_data, curr_w, curr_h, scale_x, scale_y, offset_x, offset_y
