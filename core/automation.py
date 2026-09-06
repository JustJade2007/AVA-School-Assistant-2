"""
Automation execution module for AVA School Assistant 2.
Provides humanized mouse trajectories (Bézier curves with overshoots and micro-corrections),
non-center click variance, smart typing with typo recovery on words, local action verification,
and emergency abort failsafes.
"""

import time
import math
import random
import re
import threading
from typing import Optional, List, Dict, Any, Tuple, Callable
import pyautogui

from core.logger import get_logger
from core.local_verifier import LocalVisualVerifier

logger = get_logger("automation")

# Enable PyAutoGUI failsafe: moving mouse to any corner of screen aborts
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.04

# QWERTY adjacent key map for authentic typo simulation
QWERTY_NEIGHBORS = {
    'a': ['s', 'q', 'z', 'w'],
    'b': ['v', 'g', 'h', 'n'],
    'c': ['x', 'd', 'f', 'v'],
    'd': ['s', 'e', 'r', 'f', 'c', 'x'],
    'e': ['w', 's', 'd', 'r'],
    'f': ['d', 'r', 't', 'g', 'v', 'c'],
    'g': ['f', 't', 'y', 'h', 'b', 'v'],
    'h': ['g', 'y', 'u', 'j', 'n', 'b'],
    'i': ['u', 'j', 'k', 'o'],
    'j': ['h', 'u', 'i', 'k', 'm', 'n'],
    'k': ['j', 'i', 'o', 'l', 'm'],
    'l': ['k', 'o', 'p'],
    'm': ['n', 'j', 'k'],
    'n': ['b', 'h', 'j', 'm'],
    'o': ['i', 'k', 'l', 'p'],
    'p': ['o', 'l'],
    'q': ['w', 'a'],
    'r': ['e', 'd', 'f', 't'],
    's': ['a', 'w', 'e', 'd', 'x', 'z'],
    't': ['r', 'f', 'g', 'y'],
    'u': ['y', 'h', 'j', 'i'],
    'v': ['c', 'f', 'g', 'b'],
    'w': ['q', 'a', 's', 'e'],
    'x': ['z', 's', 'd', 'c'],
    'y': ['t', 'g', 'h', 'u'],
    'z': ['a', 's', 'x']
}


def is_math_or_formula(text: str) -> bool:
    """
    Returns True if the text represents numbers, arithmetic, algebraic formulas,
    or equations that MUST NEVER have typos simulated.
    """
    clean = text.strip()
    if not clean:
        return False
    # 1. Pure numbers, decimals, currencies, percentages, arithmetic symbols
    if re.match(r"^[\d\.\+\-\*\/\=\(\)\,\s\^\%\$\<\>\:\;\#]+$", clean):
        return True
    # 2. Algebraic expressions / formulas (math operators / digits and short variable names)
    has_math_ops = bool(re.search(r"[\=\+\-\*\/\^\<\>]", clean))
    has_digits = bool(re.search(r"\d", clean))
    words = re.findall(r"[A-Za-z]{2,}", clean)
    math_keywords = {"sin", "cos", "tan", "sec", "csc", "cot", "log", "ln", "sqrt", "lim", "pi", "theta"}
    non_math_words = [w.lower() for w in words if w.lower() not in math_keywords]
    if (has_math_ops or has_digits) and len(non_math_words) == 0:
        return True
    return False


class EmergencyStopException(Exception):
    """Raised when an automation action is halted by emergency stop."""
    pass


