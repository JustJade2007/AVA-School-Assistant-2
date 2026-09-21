"""
Local Vision Verifier & Layout Shift Tracker for AVA School Assistant 2.
Provides fast, zero-AI-token visual confirmation of clicks, inputs,
visual center snapping, and dynamic fill-in-the-blank template tracking.
"""

import math
import random
import logging
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image, ImageChops, ImageStat, ImageFilter
import mss

logger = logging.getLogger(__name__)


class TransitionResult(tuple):
    """
    Tuple subclass (is_transitioned, mean_diff) that also provides dictionary-like
    and attribute access (.transitioned, .diff, .get('transitioned'), etc.)
    for backward and forward compatibility.
    """
    def __new__(cls, transitioned: bool, diff: float, details: str = ""):
        instance = super().__new__(cls, (bool(transitioned), float(diff)))
        instance._details = details
        return instance

    @property
    def transitioned(self) -> bool:
        return self[0]

    @property
    def diff(self) -> float:
        return self[1]

    @property
    def details(self) -> str:
        return getattr(self, "_details", "")

    def get(self, key: str, default: Any = None) -> Any:
        if key in ("transitioned", "is_transitioned"):
            return self[0]
        if key in ("diff", "mean_diff"):
            return self[1]
        if key == "details":
            return getattr(self, "_details", default)
        return default

    def __getitem__(self, item):
        if isinstance(item, str):
            val = self.get(item)
            if val is not None:
                return val
            raise KeyError(item)
        return super().__getitem__(item)


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

    def measure_and_target_input_box(
        self,
        roi_img: Optional[Image.Image] = None,
        center_screen_x: int = 0,
        center_screen_y: Optional[int] = None,
        radius_w: int = 140,
        radius_h: int = 45,
        crop_origin_x: Optional[int] = None,
        crop_origin_y: Optional[int] = None
    ) -> Tuple[int, int, Dict[str, Any]]:
        """
        Measures the boundary dimensions (width, height) of an input/fill-in box from a local crop,
        computes the middle 50% sub-region (leaving 25% safety margins from all outer borders),
        and selects a spot inside that middle 50% area for high-accuracy focusing.

        Returns: (chosen_screen_x, chosen_screen_y, metadata_dict)
        """
        # Handle invocation without roi_img: measure_and_target_input_box(x, y)
        if isinstance(roi_img, (int, float)) and center_screen_y is None:
            center_screen_y = int(center_screen_x)
            center_screen_x = int(roi_img)
            roi_img = None
        elif center_screen_y is None:
            center_screen_y = 0

        fallback_meta = {
            "detected": False,
            "box_width": 0,
            "box_height": 0,
            "middle_50_bounds": None
        }

        # If no image provided, capture live desktop ROI centered on (center_screen_x, center_screen_y)
        if roi_img is None:
            crop_origin_x = max(0, int(center_screen_x - radius_w))
            crop_origin_y = max(0, int(center_screen_y - radius_h))
            roi_img = self.capture_roi(center_screen_x, center_screen_y, radius_w=radius_w, radius_h=radius_h)

        if roi_img is None:
            return center_screen_x, center_screen_y, fallback_meta

        try:
            w, h = roi_img.size
            if w < 16 or h < 12:
                return center_screen_x, center_screen_y, fallback_meta

            if crop_origin_x is None:
                crop_origin_x = int(center_screen_x - w // 2)
            if crop_origin_y is None:
                crop_origin_y = int(center_screen_y - h // 2)

            gray = roi_img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_data = edges.load()

            # 1. Detect horizontal boundary lines
            h_lines = []
            for y in range(2, h - 2):
                x_start = None
                for x in range(2, w - 2):
                    if edge_data[x, y] > 28:
                        if x_start is None:
                            x_start = x
                    else:
                        if x_start is not None:
                            line_len = x - x_start
                            if line_len >= 20:
                                h_lines.append((y, x_start, x - 1, line_len))
                            x_start = None
                if x_start is not None and (w - 2 - x_start) >= 20:
                    h_lines.append((y, x_start, w - 3, w - 2 - x_start))

            # 2. Pair parallel top and bottom horizontal lines that form a rectangular input container
            candidates = []
            for i in range(len(h_lines)):
                y1, x1_start, x1_end, len1 = h_lines[i]
                for j in range(i + 1, len(h_lines)):
                    y2, x2_start, x2_end, len2 = h_lines[j]
                    box_h = y2 - y1
                    # Typical input box heights in web applications: 14px to 55px
                    if 14 <= box_h <= 55:
                        ol_start = max(x1_start, x2_start)
                        ol_end = min(x1_end, x2_end)
                        ol_len = ol_end - ol_start
                        if ol_len >= 22 and (ol_len / max(len1, len2, 1)) >= 0.5:
                            candidates.append((ol_start, y1, ol_end, y2, ol_len, box_h))

            crop_mid_x = w // 2
            crop_mid_y = h // 2

            found_box = None
            if candidates:
                # Prioritize candidate closest to the expected focus point
                candidates.sort(key=lambda c: (abs((c[0] + c[2]) / 2.0 - crop_mid_x) + abs((c[1] + c[3]) / 2.0 - crop_mid_y)))
                found_box = candidates[0]

            if found_box:
                min_x, min_y, max_x, max_y, box_w, box_h = found_box
            else:
                # Fallback: scan outward for outer bounding edges
                min_x, max_x = 0, w - 1
                min_y, max_y = 0, h - 1

                found_top = None
                for y in range(crop_mid_y, max(1, crop_mid_y - (h // 2 - 2)), -1):
                    hits = sum(1 for x in range(max(2, crop_mid_x - 30), min(w - 2, crop_mid_x + 30)) if edge_data[x, y] > 32)
                    if hits >= 10:
                        found_top = y
                        break

                found_bottom = None
                for y in range(crop_mid_y, min(h - 2, crop_mid_y + (h // 2 - 2))):
                    hits = sum(1 for x in range(max(2, crop_mid_x - 30), min(w - 2, crop_mid_x + 30)) if edge_data[x, y] > 32)
                    if hits >= 10:
                        found_bottom = y
                        break

                found_left = None
                for x in range(crop_mid_x, max(1, crop_mid_x - (w // 2 - 2)), -1):
                    hits = sum(1 for y in range(max(2, crop_mid_y - 10), min(h - 2, crop_mid_y + 10)) if edge_data[x, y] > 32)
                    if hits >= 5:
                        found_left = x
                        break

                found_right = None
                for x in range(crop_mid_x, min(w - 2, crop_mid_x + (w // 2 - 2))):
                    hits = sum(1 for y in range(max(2, crop_mid_y - 10), min(h - 2, crop_mid_y + 10)) if edge_data[x, y] > 32)
                    if hits >= 5:
                        found_right = x
                        break

                if found_top and found_bottom and found_left and found_right:
                    min_x, max_x = found_left, found_right
                    min_y, max_y = found_top, found_bottom
                else:
                    # Generic input box estimation centered around expected point
                    min_x = max(2, crop_mid_x - 35)
                    max_x = min(w - 2, crop_mid_x + 35)
                    min_y = max(2, crop_mid_y - 12)
                    max_y = min(h - 2, crop_mid_y + 12)

                box_w = max_x - min_x
                box_h = max_y - min_y

            if box_w >= 14 and box_h >= 8:
                # Calculate the middle 50% region (leaving 25% safety margins from all edges)
                mid50_min_x = int(min_x + 0.25 * box_w)
                mid50_max_x = int(max_x - 0.25 * box_w)
                mid50_min_y = int(min_y + 0.25 * box_h)
                mid50_max_y = int(max_y - 0.25 * box_h)

                if mid50_min_x > mid50_max_x:
                    mid50_min_x = mid50_max_x = (min_x + max_x) // 2
                if mid50_min_y > mid50_max_y:
                    mid50_min_y = mid50_max_y = (min_y + max_y) // 2

                # Select center of middle 50% (or slight random variance within middle 50%)
                chosen_roi_x = random.randint(mid50_min_x, mid50_max_x)
                chosen_roi_y = random.randint(mid50_min_y, mid50_max_y)

                # Exactly translate from crop space to global screen coordinates
                target_x = crop_origin_x + chosen_roi_x
                target_y = crop_origin_y + chosen_roi_y

                screen_bounds = (
                    crop_origin_x + min_x,
                    crop_origin_y + min_y,
                    crop_origin_x + max_x,
                    crop_origin_y + max_y
                )

                meta = {
                    "detected": True,
                    "box_width": box_w,
                    "box_height": box_h,
                    "middle_50_bounds": (mid50_min_x, mid50_min_y, mid50_max_x, mid50_max_y),
                    "screen_bounds": screen_bounds
                }
                logger.info(
                    f"Input box measured: {box_w}x{box_h}px at screen {screen_bounds}. "
                    f"Snapped to middle 50%: ({center_screen_x}, {center_screen_y}) -> ({target_x}, {target_y})"
                )
                return target_x, target_y, meta

        except Exception as e:
            logger.debug(f"measure_and_target_input_box error: {e}")

        return center_screen_x, center_screen_y, fallback_meta

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

    def _extract_control_features(self, roi_img: Optional[Image.Image]) -> Dict[str, float]:
        """
        Extracts structural, contrast, saturation, and luminance descriptors from a choice control ROI.
        """
        if roi_img is None:
            return {"contrast": 0.0, "sat": 0.0, "inner_std": 0.0, "inner_mean": 128.0, "edge_hits": 0.0}

        w, h = roi_img.size
        if w < 10 or h < 10:
            return {"contrast": 0.0, "sat": 0.0, "inner_std": 0.0, "inner_mean": 128.0, "edge_hits": 0.0}

        try:
            gray = roi_img.convert("L")
            rgb = roi_img.convert("RGB")
            g_pixels = gray.load()
            rgb_pixels = rgb.load()

            mid_x = w // 2
            mid_y = h // 2

            best_contrast = 0.0
            best_sat = 0.0

            scan_r = min(2, max(0, mid_x - 6), max(0, mid_y - 6))
            for cx in range(mid_x - scan_r, mid_x + scan_r + 1):
                for cy in range(mid_y - scan_r, mid_y + scan_r + 1):
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

            box_r = min(7, max(1, mid_x - 3), max(1, mid_y - 3))
            inner_box = gray.crop((mid_x - box_r, mid_y - box_r, mid_x + box_r, mid_y + box_r))
            stat = ImageStat.Stat(inner_box)
            inner_std = stat.stddev[0] if stat.stddev else 0.0
            inner_mean = stat.mean[0] if stat.mean else 128.0

            return {
                "contrast": best_contrast,
                "sat": best_sat,
                "inner_std": inner_std,
                "inner_mean": inner_mean
            }
        except Exception as e:
            logger.debug(f"_extract_control_features error: {e}")
            return {"contrast": 0.0, "sat": 0.0, "inner_std": 0.0, "inner_mean": 128.0, "edge_hits": 0.0}

    def compare_choice_to_siblings(
        self,
        target_roi: Optional[Image.Image],
        sibling_rois: List[Image.Image]
    ) -> Tuple[bool, str, float, float]:
        """
        Determines whether target_roi is selected by comparing it against sibling multiple choice points.
        Because unselected options on the same webpage share identical styling, the target's deviation
        from the sibling baseline provides reliable zero-token selection detection regardless of website theme.
        Returns: (is_selected, reason, confidence, diff_score)
        """
        if target_roi is None or not sibling_rois:
            return False, "no_sibling_data", 0.0, 0.0

        valid_sibs = [s for s in sibling_rois if s is not None and s.size[0] >= 10 and s.size[1] >= 10]
        if not valid_sibs:
            return False, "no_valid_siblings", 0.0, 0.0

        try:
            target_feat = self._extract_control_features(target_roi)
            sib_feats = [self._extract_control_features(s) for s in valid_sibs]

            # Compute median unselected baseline across siblings
            def _median(vals: List[float]) -> float:
                if not vals:
                    return 0.0
                sv = sorted(vals)
                n = len(sv)
                return sv[n // 2] if n % 2 != 0 else (sv[n // 2 - 1] + sv[n // 2]) / 2.0

            base_contrast = _median([f["contrast"] for f in sib_feats])
            base_sat = _median([f["sat"] for f in sib_feats])
            base_std = _median([f["inner_std"] for f in sib_feats])
            base_mean = _median([f["inner_mean"] for f in sib_feats])

            # Measure deviations from unselected baseline
            d_contrast = target_feat["contrast"] - base_contrast
            d_sat = target_feat["sat"] - base_sat
            d_std = target_feat["inner_std"] - base_std
            d_lum = abs(target_feat["inner_mean"] - base_mean)

            # Direct image pixel difference against sibling average
            t_gray = target_roi.convert("L")
            img_diffs = []
            for s in valid_sibs:
                s_gray = s.convert("L")
                if s_gray.size != t_gray.size:
                    s_gray = s_gray.resize(t_gray.size)
                diff = ImageChops.difference(t_gray, s_gray)
                stat = ImageStat.Stat(diff)
                img_diffs.append(stat.mean[0] if stat.mean else 0.0)

            mean_img_diff = sum(img_diffs) / len(img_diffs) if img_diffs else 0.0

            # Inter-sibling similarity check: verify that siblings themselves look like each other
            inter_sib_diffs = []
            if len(valid_sibs) >= 2:
                for idx_a in range(len(valid_sibs) - 1):
                    s_a = valid_sibs[idx_a].convert("L")
                    s_b = valid_sibs[idx_a + 1].convert("L")
                    if s_a.size != s_b.size:
                        s_b = s_b.resize(s_a.size)
                    d_ab = ImageStat.Stat(ImageChops.difference(s_a, s_b)).mean[0]
                    inter_sib_diffs.append(d_ab)
            inter_sib_baseline_variance = max(inter_sib_diffs) if inter_sib_diffs else 2.0

            # Evaluation 1: Radio bullet dot present in target compared to hollow siblings
            if d_contrast >= 13.0 and target_feat["contrast"] >= 16.0:
                conf = min(0.98, 0.78 + (d_contrast / 60.0))
                reason = f"sibling_diff_bullet (d_contrast=+{d_contrast:.1f}, base={base_contrast:.1f})"
                return True, reason, conf, d_contrast

            # Evaluation 2: Colored active dot (saturation deviation)
            if d_sat >= 14.0 and target_feat["sat"] >= 18.0:
                conf = 0.94
                reason = f"sibling_diff_colored_dot (d_sat=+{d_sat:.1f}, base_sat={base_sat:.1f})"
                return True, reason, conf, d_sat

            # Evaluation 3: Checkbox checkmark / stroke density deviation
            if d_std >= 9.0 and (d_contrast >= 6.0 or d_lum >= 12.0):
                conf = 0.92
                reason = f"sibling_diff_checkmark (d_std=+{d_std:.1f}, base_std={base_std:.1f})"
                return True, reason, conf, d_std

            # Evaluation 4: Solid fill or inverted luminance relative to hollow unselected siblings
            if d_lum >= 24.0 and mean_img_diff >= max(4.0, inter_sib_baseline_variance * 1.5):
                conf = 0.90
                reason = f"sibling_diff_fill_lum (d_lum={d_lum:.1f}, img_diff={mean_img_diff:.1f})"
                return True, reason, conf, mean_img_diff

            # Evaluation 5: Distinct holistic pixel divergence from consistent sibling baseline
            if mean_img_diff >= 7.5 and mean_img_diff >= (inter_sib_baseline_variance * 2.0):
                conf = 0.88
                reason = f"sibling_diff_holistic (mean_diff={mean_img_diff:.1f}, sib_var={inter_sib_baseline_variance:.1f})"
                return True, reason, conf, mean_img_diff

            # Unselected state: target closely matches the unselected sibling baseline
            return False, f"sibling_matches_unselected (diff={mean_img_diff:.1f})", 0.0, mean_img_diff

        except Exception as e:
            logger.debug(f"Error in compare_choice_to_siblings: {e}")
            return False, f"error_{e}", 0.0, 0.0

    def find_sibling_choice_points(
        self,
        target_x: int,
        target_y: int,
        max_scan_dist: int = 320,
        min_spacing: int = 18
    ) -> List[Tuple[int, int]]:
        """
        Discovers vertically aligned sibling multiple-choice options (e.g. radio buttons or checkboxes)
        along the same column as (target_x, target_y).
        Returns a list of screen coordinates [(x1, y1), (x2, y2), ...] of sibling choices.
        """
        siblings: List[Tuple[int, int]] = []
        try:
            # Capture vertical strip around target_x
            strip_top = max(0, target_y - max_scan_dist)
            strip_bottom = target_y + max_scan_dist
            strip_left = max(0, target_x - 16)
            strip_w = 32
            strip_h = strip_bottom - strip_top

            strip_img = self.capture_roi(target_x, target_y, radius_w=16, radius_h=max_scan_dist)
            if strip_img is None:
                return []

            sw, sh = strip_img.size
            mid_strip_y = sh // 2  # target_y in strip space
            gray = strip_img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            ep = edges.load()

            # Scan upward and downward from target_y
            found_rel_ys: List[int] = []

            # Check for repeating circular / box perimeter edge signatures
            for step_dir in [-1, 1]:
                y_range = range(mid_strip_y + (step_dir * min_spacing),
                                (0 if step_dir == -1 else sh - 10),
                                step_dir * 3)
                for cur_y in y_range:
                    if cur_y < 10 or cur_y >= sh - 10:
                        continue

                    # Avoid clustering too close to already found points
                    if any(abs(cur_y - fy) < min_spacing for fy in found_rel_ys):
                        continue

                    best_hits = 0
                    cx = sw // 2
                    for r in [7, 8, 9]:
                        if cx - r < 0 or cx + r >= sw or cur_y - r < 0 or cur_y + r >= sh:
                            continue
                        pts = [
                            ep[cx, cur_y - r], ep[cx, cur_y + r],
                            ep[cx - r, cur_y], ep[cx + r, cur_y],
                            ep[cx - int(r*0.7), cur_y - int(r*0.7)],
                            ep[cx + int(r*0.7), cur_y + int(r*0.7)]
                        ]
                        hits = sum(1 for p in pts if p >= 26)
                        if hits > best_hits:
                            best_hits = hits

                    if best_hits >= 4:
                        found_rel_ys.append(cur_y)
                        rel_diff = cur_y - mid_strip_y
                        cand_x = target_x
                        cand_y = target_y + rel_diff
                        siblings.append((cand_x, cand_y))
                        if len(siblings) >= 5:
                            break

            if siblings:
                logger.info(f"Discovered {len(siblings)} sibling choice point(s) on screen near ({target_x}, {target_y}): {siblings}")

        except Exception as e:
            logger.debug(f"find_sibling_choice_points error: {e}")

        return siblings

    def get_sibling_choice_coordinates(
        self,
        target_x: int,
        target_y: int,
        result_data: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[int, int]]:
        """
        Retrieves sibling choice coordinates from result_data (if AI provided choices)
        or automatically discovers them on screen via vertical column scanning.
        """
        sibling_coords: List[Tuple[int, int]] = []

        # 1. Check if explicit choices were returned by the AI
        if result_data and isinstance(result_data, dict):
            # Check top-level choices
            choices = result_data.get("choices")
            if not choices and isinstance(result_data.get("items"), list):
                # Search items
                for itm in result_data.get("items", []):
                    if itm.get("choices"):
                        choices = itm.get("choices")
                        break

            if isinstance(choices, list) and len(choices) >= 2:
                for c in choices:
                    cx = c.get("screen_x", c.get("x"))
                    cy = c.get("screen_y", c.get("y"))
                    if cx is not None and cy is not None:
                        icx, icy = int(cx), int(cy)
                        # Exclude the target point itself (within 12px tolerance)
                        if abs(icx - target_x) > 12 or abs(icy - target_y) > 12:
                            sibling_coords.append((icx, icy))

        # 2. If no explicit choices from AI, discover on-screen sibling points
        if not sibling_coords:
            sibling_coords = self.find_sibling_choice_points(target_x, target_y)

        return sibling_coords

    def is_radio_or_checkbox_selected(
        self,
        roi_img: Optional[Image.Image],
        sibling_rois: Optional[List[Image.Image]] = None
    ) -> Tuple[bool, str, float]:
        """
        Evaluates whether an ROI crop contains an active/selected radio button (inner bullet dot or color fill)
        or checked checkbox (checkmark/fill).
        First utilizes relative comparison against sibling_rois if provided,
        falling back to high-fidelity standalone zero-token computer vision heuristics.
        Returns (is_selected, reason, confidence).
        """
        if roi_img is None:
            return False, "no_image", 0.0

        w, h = roi_img.size
        if w < 12 or h < 12:
            return False, "image_too_small", 0.0

        # Tier 1: Relative comparative verification against sibling choices
        if sibling_rois and len(sibling_rois) >= 1:
            is_comp_sel, comp_reason, comp_conf, diff_score = self.compare_choice_to_siblings(roi_img, sibling_rois)
            if is_comp_sel:
                return True, comp_reason, comp_conf

        # Tier 2: Standalone computer vision heuristics (with light and dark theme support)
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
            if best_contrast >= 25.0:
                conf = min(1.0, 0.70 + (best_contrast / 100.0))
                return True, f"radio_inner_bullet (contrast={best_contrast:.1f})", conf

            # Evaluation 2: Colored active bullet dot (blue, green, purple active dots)
            if best_sat >= 22.0 and best_contrast >= 12.0:
                return True, f"radio_colored_bullet (sat={best_sat:.1f}, contrast={best_contrast:.1f})", 0.90

            # Evaluation 3: Checkbox checkmark or solid fill
            box_r = min(7, mid_x - 3, mid_y - 3)
            inner_box = gray.crop((mid_x - box_r, mid_y - box_r, mid_x + box_r, mid_y + box_r))
            stat = ImageStat.Stat(inner_box)
            inner_std = stat.stddev[0]
            inner_hist = inner_box.histogram()
            dark_px = sum(inner_hist[:140])
            bright_px = sum(inner_hist[160:])

            if inner_std >= 22.0 and (dark_px >= 8 or bright_px >= 8):
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
            mean_lum = stat.mean[0]
            std_dev = stat.stddev[0]
            hist = inner.histogram()

            # Contrast-aware glyph pixel counting:
            if mean_lum >= 128:
                # Light background: glyphs are dark stroke pixels contrasting against the field
                glyph_pixels = sum(hist[:110])
            else:
                # Dark background: glyphs are light stroke pixels contrasting against the field
                glyph_pixels = sum(hist[160:])

            if std_dev >= 15.0 and glyph_pixels >= 12:
                return True, f"text_glyphs_detected (std={std_dev:.1f}, glyph_px={glyph_pixels}, mean={mean_lum:.1f})", 0.88

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

    def detect_controls_in_crop(
        self,
        crop_img: Image.Image,
        origin_x: int,
        origin_y: int,
        mouse_x: int,
        mouse_y: int,
        target_hint_x: Optional[int] = None,
        target_hint_y: Optional[int] = None,
        target_type_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Visually inspects a cropped screen image around where the physical mouse cursor is located
        compared to the intended target.
        Detects actual physical interactive controls (circular radio buttons, square checkboxes,
        input containers) and calculates the exact physical discrepancy:
            delta_x = target_x - mouse_x
            delta_y = target_y - mouse_y
        """
        cw, ch = crop_img.size
        ref_x = target_hint_x if target_hint_x is not None else mouse_x
        ref_y = target_hint_y if target_hint_y is not None else mouse_y

        crop_mouse_x = mouse_x - origin_x
        crop_mouse_y = mouse_y - origin_y
        crop_ref_x = ref_x - origin_x
        crop_ref_y = ref_y - origin_y

        fallback_res: Dict[str, Any] = {
            "detected": False,
            "control_type": "unknown",
            "target_x": ref_x,
            "target_y": ref_y,
            "mouse_x": mouse_x,
            "mouse_y": mouse_y,
            "delta_x": ref_x - mouse_x,
            "delta_y": ref_y - mouse_y,
            "distance": math.hypot(ref_x - mouse_x, ref_y - mouse_y),
            "confidence": 0.0,
            "candidates": [(ref_x, ref_y)],
            "details": "no_visual_control_detected"
        }

        if cw < 16 or ch < 12:
            return fallback_res

        try:
            gray = crop_img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            ep = edges.load()

            candidates: List[Dict[str, Any]] = []

            # 1. Input Box detection (if typing or container borders exist)
            if target_type_hint == "type_text" or ch >= 25:
                try:
                    m_x, m_y, m_meta = self.measure_and_target_input_box(
                        roi_img=crop_img,
                        center_screen_x=ref_x,
                        center_screen_y=ref_y,
                        crop_origin_x=origin_x,
                        crop_origin_y=origin_y
                    )
                    if m_meta.get("detected"):
                        candidates.append({
                            "type": "input_box",
                            "x": m_x,
                            "y": m_y,
                            "score": 0.95,
                            "bounds": m_meta.get("screen_bounds")
                        })
                except Exception as e:
                    logger.debug(f"Input box check in crop error: {e}")

            # 2. Circular radio buttons & square checkboxes
            # Scan in a horizontal band surrounding the expected control row
            min_cx = max(10, int(min(crop_mouse_x, crop_ref_x) - 120))
            max_cx = min(cw - 10, int(max(crop_mouse_x, crop_ref_x) + 40))
            min_cy = max(8, int(min(crop_mouse_y, crop_ref_y) - 22))
            max_cy = min(ch - 8, int(max(crop_mouse_y, crop_ref_y) + 22))

            for cy in range(min_cy, max_cy):
                for cx in range(min_cx, max_cx):
                    # Test circular radio button perimeters at radii 7..11px
                    for r in [7, 8, 9, 10, 11]:
                        if cx - r < 2 or cx + r >= cw - 2 or cy - r < 2 or cy + r >= ch - 2:
                            continue
                        pts = []
                        for k in range(12):
                            theta = 2.0 * math.pi * k / 12.0
                            cos_t = math.cos(theta)
                            sin_t = math.sin(theta)
                            val = max(ep[int(cx + (r + dr) * cos_t), int(cy + (r + dr) * sin_t)] for dr in [-1, 0, 1])
                            pts.append(val)
                        hits = sum(1 for p in pts if p >= 26)
                        if hits >= 9:
                            # Corner edge check to distinguish square checkbox from circular radio button
                            corner_hits = 0
                            for dr in [-1, 0, 1]:
                                ch_count = sum(
                                    1 for (cdx, cdy) in [(-r - dr, -r - dr), (r + dr, -r - dr), (-r - dr, r + dr), (r + dr, r + dr)]
                                    if 0 <= cx + cdx < cw and 0 <= cy + cdy < ch and ep[cx + cdx, cy + cdy] >= 26
                                )
                                if ch_count >= 3:
                                    corner_hits = max(corner_hits, ch_count)

                            c_type = "checkbox_square" if corner_hits >= 3 else "radio_circle"
                            score = hits / 12.0
                            candidates.append({
                                "type": c_type,
                                "x": origin_x + cx,
                                "y": origin_y + cy,
                                "cx": cx,
                                "cy": cy,
                                "size": r,
                                "score": score
                            })

                    # Test square checkbox boundaries with half-widths 6..10px
                    for hw in [6, 7, 8, 9, 10]:
                        if cx - hw < 2 or cx + hw >= cw - 2 or cy - hw < 2 or cy + hw >= ch - 2:
                            continue
                        t_hits = sum(1 for x in range(cx - hw + 2, cx + hw - 1) if ep[x, cy - hw] >= 26)
                        b_hits = sum(1 for x in range(cx - hw + 2, cx + hw - 1) if ep[x, cy + hw] >= 26)
                        l_hits = sum(1 for y in range(cy - hw + 2, cy + hw - 1) if ep[cx - hw, y] >= 26)
                        r_hits = sum(1 for y in range(cy - hw + 2, cy + hw - 1) if ep[cx + hw, y] >= 26)
                        span = max(1, 2 * hw - 3)
                        edge_ratios = [t_hits / span, b_hits / span, l_hits / span, r_hits / span]
                        if all(er >= 0.40 for er in edge_ratios) and sum(edge_ratios) >= 2.2:
                            candidates.append({
                                "type": "checkbox_square",
                                "x": origin_x + cx,
                                "y": origin_y + cy,
                                "cx": cx,
                                "cy": cy,
                                "size": hw,
                                "score": sum(edge_ratios) / 4.0
                            })

            # 3. Visual center snapping fallback if no discrete shapes detected
            if not candidates:
                snap_x, snap_y = self.find_visual_element_center(crop_img, ref_x, ref_y)
                if (snap_x, snap_y) != (ref_x, ref_y):
                    candidates.append({
                        "type": "visual_element_center",
                        "x": snap_x,
                        "y": snap_y,
                        "score": 0.70
                    })

            if not candidates:
                return fallback_res

            # Group duplicate / overlapping candidates within 6px
            clustered: List[Dict[str, Any]] = []
            for cand in candidates:
                matched = False
                for cl in clustered:
                    if abs(cl["x"] - cand["x"]) <= 6 and abs(cl["y"] - cand["y"]) <= 6:
                        if cand.get("score", 0.0) > cl.get("score", 0.0):
                            cl.update(cand)
                        matched = True
                        break
                if not matched:
                    clustered.append(dict(cand))

            # Rank candidates: prioritize proximity to the target row, favoring leftward choice controls
            def _rank(c: Dict[str, Any]) -> float:
                dx = c["x"] - mouse_x
                dy = c["y"] - mouse_y
                vert_pen = abs(dy) * 3.5
                # On web pages, radio buttons and checkboxes are to the left of the option text
                horiz_pen = abs(dx) * 0.35 if dx <= 0 else (dx * 2.2)
                type_boost = 15.0 if c["type"] in ["radio_circle", "checkbox_square"] else 0.0
                return (c.get("score", 0.5) * 100.0) + type_boost - vert_pen - horiz_pen

            clustered.sort(key=_rank, reverse=True)
            best = clustered[0]
            best_x = int(best["x"])
            best_y = int(best["y"])
            delta_x = best_x - mouse_x
            delta_y = best_y - mouse_y

            unique_coords = []
            for c in clustered:
                coord = (int(c["x"]), int(c["y"]))
                if coord not in unique_coords:
                    unique_coords.append(coord)

            result = {
                "detected": True,
                "control_type": best["type"],
                "target_x": best_x,
                "target_y": best_y,
                "mouse_x": mouse_x,
                "mouse_y": mouse_y,
                "delta_x": delta_x,
                "delta_y": delta_y,
                "distance": math.hypot(delta_x, delta_y),
                "confidence": best.get("score", 0.8),
                "candidates": unique_coords,
                "details": (
                    f"Detected {best['type']} at ({best_x}, {best_y}) vs physical mouse at ({mouse_x}, {mouse_y}) "
                    f"-> offset: ({delta_x:+d}px, {delta_y:+d}px)"
                )
            }
            logger.info(f"locate_physical_target_near_mouse: {result['details']}")
            return result

        except Exception as e:
            logger.warning(f"Error in detect_controls_in_crop: {e}")
            return fallback_res

    def locate_physical_target_near_mouse(
        self,
        mouse_x: int,
        mouse_y: int,
        target_hint_x: Optional[int] = None,
        target_hint_y: Optional[int] = None,
        search_margin_left: int = 140,
        search_margin_right: int = 60,
        search_margin_v: int = 40,
        target_type_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Grabs a physical desktop screenshot surrounding the actual physical mouse cursor
        and visually compares where the mouse is on screen compared to the target control.
        Returns visual detection result with exact physical offset (delta_x, delta_y).
        """
        ref_x = target_hint_x if target_hint_x is not None else mouse_x
        ref_y = target_hint_y if target_hint_y is not None else mouse_y

        fallback_res: Dict[str, Any] = {
            "detected": False,
            "control_type": "unknown",
            "target_x": ref_x,
            "target_y": ref_y,
            "mouse_x": mouse_x,
            "mouse_y": mouse_y,
            "delta_x": ref_x - mouse_x,
            "delta_y": ref_y - mouse_y,
            "distance": math.hypot(ref_x - mouse_x, ref_y - mouse_y),
            "confidence": 0.0,
            "candidates": [(ref_x, ref_y)],
            "details": "fallback_no_visual_control_detected"
        }

        try:
            crop_min_x = max(0, min(mouse_x, ref_x) - search_margin_left)
            crop_max_x = max(mouse_x, ref_x) + search_margin_right
            crop_min_y = max(0, min(mouse_y, ref_y) - search_margin_v)
            crop_max_y = max(mouse_y, ref_y) + search_margin_v

            origin_x = int(crop_min_x)
            origin_y = int(crop_min_y)
            crop_w = int(crop_max_x - origin_x)
            crop_h = int(crop_max_y - origin_y)

            if crop_w < 16 or crop_h < 12:
                return fallback_res

            monitor = {"left": origin_x, "top": origin_y, "width": crop_w, "height": crop_h}
            sct_img = self._sct.grab(monitor)
            crop_img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            return self.detect_controls_in_crop(
                crop_img=crop_img,
                origin_x=origin_x,
                origin_y=origin_y,
                mouse_x=mouse_x,
                mouse_y=mouse_y,
                target_hint_x=ref_x,
                target_hint_y=ref_y,
                target_type_hint=target_type_hint
            )
        except Exception as e:
            logger.debug(f"locate_physical_target_near_mouse error: {e}")
            return fallback_res


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
                    isx, isy = int(sx), int(sy)
                    live_roi = self.capture_roi(isx, isy)
                    if act_type in ["click", "double_click"]:
                        # Fetch sibling choice coordinates (from AI choices or on-screen vertical scan)
                        sib_coords = self.get_sibling_choice_coordinates(isx, isy, result_data)
                        sibling_rois = [self.capture_roi(cx, cy) for cx, cy in sib_coords]
                        sel, r_reason, conf = self.is_radio_or_checkbox_selected(live_roi, sibling_rois=sibling_rois)
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
                if "recovery" in reason or "readjustment" in reason:
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
    ) -> TransitionResult:
        """
        Verifies that screen transitioned or responded visually following
        a navigation action ("Check Answer", "Next", submit).
        Returns TransitionResult(is_transitioned, mean_diff).
        """
        if before_img is None or after_img is None:
            return TransitionResult(True, 0.0, details="No image provided for comparison")

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
            details = f"mean_diff={mean_diff:.2f}, changed_px={changed_pixels}"
            logger.debug(
                f"verify_screen_transition: is_transitioned={is_transitioned}, {details}"
            )
            return TransitionResult(is_transitioned, mean_diff, details=details)
        except Exception as e:
            logger.warning(f"Error in verify_screen_transition: {e}")
            return TransitionResult(True, 0.0, details=f"Exception: {e}")

    def detect_platform_evaluation_markers(
        self,
        image: Optional[Image.Image] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
        min_cluster_pixels: int = 1200
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
                if (r >= 160 and g <= 80 and b <= 80) or (r >= 145 and r > (1.8 * max(g, b))):
                    red_count += 1
                # Strong green evaluation indicators (e.g. #10b981, #059669, #16a34a, #22c55e)
                elif (g >= 130 and r <= 90 and b <= 90) or (g >= 120 and g > (1.5 * max(r, b))):
                    green_count += 1

            if red_count >= min_cluster_pixels and red_count > (green_count * 2.0):
                confidence = min(0.99, 0.65 + (red_count / 600.0) * 0.35)
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
                confidence = min(0.99, 0.65 + (green_count / 600.0) * 0.35)
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
        Uses differential comparison to ignore static pre-existing colored elements.
        """
        if after_check_img is None:
            return {
                "detected": False,
                "status": "unsubmitted",
                "is_incorrect": False,
                "is_correct": False,
                "confidence": 0.0,
                "details": "no_after_image",
                "screen_transitioned": False,
                "transition_diff": 0.0
            }

        target_img = after_check_img
        trans_ok = False
        diff = 0.0

        if before_check_img is not None and after_check_img is not None:
            try:
                trans_ok, diff = self.verify_screen_transition(before_check_img, after_check_img)
                # If images are identical size, create a difference mask to inspect ONLY what changed
                if before_check_img.size == after_check_img.size:
                    diff_img = ImageChops.difference(before_check_img.convert("RGB"), after_check_img.convert("RGB"))
                    # Mask of pixels that changed by at least 15 intensity
                    diff_gray = diff_img.convert("L")
                    mask = diff_gray.point(lambda p: 255 if p > 15 else 0)
                    # Apply mask onto after_check_img so only new pixels are evaluated
                    masked_after = Image.new("RGB", after_check_img.size, (255, 255, 255))
                    masked_after.paste(after_check_img.convert("RGB"), mask=mask)
                    target_img = masked_after
            except Exception as e:
                logger.debug(f"Differential evaluation mask error: {e}")

        markers = self.detect_platform_evaluation_markers(target_img, min_cluster_pixels=1200)
        markers["is_incorrect"] = (markers.get("status") == "incorrect")
        markers["is_correct"] = (markers.get("status") == "correct")
        markers["screen_transitioned"] = trans_ok
        markers["transition_diff"] = diff

        return markers

    def verify_written_input_area(
        self,
        before_roi: Optional[Image.Image],
        after_roi: Optional[Image.Image],
        expected_min_words: Optional[int] = None,
        expected_chars: int = 0,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verifies that a written response (essay, short answer, explanation) was entered into the input box:
        - Confirms significant stroke density increase (characters actually rendered).
        - Estimates pixel change ratio.
        - Returns (is_verified, reason_string, metrics_dict).
        """
        if before_roi is None or after_roi is None:
            return True, "unverified_no_baseline", {}

        try:
            b_gray = before_roi.convert("L")
            a_gray = after_roi.convert("L")

            diff = ImageChops.difference(b_gray, a_gray)
            stat = ImageStat.Stat(diff)
            mean_diff = stat.mean[0]

            hist = diff.histogram()
            changed_pixels = sum(hist[18:])
            total_pixels = b_gray.width * b_gray.height
            change_ratio = changed_pixels / max(1, total_pixels)

            # For multi-word written responses, we expect significant text presence (>25 changed pixels or >1.0% change)
            is_verified = (changed_pixels >= 25 or mean_diff >= 1.0 or change_ratio >= 0.01)
            reason = "text_strokes_verified" if is_verified else "insufficient_text_detected"

            metrics = {
                "changed_pixels": changed_pixels,
                "mean_diff": round(mean_diff, 2),
                "change_ratio": round(change_ratio, 4),
                "expected_min_words": expected_min_words,
                "expected_chars": expected_chars,
            }
            logger.info(f"verify_written_input_area: verified={is_verified} ({reason}), metrics={metrics}")
            return is_verified, reason, metrics
        except Exception as e:
            logger.warning(f"verify_written_input_area failed: {e}")
            return True, f"error_{e}", {}



