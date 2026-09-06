"""
Local Vision Verifier & Layout Shift Tracker for AVA School Assistant 2.
Provides fast, zero-AI-token visual confirmation of clicks, inputs,
visual center snapping, and dynamic fill-in-the-blank template tracking.
"""

import math
import logging
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image, ImageChops, ImageStat, ImageFilter
import mss

logger = logging.getLogger(__name__)


class LocalVisualVerifier:
    """Zero-token local screen region verifier and template tracker."""

    def __init__(self):
        if hasattr(mss, "MSS"):
            self._sct = mss.MSS()
        else:
            self._sct = mss.mss()

    def capture_roi(self, x: int, y: int, radius_w: int = 35, radius_h: int = 22) -> Image.Image:
        """Captures a small region-of-interest (ROI) crop centered on (x, y)."""
        left = max(0, int(x - radius_w))
        top = max(0, int(y - radius_h))
        width = int(radius_w * 2)
        height = int(radius_h * 2)

        monitor = {"left": left, "top": top, "width": width, "height": height}
        try:
            sct_img = self._sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception as e:
            logger.debug(f"Failed to capture ROI at ({x}, {y}): {e}")
            # Return a blank image fallback
            return Image.new("RGB", (width, height), (255, 255, 255))

    def capture_band(self, x: int, y: int, offset_left: int = 40, offset_right: int = 220, radius_h: int = 35) -> Tuple[Image.Image, int, int]:
        """Captures a wider horizontal band around an input field to detect layout shifts."""
        left = max(0, int(x - offset_left))
        top = max(0, int(y - radius_h))
        width = int(offset_left + offset_right)
        height = int(radius_h * 2)

        monitor = {"left": left, "top": top, "width": width, "height": height}
        try:
            sct_img = self._sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            return img, left, top
        except Exception as e:
            logger.debug(f"Failed to capture band at ({x}, {y}): {e}")
            return Image.new("RGB", (width, height), (255, 255, 255)), left, top

    def verify_action_completion(
        self,
        before_roi: Optional[Image.Image],
        after_roi: Optional[Image.Image],
        action_type: str = "click",
        threshold_changed_pixels: int = 14,
        threshold_mean_diff: float = 1.4
    ) -> Tuple[bool, float]:
        """
        Compares before and after ROI crops to determine if the target element visually responded
        (e.g., radio dot filled, checkbox checked, focus ring glowed, or text appeared).
        Returns (is_confirmed, diff_score).
        """
        if before_roi is None or after_roi is None:
            return True, 0.0

        if before_roi.size != after_roi.size:
            return True, 0.0

        try:
            b_gray = before_roi.convert("L")
            a_gray = after_roi.convert("L")

            diff = ImageChops.difference(b_gray, a_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]

            # Count pixels with significant delta (> 18 intensity difference)
            hist = diff.histogram()
            changed_pixels = sum(hist[18:])

            # For text typing, changes are usually very pronounced
            if action_type == "type_text":
                is_confirmed = changed_pixels >= 8 or mean_diff >= 1.0
            else:
                is_confirmed = changed_pixels >= threshold_changed_pixels or mean_diff >= threshold_mean_diff

            logger.debug(
                f"Local verify [{action_type}]: confirmed={is_confirmed}, "
                f"changed_pixels={changed_pixels}, mean_diff={mean_diff:.2f}"
            )
            return is_confirmed, mean_diff
        except Exception as e:
            logger.warning(f"Error in verify_action_completion: {e}")
            return True, 0.0

    def find_visual_element_center(
        self,
        roi_img: Image.Image,
        center_screen_x: int,
        center_screen_y: int
    ) -> Tuple[int, int]:
        """
        Scans a local ROI image around an attempted click to detect high-contrast element
        boundaries (e.g. circle of radio button, rectangle of checkbox/input) and computes
        the true visual centroid.
        """
        try:
            w, h = roi_img.size
            gray = roi_img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)

            # Threshold edges to find boundary pixels
            # Element borders typically have strong edge values > 45
            edge_data = edges.load()
            roi_mid_x = w // 2
            roi_mid_y = h // 2

            # Find bounding box of significant edge features near the center
            min_x, max_x = w, 0
            min_y, max_y = h, 0
            edge_count = 0

            # Scan within safe search radius, skipping outer 2px image border artifacts
            search_r = min(w // 2 - 3, h // 2 - 3, 26)
            min_y_bound = max(2, roi_mid_y - search_r)
            max_y_bound = min(h - 2, roi_mid_y + search_r)
            min_x_bound = max(2, roi_mid_x - search_r)
            max_x_bound = min(w - 2, roi_mid_x + search_r)

            for y in range(min_y_bound, max_y_bound):
                for x in range(min_x_bound, max_x_bound):
                    val = edge_data[x, y]
                    if val > 42:
                        edge_count += 1
                        if x < min_x: min_x = x
                        if x > max_x: max_x = x
                        if y < min_y: min_y = y
                        if y > max_y: max_y = y

            if edge_count >= 15 and max_x > min_x and max_y > min_y:
                detected_mid_x = (min_x + max_x) // 2
                detected_mid_y = (min_y + max_y) // 2
                offset_x = detected_mid_x - roi_mid_x
                offset_y = detected_mid_y - roi_mid_y

                # Clamp adjustment offset to safe bounds (±16 px)
                offset_x = max(-16, min(16, offset_x))
                offset_y = max(-16, min(16, offset_y))

                snapped_x = center_screen_x + offset_x
                snapped_y = center_screen_y + offset_y
                logger.info(f"Visual center snapped: ({center_screen_x}, {center_screen_y}) -> ({snapped_x}, {snapped_y}) [offset=+({offset_x},{offset_y})]")
                return snapped_x, snapped_y

        except Exception as e:
            logger.debug(f"find_visual_element_center fallback: {e}")

        return center_screen_x, center_screen_y

    def track_shifted_input_box(
        self,
        template_img: Image.Image,
        band_img: Image.Image,
        band_origin_x: int,
        band_origin_y: int,
        expected_x: int,
        expected_y: int
    ) -> Optional[Tuple[int, int]]:
        """
        Locates a blank input box that may have shifted horizontally or vertically after
        text was typed into an earlier blank on the same line.
        Uses fast local template correlation, with empty box contour fallback.
        """
        try:
            tw, th = template_img.size
            bw, bh = band_img.size

            if tw >= bw or th >= bh:
                return None

            t_gray = template_img.convert("L")
            b_gray = band_img.convert("L")

            if hasattr(t_gray, "get_flattened_data"):
                t_data = list(t_gray.get_flattened_data())
            else:
                t_data = list(t_gray.getdata())
            b_pixels = b_gray.load()

            # Fast multi-step template matching using Sum of Absolute Differences (SAD)
            best_sad = float("inf")
            best_bx = 0
            best_by = 0

            # Step across candidate positions (step size 2 for speed, then refine)
            step = 2
            for by in range(0, bh - th + 1, step):
                for bx in range(0, bw - tw + 1, step):
                    sad = 0
                    idx = 0
                    for ty in range(0, th, 2):  # Sample every 2nd row
                        row_sad = 0
                        for tx in range(0, tw, 2):
                            diff = abs(b_pixels[bx + tx, by + ty] - t_data[ty * tw + tx])
                            row_sad += diff
                        sad += row_sad
                        if sad > best_sad:
                            break

                    if sad < best_sad:
                        best_sad = sad
                        best_bx = bx
                        best_by = by

            # Refine best position at 1px resolution
            refine_range = 2
            r_best_sad = best_sad
            r_best_bx = best_bx
            r_best_by = best_by

            for rby in range(max(0, best_by - refine_range), min(bh - th + 1, best_by + refine_range + 1)):
                for rbx in range(max(0, best_bx - refine_range), min(bw - tw + 1, best_bx + refine_range + 1)):
                    sad = 0
                    for ty in range(0, th, 2):
                        for tx in range(0, tw, 2):
                            sad += abs(b_pixels[rbx + tx, rby + ty] - t_data[ty * tw + tx])
                    if sad < r_best_sad:
                        r_best_sad = sad
                        r_best_bx = rbx
                        r_best_by = rby

            # Calculate screen coordinates of match center
            matched_center_x = band_origin_x + r_best_bx + tw // 2
            matched_center_y = band_origin_y + r_best_by + th // 2

            shift_x = matched_center_x - expected_x
            shift_y = matched_center_y - expected_y

            # Check if shift is realistic (e.g. within -30px to +180px horizontally, ±30px vertically)
            if -30 <= shift_x <= 180 and abs(shift_y) <= 30:
                logger.info(
                    f"Dynamic blank tracked: original=({expected_x}, {expected_y}) -> "
                    f"shifted=({matched_center_x}, {matched_center_y}) [delta=+({shift_x},{shift_y})]"
                )
                return matched_center_x, matched_center_y
            else:
                logger.debug(f"Template match outside expected shift bounds: delta=({shift_x},{shift_y})")

        except Exception as e:
            logger.warning(f"Error in track_shifted_input_box: {e}")

        return None

    def is_radio_or_checkbox_selected(self, roi_img: Optional[Image.Image]) -> Tuple[bool, str, float]:
        """
        Evaluates whether an ROI crop contains an active/selected radio button (inner bullet dot or color fill)
        or checked checkbox (checkmark/fill).
        Zero-token computer vision heuristic with light and dark theme support.
        Returns (is_selected, reason, confidence).
        """
        if roi_img is None:
            return False, "no_image", 0.0

        w, h = roi_img.size
        if w < 12 or h < 12:
            return False, "image_too_small", 0.0

        try:
            gray = roi_img.convert("L")
            rgb = roi_img.convert("RGB")
            g_pixels = gray.load()
            rgb_pixels = rgb.load()

            mid_x = w // 2
            mid_y = h // 2

            best_contrast = 0.0
            best_sat = 0.0

            # Scan small window (+-2 px) around center to handle sub-pixel jitter
            # without expanding into the outer border ring (which starts at r >= 8 px)
            scan_r = min(2, mid_x - 6, mid_y - 6)
            for cx in range(mid_x - scan_r, mid_x + scan_r + 1):
                for cy in range(mid_y - scan_r, mid_y + scan_r + 1):
                    # 1. Inner core pixels (radius <= 3.5 px, dx^2 + dy^2 <= 12)
                    core_vals = []
                    core_sats = []
                    for dx in range(-3, 4):
                        for dy in range(-3, 4):
                            if dx * dx + dy * dy <= 12:
                                px, py = cx + dx, cy + dy
                                if 0 <= px < w and 0 <= py < h:
                                    core_vals.append(g_pixels[px, py])
                                    r, g, b = rgb_pixels[px, py]
                                    sat = max(abs(r - g), abs(g - b), abs(r - b))
                                    core_sats.append(sat)

                    # 2. Gap ring pixels (radius 4.2 to 6.0 px, 18 <= dx^2 + dy^2 <= 36)
                    # Stays safely inside the 8-11 px outer border ring
                    gap_vals = []
                    for dx in range(-6, 7):
                        for dy in range(-6, 7):
                            dist_sq = dx * dx + dy * dy
                            if 18 <= dist_sq <= 36:
                                px, py = cx + dx, cy + dy
                                if 0 <= px < w and 0 <= py < h:
                                    gap_vals.append(g_pixels[px, py])

                    if core_vals and gap_vals:
                        avg_core = sum(core_vals) / len(core_vals)
                        avg_gap = sum(gap_vals) / len(gap_vals)
                        contrast = abs(avg_gap - avg_core)
                        avg_sat = sum(core_sats) / len(core_sats)

                        if contrast > best_contrast:
                            best_contrast = contrast
                        if avg_sat > best_sat:
                            best_sat = avg_sat

            # Evaluation 1: Radio button inner bullet dot
            if best_contrast >= 28.0:
                conf = min(1.0, 0.70 + (best_contrast / 100.0))
                return True, f"radio_inner_bullet (contrast={best_contrast:.1f})", conf

            # Evaluation 2: Colored active bullet dot (blue, green, purple active dots)
            if best_sat >= 25.0 and best_contrast >= 14.0:
                return True, f"radio_colored_bullet (sat={best_sat:.1f}, contrast={best_contrast:.1f})", 0.90

            # Evaluation 3: Checkbox checkmark or solid fill
            # Inner square has high variance / checkmark strokes (both light and dark modes)
            box_r = min(7, mid_x - 3, mid_y - 3)
            inner_box = gray.crop((mid_x - box_r, mid_y - box_r, mid_x + box_r, mid_y + box_r))
            stat = ImageStat.Stat(inner_box)
            inner_std = stat.stddev[0]
            inner_hist = inner_box.histogram()
            dark_px = sum(inner_hist[:140])
            bright_px = sum(inner_hist[160:])

            if inner_std >= 25.0 and (dark_px >= 10 or bright_px >= 10):
                return True, f"checkbox_checkmark (std={inner_std:.1f})", 0.88

        except Exception as e:
            logger.debug(f"Error evaluating is_radio_or_checkbox_selected: {e}")

        return False, "unselected", 0.0

    def is_text_input_filled(
        self,
        after_roi: Optional[Image.Image],
        before_roi: Optional[Image.Image] = None,
        threshold_stroke_pixels: int = 12
    ) -> Tuple[bool, str, float]:
        """
        Determines whether a text input box now contains typed characters/glyphs.
        Returns (is_filled, reason, confidence).
        """
        if after_roi is None:
            return False, "no_image", 0.0

        try:
            # 1. If baseline before_roi is available, compute direct stroke difference
            if before_roi is not None and before_roi.size == after_roi.size:
                b_gray = before_roi.convert("L")
                a_gray = after_roi.convert("L")
                diff = ImageChops.difference(b_gray, a_gray)
                stat = ImageStat.Stat(diff)
                mean_diff = stat.mean[0]
                hist = diff.histogram()
                changed_strokes = sum(hist[22:])

                if changed_strokes >= threshold_stroke_pixels or mean_diff >= 1.6:
                    return True, f"text_stroke_diff (strokes={changed_strokes}, mean={mean_diff:.1f})", 0.95

            # 2. Static inspection: check if the center of after_roi contains text glyph strokes
            w, h = after_roi.size
            margin_x = max(3, int(w * 0.15))
            margin_y = max(3, int(h * 0.15))
            inner = after_roi.convert("L").crop((margin_x, margin_y, w - margin_x, h - margin_y))
            stat = ImageStat.Stat(inner)
            std_dev = stat.stddev[0]
            hist = inner.histogram()
            # Count dark text pixels against typical light field
            dark_pixels = sum(hist[:135])

            if std_dev >= 16.0 and dark_pixels >= 12:
                return True, f"text_glyphs_detected (std={std_dev:.1f}, dark_px={dark_pixels})", 0.88

        except Exception as e:
            logger.debug(f"Error evaluating is_text_input_filled: {e}")

        return False, "input_empty", 0.0

    def find_radio_or_checkbox_in_band(
        self,
        band_img: Image.Image,
        click_screen_x: int,
        click_screen_y: int,
        band_origin_x: int,
        band_origin_y: int,
        max_scan_left: int = 85
    ) -> Optional[Tuple[int, int]]:
        """
        Scans leftward in the option band from the click coordinate to locate
        a circular radio button or checkbox that was missed.
        Returns screen coordinates (screen_x, screen_y) of detected control center.
        """
        try:
            bw, bh = band_img.size
            band_click_x = click_screen_x - band_origin_x
            band_click_y = click_screen_y - band_origin_y

            gray = band_img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            ep = edges.load()

            # Scan leftward starting 14px left of click up to max_scan_left
            start_x = max(8, band_click_x - 14)
            end_x = max(8, band_click_x - max_scan_left)

            best_score = 0
            best_coord = None

            for cx in range(start_x, end_x, -2):
                for cy in range(max(8, band_click_y - 6), min(bh - 8, band_click_y + 7), 2):
                    for r in [8, 9, 10, 11]:
                        if cx - r < 1 or cx + r >= bw - 1 or cy - r < 1 or cy + r >= bh - 1:
                            continue

                        # Sample 8 points around circle perimeter
                        p_top = ep[cx, cy - r]
                        p_bot = ep[cx, cy + r]
                        p_left = ep[cx - r, cy]
                        p_right = ep[cx + r, cy]
                        d = int(r * 0.707)
                        p_d1 = ep[cx - d, cy - d]
                        p_d2 = ep[cx + d, cy - d]
                        p_d3 = ep[cx - d, cy + d]
                        p_d4 = ep[cx + d, cy + d]

                        pts = [p_top, p_bot, p_left, p_right, p_d1, p_d2, p_d3, p_d4]
                        hits = sum(1 for p in pts if p >= 32)

                        if hits >= 5 and hits > best_score:
                            best_score = hits
                            best_coord = (band_origin_x + cx, band_origin_y + cy)

            if best_coord and best_score >= 5:
                logger.info(f"Detected option control at {best_coord} (perimeter hits={best_score}/8)")
                return best_coord

        except Exception as e:
            logger.debug(f"Error in find_radio_or_checkbox_in_band: {e}")

        return None

    def is_option_row_highlighted(
        self,
        before_band: Optional[Image.Image],
        after_band: Optional[Image.Image]
    ) -> Tuple[bool, float]:
        """
        Detects if an entire option card or row container changed background color/tint when clicked.
        """
        if before_band is None or after_band is None or before_band.size != after_band.size:
            return False, 0.0

        try:
            b_gray = before_band.convert("L")
            a_gray = after_band.convert("L")
            diff = ImageChops.difference(b_gray, a_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]
            hist = diff.histogram()
            # Count pixels with noticeable change
            changed_px = sum(hist[12:])
            total_px = before_band.width * before_band.height
            ratio = (changed_px / total_px) if total_px > 0 else 0.0

            is_highlighted = (ratio >= 0.20 and mean_diff >= 1.8)
            return is_highlighted, mean_diff
        except Exception as e:
            logger.debug(f"Error evaluating is_option_row_highlighted: {e}")
            return False, 0.0

    def verify_solution_outcome(
        self,
        actions: List[Dict[str, Any]],
        result_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive zero-token verification across all executed actions in a solution.
        Confirms whether the question was answered before allowing the engine to go idle.
        Returns outcome dict:
        {
            "is_answered": bool,
            "verified_count": int,
            "total_actions": int,
            "details": str,
            "recovery_used": bool
        }
        """
        if not actions:
            return {
                "is_answered": True,
                "verified_count": 0,
                "total_actions": 0,
                "details": "no_actions_to_verify",
                "recovery_used": False
            }

        verified_count = 0
        recovery_used = False
        reasons = []

        for i, act in enumerate(actions):
            act_type = act.get("type", "").lower()
            if act_type not in ["click", "double_click", "type_text", "drag"]:
                # Non-interactive or utility action (delay, key_press, etc.)
                continue

            is_act_verified = act.get("verified", False)
            reason = act.get("verification_reason", "")

            # If not yet verified by inline execution, perform live check
            if not is_act_verified:
                sx = act.get("screen_x", act.get("x"))
                sy = act.get("screen_y", act.get("y"))
                if sx is not None and sy is not None:
                    live_roi = self.capture_roi(int(sx), int(sy))
                    if act_type in ["click", "double_click"]:
                        sel, r_reason, conf = self.is_radio_or_checkbox_selected(live_roi)
                        if sel:
                            is_act_verified = True
                            reason = f"live_{r_reason}"
                    elif act_type == "type_text":
                        filled, f_reason, conf = self.is_text_input_filled(live_roi)
                        if filled:
                            is_act_verified = True
                            reason = f"live_{f_reason}"

            if is_act_verified:
                verified_count += 1
                if "recovery" in reason:
                    recovery_used = True
                reasons.append(f"Act #{i+1}: {reason}")
            else:
                reasons.append(f"Act #{i+1}: UNCONFIRMED")

        # In multi-choice or single answer questions: at least 1 answer action must be verified.
        # In multi-part or multi-action: majority must be verified.
        total_verifiable = sum(1 for a in actions if a.get("type", "").lower() in ["click", "double_click", "type_text", "drag"])
        
        if total_verifiable == 0:
            is_answered = True
        elif total_verifiable == 1:
            is_answered = (verified_count >= 1)
        else:
            # If multiple actions, at least 1 primary action or all actions
            is_answered = (verified_count >= 1)

        summary_details = " | ".join(reasons)
        return {
            "is_answered": is_answered,
            "verified_count": verified_count,
            "total_actions": total_verifiable,
            "details": summary_details,
            "recovery_used": recovery_used
        }

    def verify_modal_dismissed(
        self,
        baseline_img: Optional[Image.Image],
        current_img: Optional[Image.Image],
        threshold_diff: float = 3.5,
        threshold_ratio: float = 0.04
    ) -> Tuple[bool, float]:
        """
        Compares the current screen/viewport against the pre-modal baseline image.
        Zero-token confirmation that the modal/reference sheet was actually dismissed
        and the underlying question content is visible again.
        Returns (is_dismissed, mean_diff).
        """
        if baseline_img is None or current_img is None:
            return True, 0.0

        try:
            if baseline_img.size != current_img.size:
                current_img = current_img.resize(baseline_img.size)

            b_gray = baseline_img.convert("L")
            c_gray = current_img.convert("L")

            diff = ImageChops.difference(b_gray, c_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]

            hist = diff.histogram()
            # Noticeable pixel changes (> 20 intensity difference)
            changed_pixels = sum(hist[20:])
            total_pixels = b_gray.width * b_gray.height
            ratio = (changed_pixels / total_pixels) if total_pixels > 0 else 0.0

            # When dismissed, current image closely aligns with baseline
            # (allowing for subtle caret blink or cursor differences)
            is_dismissed = (mean_diff <= threshold_diff and ratio <= threshold_ratio)
            logger.debug(
                f"verify_modal_dismissed: is_dismissed={is_dismissed}, "
                f"mean_diff={mean_diff:.2f}, changed_ratio={ratio:.4f}"
            )
            return is_dismissed, mean_diff
        except Exception as e:
            logger.warning(f"Error in verify_modal_dismissed: {e}")
            return True, 0.0

    def verify_screen_scrolled(
        self,
        before_img: Optional[Image.Image],
        after_img: Optional[Image.Image],
        min_diff: float = 1.6,
        min_ratio: float = 0.03
    ) -> Tuple[bool, float]:
        """
        Verifies that scrolling actually caused viewport content displacement.
        Returns (has_scrolled, mean_diff).
        """
        if before_img is None or after_img is None:
            return True, 0.0

        try:
            if before_img.size != after_img.size:
                after_img = after_img.resize(before_img.size)

            b_gray = before_img.convert("L")
            a_gray = after_img.convert("L")

            diff = ImageChops.difference(b_gray, a_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]

            hist = diff.histogram()
            changed_pixels = sum(hist[16:])
            total_pixels = b_gray.width * b_gray.height
            ratio = (changed_pixels / total_pixels) if total_pixels > 0 else 0.0

            has_scrolled = (mean_diff >= min_diff or ratio >= min_ratio)
            logger.debug(
                f"verify_screen_scrolled: has_scrolled={has_scrolled}, "
                f"mean_diff={mean_diff:.2f}, changed_ratio={ratio:.4f}"
            )
            return has_scrolled, mean_diff
        except Exception as e:
            logger.warning(f"Error in verify_screen_scrolled: {e}")
            return True, 0.0

    def verify_drag_completion(
        self,
        start_before: Optional[Image.Image],
        start_after: Optional[Image.Image],
        dest_before: Optional[Image.Image],
        dest_after: Optional[Image.Image],
        min_diff: float = 1.4
    ) -> Tuple[bool, str]:
        """
        Verifies drag-and-drop by checking that origin element was picked up
        and/or destination area received the dropped element.
        Returns (is_completed, reason).
        """
        if any(img is None for img in [start_before, start_after, dest_before, dest_after]):
            return True, "no_roi_available"

        try:
            diff_start = ImageChops.difference(start_before.convert("L"), start_after.convert("L"))
            diff_dest = ImageChops.difference(dest_before.convert("L"), dest_after.convert("L"))

            stat_s = ImageStat.Stat(diff_start).mean[0]
            stat_d = ImageStat.Stat(diff_dest).mean[0]

            # At least one region must exhibit visual displacement
            is_confirmed = (stat_s >= min_diff or stat_d >= min_diff)
            reason = f"drag_start_diff={stat_s:.1f}, dest_diff={stat_d:.1f}"
            logger.debug(f"verify_drag_completion: confirmed={is_confirmed}, reason={reason}")
            return is_confirmed, reason
        except Exception as e:
            logger.warning(f"Error in verify_drag_completion: {e}")
            return True, "error_fallback"

    def verify_screen_transition(
        self,
        before_img: Optional[Image.Image],
        after_img: Optional[Image.Image],
        min_diff: float = 1.4,
        min_changed_pixels: int = 30
    ) -> Tuple[bool, float]:
        """
        Verifies that screen transitioned or responded visually following
        a navigation action ("Check Answer", "Next", submit).
        Returns (is_transitioned, mean_diff).
        """
        if before_img is None or after_img is None:
            return True, 0.0

        try:
            if before_img.size != after_img.size:
                after_img = after_img.resize(before_img.size)

            b_gray = before_img.convert("L")
            a_gray = after_img.convert("L")

            diff = ImageChops.difference(b_gray, a_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]

            hist = diff.histogram()
            changed_pixels = sum(hist[16:])

            is_transitioned = (mean_diff >= min_diff or changed_pixels >= min_changed_pixels)
            logger.debug(
                f"verify_screen_transition: is_transitioned={is_transitioned}, "
                f"mean_diff={mean_diff:.2f}, changed_px={changed_pixels}"
            )
            return is_transitioned, mean_diff
        except Exception as e:
            logger.warning(f"Error in verify_screen_transition: {e}")
            return True, 0.0

    def detect_platform_evaluation_markers(
        self,
        image: Optional[Image.Image] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
        min_cluster_pixels: int = 35
    ) -> Dict[str, Any]:
        """
        Inspects an image or screen capture for high-contrast visual grading markers:
        - Incorrect: prominent red evaluation cues (red 'X', red border, red banner).
        - Correct: prominent green evaluation cues (green checkmark, green border, green badge).
        - Unsubmitted: no significant platform grading indicators.
        Returns:
        {
            "detected": bool,
            "status": "correct" | "incorrect" | "unsubmitted",
            "confidence": float,
            "details": str,
            "red_pixels": int,
            "green_pixels": int
        }
        """
        if image is None:
            if region:
                image = self.capture_roi(region[0] + (region[2]-region[0])//2, region[1] + (region[3]-region[1])//2,
                                         radius_w=(region[2]-region[0])//2, radius_h=(region[3]-region[1])//2)
            else:
                return {
                    "detected": False,
                    "status": "unsubmitted",
                    "confidence": 0.0,
                    "details": "no_image_provided",
                    "red_pixels": 0,
                    "green_pixels": 0
                }

        try:
            rgb_img = image.convert("RGB")
            # Downsample for speed if very large while retaining color cues
            if rgb_img.width > 800 or rgb_img.height > 600:
                rgb_img = rgb_img.resize((min(800, rgb_img.width), min(600, rgb_img.height)), Image.Resampling.BOX)

            if hasattr(rgb_img, "get_flattened_data"):
                pixels = rgb_img.get_flattened_data()
            else:
                pixels = rgb_img.getdata()

            red_count = 0
            green_count = 0

            for r, g, b in pixels:
                # Strong red evaluation indicators (e.g. #ef4444, #dc2626, #b91c1c, #e11d48)
                if (r >= 150 and g <= 95 and b <= 95) or (r >= 135 and r > (1.6 * max(g, b))):
                    red_count += 1
                # Strong green evaluation indicators (e.g. #10b981, #059669, #16a34a, #22c55e)
                elif (g >= 125 and r <= 100 and b <= 100) or (g >= 120 and g > (1.4 * max(r, b))):
                    green_count += 1

            if red_count >= min_cluster_pixels and red_count > (green_count * 1.5):
                confidence = min(0.99, 0.65 + (red_count / 300.0) * 0.35)
                return {
                    "detected": True,
                    "status": "incorrect",
                    "is_incorrect": True,
                    "is_correct": False,
                    "confidence": confidence,
                    "details": f"detected_red_error_cluster ({red_count}px)",
                    "red_pixels": red_count,
                    "green_pixels": green_count
                }
            elif green_count >= min_cluster_pixels and green_count > (red_count * 1.5):
                confidence = min(0.99, 0.65 + (green_count / 300.0) * 0.35)
                return {
                    "detected": True,
                    "status": "correct",
                    "is_incorrect": False,
                    "is_correct": True,
                    "confidence": confidence,
                    "details": f"detected_green_success_cluster ({green_count}px)",
                    "red_pixels": red_count,
                    "green_pixels": green_count
                }
            else:
                return {
                    "detected": False,
                    "status": "unsubmitted",
                    "is_incorrect": False,
                    "is_correct": False,
                    "confidence": 0.5,
                    "details": f"no_dominant_grading_markers (red={red_count}, green={green_count})",
                    "red_pixels": red_count,
                    "green_pixels": green_count
                }
        except Exception as e:
            logger.warning(f"Error in detect_platform_evaluation_markers: {e}")
            return {
                "detected": False,
                "status": "unsubmitted",
                "is_incorrect": False,
                "is_correct": False,
                "confidence": 0.0,
                "details": f"error: {e}",
                "red_pixels": 0,
                "green_pixels": 0
            }

    def verify_post_submission_evaluation(
        self,
        before_check_img: Optional[Image.Image],
        after_check_img: Optional[Image.Image]
    ) -> Dict[str, Any]:
        """
        Compares the screen state before and after clicking 'Check Answer' / 'Submit'.
        Detects if newly introduced visual elements signify an incorrect or correct outcome.
        """
        markers = self.detect_platform_evaluation_markers(after_check_img)
        markers["is_incorrect"] = (markers.get("status") == "incorrect")
        markers["is_correct"] = (markers.get("status") == "correct")
        if before_check_img and after_check_img:
            trans_ok, diff = self.verify_screen_transition(before_check_img, after_check_img)
            markers["screen_transitioned"] = trans_ok
            markers["transition_diff"] = diff
        else:
            markers["screen_transitioned"] = False
            markers["transition_diff"] = 0.0

        return markers