class AutomationExecutor:
    """Executes GUI actions with humanization, local verification, and safety controls."""

    def __init__(
        self,
        humanize: bool = True,
        speed_multiplier: float = 1.0,
        click_variance_enabled: bool = True,
        smart_typos_enabled: bool = True,
        local_verification_enabled: bool = True,
        on_adjustment_callback: Optional[Callable[[str], None]] = None
    ):
        self.humanize = humanize
        self.speed_multiplier = max(0.1, speed_multiplier)
        self.click_variance_enabled = click_variance_enabled
        self.smart_typos_enabled = smart_typos_enabled
        self.local_verification_enabled = local_verification_enabled
        self.on_adjustment_callback = on_adjustment_callback

        self.verifier = LocalVisualVerifier()
        self._stop_event = threading.Event()
        self._is_executing = False

    def request_stop(self):
        """Immediately signals any running automation sequence to halt."""
        self._stop_event.set()
        try:
            pyautogui.mouseUp(button="left")
            pyautogui.mouseUp(button="right")
        except Exception:
            pass

    def reset_stop(self):
        self._stop_event.clear()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def _check_stop(self):
        if self._stop_event.is_set():
            raise EmergencyStopException("Emergency stop triggered. Halting execution.")

    def apply_click_variance(self, x: int, y: int, radius_x: int = 2, radius_y: int = 2) -> Tuple[int, int]:
        """Adds subtle Gaussian jitter (1-2px) so clicks never land on the exact mathematical center."""
        if not self.humanize or not self.click_variance_enabled:
            return x, y

        dx = int(random.gauss(0, radius_x * 0.45))
        dy = int(random.gauss(0, radius_y * 0.45))
        dx = max(-radius_x, min(radius_x, dx))
        dy = max(-radius_y, min(radius_y, dy))
        return x + dx, y + dy

    def move_mouse_humanized(self, target_x: int, target_y: int, duration: Optional[float] = None, allow_overshoot: bool = False):
        """
        Moves mouse to target directly using cubic Bézier curve with humanized velocity curves.
        Direct trajectory directly into the target coordinate without moving past or overshooting the box.
        """
        self._check_stop()

        start_x, start_y = pyautogui.position()
        dist = math.hypot(target_x - start_x, target_y - start_y)
        if dist < 4:
            pyautogui.moveTo(target_x, target_y)
            return

        if not self.humanize:
            move_dur = (0.2 * self.speed_multiplier) if duration is None else duration
            pyautogui.moveTo(target_x, target_y, duration=move_dur, tween=pyautogui.easeOutQuad)
            return

        self._bezier_move(start_x, start_y, target_x, target_y, duration=duration)

    def _bezier_move(self, start_x: int, start_y: int, target_x: int, target_y: int, duration: Optional[float] = None):
        """Internal cubic Bézier path execution."""
        dist = math.hypot(target_x - start_x, target_y - start_y)
        if dist < 3:
            pyautogui.moveTo(target_x, target_y)
            return

        if duration is None:
            duration = min(0.65, max(0.18, (dist / 1400.0) * 0.45)) * self.speed_multiplier

        deviation = dist * random.uniform(0.08, 0.22)
        angle = math.atan2(target_y - start_y, target_x - start_x)
        normal_angle = angle + (math.pi / 2) * random.choice([1, -1])

        cp1_x = start_x + (target_x - start_x) * 0.33 + math.cos(normal_angle) * deviation
        cp1_y = start_y + (target_y - start_y) * 0.33 + math.sin(normal_angle) * deviation
        cp2_x = start_x + (target_x - start_x) * 0.66 + math.cos(normal_angle) * (deviation * 0.55)
        cp2_y = start_y + (target_y - start_y) * 0.66 + math.sin(normal_angle) * (deviation * 0.55)

        steps = max(14, int(duration * 60))
        start_time = time.time()

        for step in range(steps + 1):
            self._check_stop()
            t = step / float(steps)
            ease_t = 3 * t**2 - 2 * t**3

            u = 1 - ease_t
            cur_x = (u**3 * start_x +
                     3 * u**2 * ease_t * cp1_x +
                     3 * u * ease_t**2 * cp2_x +
                     ease_t**3 * target_x)
            cur_y = (u**3 * start_y +
                     3 * u**2 * ease_t * cp1_y +
                     3 * u * ease_t**2 * cp2_y +
                     ease_t**3 * target_y)

            jitter_x = random.uniform(-0.6, 0.6) if step < steps else 0
            jitter_y = random.uniform(-0.6, 0.6) if step < steps else 0

            pyautogui.moveTo(int(cur_x + jitter_x), int(cur_y + jitter_y))

            elapsed = time.time() - start_time
            target_elapsed = (duration / steps) * step
            if target_elapsed > elapsed:
                time.sleep(target_elapsed - elapsed)

        pyautogui.moveTo(target_x, target_y)

    def click(self, x: int, y: int, button: str = "left", double: bool = False, allow_variance: bool = True):
        """Moves to coordinate with variance and clicks with realistic hold duration."""
        self._check_stop()
        final_x, final_y = self.apply_click_variance(x, y) if allow_variance else (x, y)
        self.move_mouse_humanized(final_x, final_y)
        self._check_stop()

        # Human-like pre-click hesitation
        if self.humanize:
            time.sleep(random.uniform(0.08, 0.20))

        if double:
            pyautogui.doubleClick(final_x, final_y, button=button)
        else:
            # Realistic mouse down -> hold -> mouse up
            if self.humanize:
                pyautogui.mouseDown(final_x, final_y, button=button)
                time.sleep(random.uniform(0.065, 0.110))
                pyautogui.mouseUp(final_x, final_y, button=button)
            else:
                pyautogui.click(final_x, final_y, button=button)

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = 0.5):
        """Drags from starting point to destination."""
        self._check_stop()
        self.move_mouse_humanized(from_x, from_y)
        self._check_stop()

        time.sleep(0.08)
        pyautogui.mouseDown(button="left")
        time.sleep(0.06)

        self.move_mouse_humanized(to_x, to_y, duration=duration)
        self._check_stop()

        time.sleep(0.08)
        pyautogui.mouseUp(button="left")

    def type_text(self, text: str, interval: float = 0.04):
        """
        Types string with randomized human typing cadence.
        Features Smart Typo Simulation: creates occasional realistic typos on word tokens,
        pauses for human realization, backspaces, and retypes the correct character.
        GUARANTEE: Pure numbers, math equations, and short codes are 100% typo-free!
        """
        self._check_stop()

        # Check if text is pure math/numeric or code (must be 100% clean)
        is_numeric_or_formula = is_math_or_formula(text)

        i = 0
        while i < len(text):
            self._check_stop()
            char = text[i]
            lower_char = char.lower()

            # Smart Typo Simulation on letters
            should_typo = (
                self.humanize and
                self.smart_typos_enabled and
                not is_numeric_or_formula and
                lower_char in QWERTY_NEIGHBORS and
                random.random() < 0.025  # ~2.5% chance per eligible character
            )

            if should_typo:
                # 1. Type adjacent wrong key
                wrong_char = random.choice(QWERTY_NEIGHBORS[lower_char])
                if char.isupper():
                    wrong_char = wrong_char.upper()
                pyautogui.write(wrong_char)

                # 2. Human realization pause
                time.sleep(random.uniform(0.14, 0.28))
                self._check_stop()

                # 3. Backspace to erase mistake
                pyautogui.press("backspace")
                time.sleep(random.uniform(0.06, 0.12))
                self._check_stop()

                # 4. Type the correct character
                pyautogui.write(char)
            else:
                pyautogui.write(char)

            if self.humanize:
                # Variable typing speed with cadence bursts
                delay = interval * random.uniform(0.65, 1.45)
                if char in [",", ".", " ", "?", "!"]:
                    delay += random.uniform(0.09, 0.24)
                elif char.isupper():
                    delay += random.uniform(0.04, 0.10)
                time.sleep(delay)
            else:
                time.sleep(interval)

            i += 1

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None):
        """Scrolls mouse wheel."""
        self._check_stop()
        if x is not None and y is not None:
            self.move_mouse_humanized(x, y)
        self._check_stop()
        pyautogui.scroll(clicks)

    def key_press(self, key: str):
        """Presses an individual key or combo (e.g. 'enter', 'tab', 'ctrl+a')."""
        self._check_stop()
        if "+" in key:
            keys = [k.strip().lower() for k in key.split("+")]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key.lower())

    def idle_cursor_wander(self, duration: float, stop_check_event: Optional[threading.Event] = None):
        """
        Subtly wanders the cursor during reading/thinking deliberation pauses
        to mimic natural visual reading across lines of text.
        """
        start_time = time.time()
        cur_x, cur_y = pyautogui.position()

        while (time.time() - start_time) < duration:
            self._check_stop()
            if stop_check_event and stop_check_event.is_set():
                break

            # Gentle random drift (15-35px horizontally, 5-15px vertically)
            target_x = max(100, min(1800, cur_x + random.randint(-35, 45)))
            target_y = max(100, min(1000, cur_y + random.randint(-12, 12)))

            move_dur = random.uniform(0.5, 1.1)
            self._bezier_move(cur_x, cur_y, target_x, target_y, duration=move_dur)
            cur_x, cur_y = target_x, target_y

            # Idle pause before next slight movement
            pause_time = random.uniform(0.4, 0.9)
            remaining = duration - (time.time() - start_time)
            time.sleep(min(pause_time, max(0.0, remaining)))

    def execute_action(self, action: Dict[str, Any]):
        """
        Executes a single action with local verification and visual center snapping.
        """
        self._check_stop()
        action_type = action.get("type", "").lower()
        desc = action.get("description", "")
        logger.debug(f"Executing action [{action_type}]: {desc}")

        # Check screen translated coordinates
        x = action.get("screen_x", action.get("x"))
        y = action.get("screen_y", action.get("y"))

        if action_type in ["click", "double_click"] and x is not None and y is not None:
            target_x, target_y = int(x), int(y)
            is_double = (action_type == "double_click")

            # Local verification setup: capture baseline ROI and option row band
            before_roi = None
            before_band = None
            band_origin_x, band_origin_y = max(0, target_x - 85), max(0, target_y - 25)
            if self.local_verification_enabled:
                before_roi = self.verifier.capture_roi(target_x, target_y)
                before_band, band_origin_x, band_origin_y = self.verifier.capture_band(
                    target_x, target_y, offset_left=85, offset_right=35, radius_h=25
                )

            # Perform primary click
            self.click(target_x, target_y, double=is_double)

            # Post-action local verification
            is_confirmed = False
            verification_reason = "unverified"

            if self.local_verification_enabled and before_roi:
                time.sleep(0.09)
                after_roi = self.verifier.capture_roi(target_x, target_y)
                after_band, _, _ = self.verifier.capture_band(
                    target_x, target_y, offset_left=85, offset_right=35, radius_h=25
                )

                # 1. Direct radio / checkbox selection check at click location
                sel, r_reason, conf = self.verifier.is_radio_or_checkbox_selected(after_roi)
                if sel:
                    is_confirmed = True
                    verification_reason = r_reason
                else:
                    # 2. Check for option row background highlight
                    row_hl, hl_score = self.verifier.is_option_row_highlighted(before_band, after_band)
                    if row_hl:
                        is_confirmed = True
                        verification_reason = f"row_highlight (diff={hl_score:.1f})"
                    else:
                        # 3. Check for general pixel difference
                        diff_ok, diff_score = self.verifier.verify_action_completion(before_roi, after_roi, action_type="click")
                        if diff_ok and diff_score >= 1.6:
                            is_confirmed = True
                            verification_reason = f"pixel_diff (score={diff_score:.1f})"

                # --- SMART ZERO-TOKEN RECOVERY PROBING ---
                # If primary click missed (e.g. coordinates landed on text label instead of radio circle):
                if not is_confirmed:
                    logger.warning(
                        f"Action [{action_type}] at ({target_x}, {target_y}) did not register answer state. "
                        f"Initiating zero-token recovery probing..."
                    )

                    recovery_candidates = []

                    # Probe candidate 1: Search option band leftward for circular radio button / checkbox
                    found_control = self.verifier.find_radio_or_checkbox_in_band(
                        after_band, target_x, target_y, band_origin_x, band_origin_y, max_scan_left=80
                    )
                    if found_control:
                        recovery_candidates.append(found_control)

                    # Probe candidate 2: Visual center snapping from ROI
                    snapped_x, snapped_y = self.verifier.find_visual_element_center(before_roi, target_x, target_y)
                    if (snapped_x, snapped_y) != (target_x, target_y) and (snapped_x, snapped_y) not in recovery_candidates:
                        recovery_candidates.append((snapped_x, snapped_y))

                    # Probe candidates 3: Standard web radio offsets (radio circles standardly 20-50px left of text)
                    for dx in [-24, -38, -52, -14]:
                        cand = (target_x + dx, target_y)
                        if cand not in recovery_candidates:
                            recovery_candidates.append(cand)

                    # Probe candidates 4: High-DPI vertical adjustments
                    for dy in [-8, +8]:
                        cand = (target_x, target_y + dy)
                        if cand not in recovery_candidates:
                            recovery_candidates.append(cand)

                    # Execute recovery probes
                    for probe_x, probe_y in recovery_candidates:
                        self._check_stop()
                        offset_x = probe_x - target_x
                        offset_y = probe_y - target_y
                        msg = f"🎯 Zero-token recovery: Retrying click at ({probe_x}, {probe_y}) [{offset_x:+d}px, {offset_y:+d}px]"
                        logger.info(msg)
                        if self.on_adjustment_callback:
                            self.on_adjustment_callback(msg)

                        # Retry click at probed coordinate without mouse variance
                        self.click(probe_x, probe_y, double=is_double, allow_variance=False)
                        time.sleep(0.09)

                        # Check if this probe successfully activated the radio button / checkbox
                        probe_roi = self.verifier.capture_roi(probe_x, probe_y)
                        p_sel, p_reason, p_conf = self.verifier.is_radio_or_checkbox_selected(probe_roi)
                        p_diff_ok, p_diff_score = self.verifier.verify_action_completion(before_roi, probe_roi, action_type="click")

                        if p_sel or (p_diff_ok and p_diff_score >= 1.8):
                            logger.info(f"[OK] Zero-token recovery SUCCESS at ({probe_x}, {probe_y}): {p_reason if p_sel else 'diff_confirmed'}")
                            is_confirmed = True
                            verification_reason = f"recovery_{p_reason if p_sel else 'diff_confirmed'}"
                            action["screen_x"] = probe_x
                            action["screen_y"] = probe_y
                            if "x" in action: action["x"] = probe_x
                            if "y" in action: action["y"] = probe_y
                            break

            action["verified"] = is_confirmed
            action["verification_reason"] = verification_reason

        elif action_type == "drag":
            fx = action.get("screen_from_x", action.get("from_x"))
            fy = action.get("screen_from_y", action.get("from_y"))
            tx = action.get("screen_to_x", action.get("to_x"))
            ty = action.get("screen_to_y", action.get("to_y"))

            start_before = None
            dest_before = None
            if self.local_verification_enabled and all(v is not None for v in [fx, fy, tx, ty]):
                start_before = self.verifier.capture_roi(int(fx), int(fy))
                dest_before = self.verifier.capture_roi(int(tx), int(ty))

            if all(v is not None for v in [fx, fy, tx, ty]):
                self.drag(int(fx), int(fy), int(tx), int(ty))

            is_drag_ok = True
            drag_reason = "unverified"
            if self.local_verification_enabled and start_before and dest_before:
                time.sleep(0.08)
                start_after = self.verifier.capture_roi(int(fx), int(fy))
                dest_after = self.verifier.capture_roi(int(tx), int(ty))
                is_drag_ok, drag_reason = self.verifier.verify_drag_completion(
                    start_before, start_after, dest_before, dest_after
                )
                if not is_drag_ok:
                    logger.warning(f"Drag action failed zero-token confirmation ({drag_reason}). Retrying with extended hold...")
                    self.drag(int(fx), int(fy), int(tx), int(ty), duration=0.75)
                    time.sleep(0.08)
                    start_after2 = self.verifier.capture_roi(int(fx), int(fy))
                    dest_after2 = self.verifier.capture_roi(int(tx), int(ty))
                    is_drag_ok, drag_reason = self.verifier.verify_drag_completion(
                        start_before, start_after2, dest_before, dest_after2
                    )
                    if is_drag_ok:
                        drag_reason = f"recovery_{drag_reason}"

            action["verified"] = is_drag_ok
            action["verification_reason"] = drag_reason

        elif action_type == "type_text":
            text = action.get("text", "")
            clear_first = action.get("clear_first", False)

            before_input_roi = None
            if self.local_verification_enabled and x is not None and y is not None:
                before_input_roi = self.verifier.capture_roi(int(x), int(y))

            if x is not None and y is not None:
                self.click(int(x), int(y), allow_variance=False)
                time.sleep(0.1)

            if clear_first:
                logger.info("Clearing existing text in input field (Ctrl+A -> Backspace)...")
                self.key_press("ctrl+a")
                time.sleep(0.05)
                self.key_press("backspace")
                time.sleep(0.05)

            self.type_text(text)

            # Post-typing verification: verify text entered the input
            is_filled = True
            f_reason = "unverified"
            if self.local_verification_enabled and x is not None and y is not None:
                time.sleep(0.08)
                after_input_roi = self.verifier.capture_roi(int(x), int(y))
                is_filled, f_reason, f_conf = self.verifier.is_text_input_filled(after_input_roi, before_input_roi)

                # Smart Zero-Token Recovery for typing: If empty, snap center, click firmly and retype
                if not is_filled:
                    logger.warning(f"Type text unconfirmed ({f_reason}). Retrying input focus and retyping...")
                    snapped_x, snapped_y = self.verifier.find_visual_element_center(before_input_roi, int(x), int(y)) if before_input_roi else (int(x), int(y))
                    self.click(snapped_x, snapped_y, allow_variance=False)
                    time.sleep(0.08)
                    self.key_press("ctrl+a")
                    time.sleep(0.04)
                    self.key_press("backspace")
                    time.sleep(0.04)
                    self.type_text(text)
                    time.sleep(0.08)
                    after_input_roi2 = self.verifier.capture_roi(snapped_x, snapped_y)
                    is_filled, f_reason, _ = self.verifier.is_text_input_filled(after_input_roi2, before_input_roi)
                    if is_filled:
                        f_reason = f"recovery_{f_reason}"

            action["verified"] = is_filled
            action["verification_reason"] = f_reason

        elif action_type == "key_press":
            key = action.get("key", "enter")
            before_key_roi = None
            key_x = int(x) if x is not None else 400
            key_y = int(y) if y is not None else 300
            if self.local_verification_enabled:
                before_key_roi = self.verifier.capture_roi(key_x, key_y)

            self.key_press(key)

            key_ok = True
            key_reason = "executed"
            if self.local_verification_enabled and before_key_roi:
                time.sleep(0.08)
                after_key_roi = self.verifier.capture_roi(key_x, key_y)
                diff_ok, diff_score = self.verifier.verify_action_completion(before_key_roi, after_key_roi, action_type="click")
                key_ok = diff_ok or diff_score >= 1.0
                key_reason = f"key_diff={diff_score:.1f}"

            action["verified"] = key_ok
            action["verification_reason"] = key_reason

        elif action_type == "scroll":
            clicks = action.get("clicks", -3)
            scroll_x = int(x) if x is not None else 500
            scroll_y = int(y) if y is not None else 400

            before_scroll_roi = None
            if self.local_verification_enabled:
                before_scroll_roi = self.verifier.capture_roi(scroll_x, scroll_y, radius_w=60, radius_h=60)

            self.scroll(clicks, x, y)

            scroll_ok = True
            scroll_reason = "executed"
            if self.local_verification_enabled and before_scroll_roi:
                time.sleep(0.1)
                after_scroll_roi = self.verifier.capture_roi(scroll_x, scroll_y, radius_w=60, radius_h=60)
                diff_ok, diff_score = self.verifier.verify_action_completion(before_scroll_roi, after_scroll_roi, action_type="scroll")
                if not diff_ok and diff_score < 0.6:
                    logger.warning(f"Scroll action produced 0 displacement (diff={diff_score:.1f}). Focusing container and retrying...")
                    self.click(scroll_x, scroll_y, allow_variance=False)
                    time.sleep(0.08)
                    self.scroll(clicks, scroll_x, scroll_y)
                    time.sleep(0.1)
                    after_scroll_roi2 = self.verifier.capture_roi(scroll_x, scroll_y, radius_w=60, radius_h=60)
                    diff_ok, diff_score = self.verifier.verify_action_completion(before_scroll_roi, after_scroll_roi2, action_type="scroll")
                    if diff_ok:
                        scroll_reason = f"recovery_scroll_diff={diff_score:.1f}"
                    else:
                        scroll_reason = f"scroll_diff={diff_score:.1f}"
                else:
                    scroll_reason = f"scroll_diff={diff_score:.1f}"
                scroll_ok = diff_ok or diff_score >= 0.8

            action["verified"] = scroll_ok
            action["verification_reason"] = scroll_reason

        elif action_type == "delay":
            secs = float(action.get("seconds", 0.5))
            time.sleep(secs)
            action["verified"] = True
            action["verification_reason"] = "delay_completed"

    def execute_action_sequence(self, actions: List[Dict[str, Any]], delay_between: float = 0.3) -> Dict[str, Any]:
        """
        Executes a sequence of actions with delay between each, dynamic blank shift tracking,
        and zero-token action verification.
        Returns a verification summary dict.
        """
        self.reset_stop()
        self._is_executing = True
        try:
            for idx, action in enumerate(actions):
                self._check_stop()

                # Dynamic layout shift tracking for subsequent blanks:
                # If current action is 'type_text', subsequent input actions might shift because the typed text
                # expands the current box or line. Pre-capture templates of subsequent input targets before typing.
                subsequent_input_targets = []
                if self.local_verification_enabled and action.get("type", "").lower() == "type_text":
                    for sub_idx in range(idx + 1, len(actions)):
                        sub_act = actions[sub_idx]
                        if sub_act.get("type", "").lower() in ["type_text", "click"]:
                            sx = sub_act.get("screen_x", sub_act.get("x"))
                            sy = sub_act.get("screen_y", sub_act.get("y"))
                            if sx is not None and sy is not None:
                                t_roi = self.verifier.capture_roi(int(sx), int(sy), radius_w=25, radius_h=15)
                                subsequent_input_targets.append((sub_idx, int(sx), int(sy), t_roi))

                self.execute_action(action)

                # After typing, inspect if subsequent inputs shifted
                if subsequent_input_targets:
                    time.sleep(0.08)
                    for sub_idx, orig_x, orig_y, t_roi in subsequent_input_targets:
                        band_img, bx, by = self.verifier.capture_band(orig_x, orig_y, offset_left=40, offset_right=200, radius_h=30)
                        shifted = self.verifier.track_shifted_input_box(t_roi, band_img, bx, by, orig_x, orig_y)
                        if shifted and shifted != (orig_x, orig_y):
                            nx, ny = shifted
                            dx = nx - orig_x
                            dy = ny - orig_y
                            sub_act = actions[sub_idx]
                            sub_act["screen_x"] = nx
                            sub_act["screen_y"] = ny
                            if "x" in sub_act:
                                sub_act["x"] = nx
                            if "y" in sub_act:
                                sub_act["y"] = ny
                            msg = f"🎯 Adjusted input target #{sub_idx + 1} layout shift ({dx:+d}px, {dy:+d}px)"
                            logger.info(msg)
                            if self.on_adjustment_callback:
                                self.on_adjustment_callback(msg)

                time.sleep(delay_between)

            # Overall sequence evaluation
            verifiable_actions = [a for a in actions if a.get("type", "").lower() in ["click", "double_click", "type_text", "drag", "key_press", "scroll"]]
            verified_count = sum(1 for a in verifiable_actions if a.get("verified", False))
            all_verified = (verified_count == len(verifiable_actions)) if verifiable_actions else True

            return {
                "all_verified": all_verified,
                "verified_count": verified_count,
                "total_verifiable": len(verifiable_actions),
                "actions": actions
            }
        finally:
            self._is_executing = False
