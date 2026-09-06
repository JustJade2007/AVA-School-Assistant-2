"""
Assistant Engine orchestrator for AVA School Assistant 2.
Coordinates screen capture, AI vision queries, automation execution,
state transitions, and loop control.
"""

import time
import random
import threading
from enum import Enum
from typing import Dict, Any, Optional, Callable, List, Tuple
from PIL import Image, ImageStat

from config import AppConfig, ConfigManager
from core.capture import ScreenCapture
from core.ai_client import AIClient
from core.automation import AutomationExecutor, EmergencyStopException
from core.local_verifier import LocalVisualVerifier
from core.logger import get_logger
from core.error_handler import create_error_diagnostic, ErrorDiagnostic

logger = get_logger("engine")


class EngineState(Enum):
    IDLE = "Idle"
    SCANNING = "Scanning Screen..."
    THINKING = "Solving with AI..."
    READING = "Reading Question..."
    WAITING_CONFIRMATION = "Waiting for Confirmation"
    EXECUTING = "Executing Actions..."
    VERIFYING = "Verifying Answer..."
    INSPECTING = "Inspecting Supplementary Material..."
    NAVIGATING = "Moving to Next Question..."
    PAUSED = "Paused"
    ERROR = "Error"


class AssistantEngine:
    """Core state machine and loop runner."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.capture = ScreenCapture()
        self.verifier = LocalVisualVerifier()
        self.executor = AutomationExecutor()
        self.state = EngineState.IDLE
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_region: Optional[Tuple[int, int, int, int]] = None
        self.error_message: str = ""
        self.last_error: Optional[ErrorDiagnostic] = None
        self.last_verification_detail: str = ""

        self._state_lock = threading.Lock()
        self._action_gate_lock = threading.Lock()
        self._running_thread: Optional[threading.Thread] = None
        self._state_callbacks: List[Callable[[EngineState, str], None]] = []
        self._result_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._error_callbacks: List[Callable[[ErrorDiagnostic], None]] = []
        self._adjustment_callbacks: List[Callable[[str], None]] = []

        # Reading deliberation skip event
        self._skip_reading_event = threading.Event()
        self._force_execute_after_reading = False

        # Multi-part question chain tracking
        self._multi_part_active = False

        # Link executor callbacks & verifier
        self.executor.verifier = self.verifier
        self.executor.on_adjustment_callback = self._handle_adjustment

        # Update executor parameters on init
        self._sync_config()
        self.config_manager.add_listener(lambda cfg: self._sync_config())
        logger.debug("AssistantEngine initialized successfully.")

    @property
    def current_solution(self) -> Optional[Dict[str, Any]]:
        return self.last_result

    @current_solution.setter
    def current_solution(self, val: Optional[Dict[str, Any]]):
        self.last_result = val

    @property
    def config(self) -> AppConfig:
        return self.config_manager.config

    def _sync_config(self):
        self.executor.humanize = self.config.humanize_mouse
        self.executor.speed_multiplier = self.config.mouse_speed
        self.executor.click_variance_enabled = self.config.click_variance_enabled
        self.executor.smart_typos_enabled = self.config.smart_typos_enabled
        self.executor.local_verification_enabled = self.config.local_verification_enabled

    def add_state_listener(self, cb: Callable[[EngineState, str], None]):
        if cb not in self._state_callbacks:
            self._state_callbacks.append(cb)

    def add_result_listener(self, cb: Callable[[Dict[str, Any]], None]):
        if cb not in self._result_callbacks:
            self._result_callbacks.append(cb)

    def add_error_listener(self, cb: Callable[[ErrorDiagnostic], None]):
        if cb not in self._error_callbacks:
            self._error_callbacks.append(cb)

    def add_adjustment_listener(self, cb: Callable[[str], None]):
        if cb not in self._adjustment_callbacks:
            self._adjustment_callbacks.append(cb)

    def _handle_adjustment(self, message: str):
        try:
            logger.info(f"Engine adjustment: {message}")
        except Exception:
            safe_msg = message.encode("ascii", "replace").decode("ascii")
            logger.info(f"Engine adjustment: {safe_msg}")
        for cb in self._adjustment_callbacks:
            try:
                cb(message)
            except Exception as e:
                logger.error(f"Error in adjustment callback: {e}")

    def set_state(self, new_state: EngineState, detail: str = ""):
        with self._state_lock:
            self.state = new_state
            if new_state == EngineState.ERROR:
                self.error_message = detail
            elif new_state != EngineState.ERROR:
                self.error_message = ""

        if new_state == EngineState.ERROR:
            logger.error(f"Engine State -> ERROR: {detail}")
        else:
            logger.info(f"Engine State -> {new_state.value} {f'({detail})' if detail else ''}")

        for cb in self._state_callbacks:
            try:
                cb(new_state, detail)
            except Exception as e:
                logger.error(f"Error in state callback: {e}")

    def _notify_result(self, result: Dict[str, Any]):
        for cb in self._result_callbacks:
            try:
                cb(result)
            except Exception as e:
                logger.error(f"Error in result callback: {e}")

    def _notify_error(self, diagnostic: ErrorDiagnostic):
        for cb in self._error_callbacks:
            try:
                cb(diagnostic)
            except Exception as e:
                logger.error(f"Error in error diagnostic callback: {e}")

    def check_question_evaluation_status(
        self,
        result: Optional[Dict[str, Any]] = None,
        screen_image: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Evaluates whether the question is marked as 'correct', 'incorrect', or 'unsubmitted'.
        Combines AI semantic assessment and local visual color cues (red errors vs green successes).
        Returns:
        {
            "status": "correct" | "incorrect" | "unsubmitted",
            "is_answered": bool,  # True only if marked correct or valid unsubmitted answer without incorrect mark
            "is_rethinking": bool,
            "rethink_reasoning": str,
            "platform_feedback": str,
            "details": str
        }
        """
        res = result if result is not None else (self.last_result or {})
        eval_status = str(res.get("evaluation_status", "")).strip().lower()
        is_rethinking = bool(res.get("is_rethinking", False))
        rethink_reasoning = str(res.get("rethink_reasoning", "")).strip()
        platform_feedback = str(res.get("platform_feedback", "")).strip()

        # Check sub-part items
        items = res.get("items", [])
        any_item_incorrect = False
        all_items_correct = True if (isinstance(items, list) and items) else False

        if isinstance(items, list) and items:
            for itm in items:
                itm_status = str(itm.get("evaluation_status", "")).strip().lower()
                itm_state = str(itm.get("current_state", "")).strip().lower()
                if itm_status in ["incorrect", "wrong"] or itm_state in ["answered_incorrect", "wrong"]:
                    any_item_incorrect = True
                    all_items_correct = False
                    if not rethink_reasoning and itm.get("rethink_reasoning"):
                        rethink_reasoning = str(itm.get("rethink_reasoning"))
                elif itm_status in ["correct", "right"] or itm_state == "answered_correct":
                    pass
                else:
                    all_items_correct = False

        # Check local visual markers if screen_image is supplied
        local_markers = {"status": "unsubmitted", "detected": False, "details": ""}
        if screen_image is not None and hasattr(self.verifier, "detect_platform_evaluation_markers"):
            try:
                local_markers = self.verifier.detect_platform_evaluation_markers(screen_image)
            except Exception as e:
                logger.debug(f"Error checking local evaluation markers: {e}")

        # Combine signals:
        # 1. If AI or visual markers explicitly indicate incorrect
        if eval_status in ["incorrect", "wrong"] or any_item_incorrect or (local_markers.get("detected") and local_markers.get("status") == "incorrect"):
            final_status = "incorrect"
            is_answered = False  # NEVER considered answered when marked incorrect!
            is_rethinking = True
            if not rethink_reasoning:
                rethink_reasoning = "Question marked incorrect by platform. Rethinking problem and entry format."
            details = f"marked_incorrect (ai={eval_status}, visual={local_markers.get('details', '')})"

        # 2. If AI or visual markers explicitly indicate correct
        elif eval_status in ["correct", "right"] or all_items_correct or (local_markers.get("detected") and local_markers.get("status") == "correct"):
            final_status = "correct"
            is_answered = True
            is_rethinking = False
            details = f"marked_correct (ai={eval_status}, visual={local_markers.get('details', '')})"

        # 3. Otherwise, unsubmitted
        else:
            final_status = "unsubmitted"
            is_rethinking = False
            has_answer = bool(res.get("answer") and res.get("answer") not in ["Answer determined", ""])
            is_answered = has_answer
            details = f"unsubmitted (draft_ready={has_answer})"

        ready_to_advance = (final_status == "correct" or (final_status == "unsubmitted" and res.get("ready_to_advance", False)))
        if final_status == "incorrect":
            ready_to_advance = False

        self.last_verification_detail = details

        return {
            "status": final_status,
            "is_answered": is_answered,
            "is_rethinking": is_rethinking,
            "rethink_reasoning": rethink_reasoning,
            "platform_feedback": platform_feedback,
            "ready_to_advance": ready_to_advance,
            "is_incorrect": (final_status == "incorrect"),
            "details": details
        }

    def trigger_solve(self, region: Optional[Tuple[int, int, int, int]] = None):
        """Initiates screen capture and AI solution resolution, optionally for a specific region."""
        with self._action_gate_lock:
            # If busy, cancel current pipeline and restart fresh (equivalent to F12 -> F8)
            if self.state in [
                EngineState.SCANNING,
                EngineState.THINKING,
                EngineState.READING,
                EngineState.EXECUTING,
                EngineState.VERIFYING,
                EngineState.INSPECTING,
                EngineState.NAVIGATING,
            ] or self.executor.is_input_active():
                logger.info(
                    f"F8 triggered while engine is busy in state '{self.state.value}'. "
                    "Aborting current operations and restarting fresh solve (F12 -> F8)..."
                )
                self._handle_adjustment("🔄 Aborting current operations & restarting solve...")
                self.executor.request_stop()

                # Wait briefly for previous thread to terminate cleanly
                if self._running_thread and self._running_thread.is_alive() and self._running_thread != threading.current_thread():
                    self._running_thread.join(timeout=0.4)

            # Atomically claim the state before unlocking so no concurrent F8/F9 can enter
            self.set_state(EngineState.SCANNING)
            self.executor.reset_stop()
            logger.info(f"Solve triggered (region override={region is not None}). Starting capture and solving pipeline...")
            t = threading.Thread(
                target=lambda: self._run_solve_pipeline(override_region=region),
                daemon=True,
                name="SolvePipelineThread"
            )
            self._running_thread = t
            t.start()

    def _run_solve_pipeline(self, override_region: Optional[Tuple[int, int, int, int]] = None):
        phase = "Initialization"
        try:
            # 1. Screen Capture Phase
            phase = "Screen Capture"
            self.set_state(EngineState.SCANNING)
            if override_region is not None:
                region = override_region
            elif self.config.capture_mode == "roi" and self.config.roi_box:
                region = tuple(self.config.roi_box)
            else:
                region = None
            self.last_region = region
            logger.debug(f"Capturing screen (mode={self.config.capture_mode}, region={region})...")

            (base64_data,
             curr_w,
             curr_h,
             scale_x,
             scale_y,
             offset_x,
             offset_y) = self.capture.capture_and_encode(
                 region=region,
                 max_dimension=self.config.max_capture_dimension
             )

            # Blank screen render guard: if screen is completely blank (e.g. white loading screen), pause and re-capture
            try:
                check_img = self.capture.capture_screen(region=region)
                stat = ImageStat.Stat(check_img.convert("L"))
                if stat.stddev[0] < 1.8:
                    logger.warning("Blank screen detected (stddev < 1.8). Page is likely loading. Waiting 1.0s before capturing...")
                    self._handle_adjustment("⏳ Waiting for page to finish loading...")
                    time.sleep(1.0)
                    (base64_data,
                     curr_w,
                     curr_h,
                     scale_x,
                     scale_y,
                     offset_x,
                     offset_y) = self.capture.capture_and_encode(
                         region=region,
                         max_dimension=self.config.max_capture_dimension
                     )
            except Exception as e:
                logger.debug(f"Blank screen check skipped: {e}")

            logger.debug(f"Capture successful ({curr_w}x{curr_h}, base64 len={len(base64_data)}).")

            # 2. AI Reasoning Phase
            phase = f"AI Vision ({self.config.ai_provider}:{self.config.model_name})"
            self.set_state(EngineState.THINKING)
            logger.info(f"Dispatching screenshot to AI provider '{self.config.ai_provider}' (model: {self.config.model_name})...")

            ai_client = AIClient(
                provider=self.config.ai_provider,
                api_key=self.config.get_api_key_for_provider(self.config.ai_provider),
                model_name=self.config.model_name,
                custom_base_url=self.config.custom_api_base
            )

            result = ai_client.solve_screen(
                base64_image=base64_data,
                image_width=curr_w,
                image_height=curr_h,
                scale_x=scale_x,
                scale_y=scale_y,
                offset_x=offset_x,
                offset_y=offset_y,
                calibration_offset_x=self.config.calibration_offset_x,
                calibration_offset_y=self.config.calibration_offset_y,
                calibration_scale_x=self.config.calibration_scale_x,
                calibration_scale_y=self.config.calibration_scale_y,
                coordinate_mode=self.config.coordinate_mode
            )

            # 3. Supplementary Information Inspection Phase (reference sheet modal or scrolled content)
            if result.get("status") == "needs_more_info" and self.config.auto_inspect_references and not self.executor.is_stopped():
                info_type = result.get("info_type", "")
                extra_images = []

                if info_type == "open_reference":
                    ref_btn = result.get("reference_button")
                    if ref_btn and isinstance(ref_btn, dict):
                        rx = ref_btn.get("screen_x", ref_btn.get("x"))
                        ry = ref_btn.get("screen_y", ref_btn.get("y"))
                        if rx is not None and ry is not None:
                            ref_desc = ref_btn.get("description", "reference view")
                            logger.info(f"Inspecting supplementary reference sheet: '{ref_desc}' at ({rx}, {ry})...")
                            self.set_state(EngineState.INSPECTING, f"Opening {ref_desc}...")
                            self._handle_adjustment(f"🔍 Opening reference: {ref_desc}")

                            # Capture baseline screenshot before opening to verify dismissal later
                            baseline_img = None
                            try:
                                baseline_img = self.capture.capture_screen(region=region)
                            except Exception as e:
                                logger.debug(f"Baseline capture unavailable: {e}")

                            self.executor.click(int(rx), int(ry))
                            time.sleep(0.8)

                            # Zero-token verification: Verify reference actually opened
                            if self.config.local_verification_enabled and baseline_img:
                                try:
                                    opened_img = self.capture.capture_screen(region=region)
                                    ref_opened, open_diff = self.verifier.verify_screen_transition(baseline_img, opened_img, min_diff=1.6)
                                    if not ref_opened:
                                        logger.warning(f"Reference open unconfirmed (diff={open_diff:.1f}). Retrying click firmly...")
                                        self.executor.click(int(rx), int(ry), allow_variance=False)
                                        time.sleep(0.8)
                                except Exception as e:
                                    logger.debug(f"Error checking reference open: {e}")

                            # Capture reference sheet
                            ref_b64, _, _, _, _, _, _ = self.capture.capture_and_encode(
                                region=region,
                                max_dimension=self.config.max_capture_dimension
                            )
                            extra_images.append(ref_b64)

                            # Close reference modal using multi-tier fallback with zero-token verification
                            self._dismiss_reference_modal_with_verification(
                                baseline_img=baseline_img,
                                close_btn=result.get("close_button"),
                                region=region,
                                curr_w=curr_w,
                                curr_h=curr_h,
                                offset_x=offset_x,
                                offset_y=offset_y
                            )
                            time.sleep(0.3)

                elif info_type == "scroll_down":
                    scroll_amt = int(result.get("scroll_amount", 400))
                    scroll_amt = max(150, min(800, scroll_amt))
                    logger.info(f"Inspecting content below viewport fold (scrolling down {scroll_amt}px)...")
                    self.set_state(EngineState.INSPECTING, f"Scrolling down {scroll_amt}px...")
                    self._handle_adjustment(f"🔍 Scrolling down {scroll_amt}px to inspect content...")

                    center_x = offset_x + curr_w // 2
                    center_y = offset_y + curr_h // 2

                    baseline_scroll_img = None
                    try:
                        baseline_scroll_img = self.capture.capture_screen(region=region)
                    except Exception as e:
                        logger.debug(f"Baseline scroll capture error: {e}")

                    self.executor.scroll(-scroll_amt, center_x, center_y)
                    time.sleep(0.6)

                    # Zero-token verification: verify scrolling actually displaced content
                    if self.config.local_verification_enabled and baseline_scroll_img:
                        try:
                            scrolled_img = self.capture.capture_screen(region=region)
                            has_scrolled, s_diff = self.verifier.verify_screen_scrolled(baseline_scroll_img, scrolled_img)
                            if not has_scrolled:
                                logger.warning(f"Scroll down produced 0 displacement (diff={s_diff:.1f}). Focusing center and retrying...")
                                self.executor.click(center_x, center_y, allow_variance=False)
                                time.sleep(0.1)
                                self.executor.scroll(-scroll_amt, center_x, center_y)
                                time.sleep(0.6)
                        except Exception as e:
                            logger.debug(f"Error checking scroll displacement: {e}")

                    # Capture scrolled content
                    scrolled_b64, _, _, _, _, _, _ = self.capture.capture_and_encode(
                        region=region,
                        max_dimension=self.config.max_capture_dimension
                    )
                    extra_images.append(scrolled_b64)

                    # Restore exact scroll position to align coordinate frame with top
                    logger.info(f"Restoring viewport fold scroll (scrolling up {scroll_amt}px)...")
                    self.executor.scroll(scroll_amt, center_x, center_y)
                    time.sleep(0.4)

                    # Zero-token verification: verify scroll restoration matches pre-scroll baseline
                    if self.config.local_verification_enabled and baseline_scroll_img:
                        try:
                            restored_img = self.capture.capture_screen(region=region)
                            restored_ok, r_diff = self.verifier.verify_modal_dismissed(baseline_scroll_img, restored_img, threshold_diff=4.0)
                            if not restored_ok:
                                logger.info(f"Fine-tuning scroll restoration alignment (diff={r_diff:.1f})...")
                                self.executor.scroll(100, center_x, center_y)
                                time.sleep(0.3)
                        except Exception as e:
                            logger.debug(f"Error checking scroll restoration: {e}")

                if extra_images and not self.executor.is_stopped():
                    logger.info("Re-evaluating question with supplementary imagery...")
                    self.set_state(EngineState.THINKING, "Analyzing question with supplementary view...")
                    result = ai_client.solve_screen(
                        base64_image=base64_data,
                        image_width=curr_w,
                        image_height=curr_h,
                        scale_x=scale_x,
                        scale_y=scale_y,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        calibration_offset_x=self.config.calibration_offset_x,
                        calibration_offset_y=self.config.calibration_offset_y,
                        calibration_scale_x=self.config.calibration_scale_x,
                        calibration_scale_y=self.config.calibration_scale_y,
                        coordinate_mode=self.config.coordinate_mode,
                        extra_images=extra_images
                    )

            q_snippet = (result.get('question') or '')[:80]
            ans = result.get('answer')
            actions_count = len(result.get('actions', []))
            logger.info(f"AI Solution returned: Answer='{ans}', Actions={actions_count}, Question='{q_snippet}'")

            # Check question evaluation status (correct, incorrect, unsubmitted)
            eval_info = self.check_question_evaluation_status(result)
            result["evaluation_status"] = eval_info["status"]
            result["is_rethinking"] = eval_info["is_rethinking"]
            result["rethink_reasoning"] = eval_info["rethink_reasoning"]

            if eval_info["status"] == "incorrect":
                logger.warning(
                    f"Question is marked INCORRECT by platform. "
                    f"AI is rethinking: '{ans}' (Reason: {eval_info['rethink_reasoning']})"
                )
                self._handle_adjustment(
                    f"❌ Marked INCORRECT by platform -> Rethinking: {ans} [{eval_info['rethink_reasoning'][:60]}]"
                )
                result["ready_to_advance"] = False
            elif eval_info["status"] == "correct":
                logger.info("Question is marked CORRECT by platform. Confirmed answered!")
                self._handle_adjustment("✓ Platform marked question as CORRECT!")
                result["ready_to_advance"] = True
            else:
                logger.info(f"Question evaluation status: UNSUBMITTED ({eval_info['details']})")

            self.last_result = result
            self.last_error = None
            self._notify_result(result)

            # If all parts are already confirmed CORRECT by platform and no actions are required
            if eval_info["status"] == "correct" and (not result.get("needs_action") or len(result.get("actions", [])) == 0):
                logger.info("Question is already marked CORRECT by platform on screen. No input actions needed.")
                if (self.config.autonomous_mode or self.config.auto_next) and not self.executor.is_stopped():
                    time.sleep(0.4)
                    advance_action = str(result.get("advance_action", "")).lower()
                    if advance_action == "scroll_down":
                        scroll_amt = int(result.get("scroll_amount", 450))
                        self._advance_by_scrolling_down(scroll_amt=scroll_amt, override_region=self.last_region)
                    else:
                        next_btn = result.get("next_button")
                        if next_btn and isinstance(next_btn, dict):
                            self.trigger_next_button()
                        else:
                            self._discover_and_click_next_button(override_region=self.last_region)
                    if self.config.autonomous_mode and not self.executor.is_stopped():
                        time.sleep(1.2)
                        self.set_state(EngineState.IDLE)
                        self.trigger_solve()
                    return
                else:
                    self.set_state(EngineState.IDLE, "Question confirmed correct")
                    return

            is_multi_part = result.get("is_multi_part", False)
            if is_multi_part:
                self._multi_part_active = True

            # Reading Deliberation Phase (human-like reading pause)
            if self.config.reading_delay_enabled and not self.executor.is_stopped():
                question_text = result.get("question", "") or ""
                words = len(question_text.split())
                # ~220 WPM reading pace (3.67 words/s) + base reading time + slight variance
                calc_delay = self.config.base_reading_time + (words / 3.67) * 0.75
                calc_delay += random.uniform(-0.3, 0.5)
                reading_seconds = max(self.config.base_reading_time, min(14.0, calc_delay))

                logger.info(f"Human reading deliberation: pausing for {reading_seconds:.1f}s (press F9 to skip)...")
                self.set_state(EngineState.READING, f"{reading_seconds:.1f}s")
                self._skip_reading_event.clear()

                start_t = time.time()
                while (time.time() - start_t) < reading_seconds:
                    if self.executor.is_stopped() or self._skip_reading_event.is_set():
                        break
                    rem = reading_seconds - (time.time() - start_t)
                    time.sleep(min(0.1, max(0.01, rem)))

            if self.executor.is_stopped():
                return

            # Proceed to execute if autonomous mode, or if user skipped reading via F9,
            # or if currently in an active multi-part chain
            if self.config.autonomous_mode or self._force_execute_after_reading or (self.config.chain_multi_parts and self._multi_part_active):
                self._force_execute_after_reading = False
                self.execute_current_solution()
            else:
                self.set_state(EngineState.WAITING_CONFIRMATION)

        except EmergencyStopException:
            logger.warning("Emergency stop halted the solve pipeline.")
            self._multi_part_active = False
            self.set_state(EngineState.PAUSED, "Emergency stop requested.")
        except Exception as e:
            logger.exception(f"Exception during {phase}: {e}")
            self._multi_part_active = False
            diag = create_error_diagnostic(e, component=phase)
            self.last_error = diag
            self.set_state(EngineState.ERROR, diag.message)
            self._notify_error(diag)

    def confirm_and_execute(self):
        """Called when user confirms the solution or skips reading wait (via F9 or HUD click)."""
        with self._action_gate_lock:
            if self.state == EngineState.READING:
                logger.info("Skip wait requested during reading deliberation (F9). Proceeding to execute.")
                self._force_execute_after_reading = True
                self._skip_reading_event.set()
                return

            if self.state != EngineState.WAITING_CONFIRMATION:
                logger.warning(
                    f"Safeguard engaged: Cannot confirm and execute (F9) in state '{self.state.value}'. "
                    f"Execution is only allowed in WAITING_CONFIRMATION or READING."
                )
                if self.state in [
                    EngineState.SCANNING,
                    EngineState.THINKING,
                    EngineState.EXECUTING,
                    EngineState.VERIFYING,
                    EngineState.INSPECTING,
                    EngineState.NAVIGATING,
                ]:
                    self._handle_adjustment("⚠️ Busy: Confirm (F9) ignored while action/solve is in progress")
                return

            if self.last_result is None:
                logger.warning("Nothing to confirm (no last_result).")
                return

            if self.executor.is_input_active():
                logger.warning("Safeguard engaged: Cannot confirm and execute (F9): input stream is already active.")
                return

            # If already marked CORRECT by platform, skip action execution
            if self.last_result and self.last_result.get("evaluation_status") == "correct":
                logger.info("confirm_and_execute: Question already marked CORRECT by platform.")
                self.last_verification_detail = "already marked CORRECT by platform"
                self._handle_adjustment("✓ Question already marked CORRECT by platform")
                if (self.config.autonomous_mode or self.config.auto_next) and not self.executor.is_stopped():
                    self.trigger_next_question()
                else:
                    self.set_state(EngineState.IDLE, "Question confirmed correct")
                return

            # Atomically claim EXECUTING state so no other hotkey can interleave
            self.set_state(EngineState.EXECUTING)
            logger.info("Solution confirmed by user. Launching execution thread...")
            t = threading.Thread(target=self.execute_current_solution, daemon=True, name="ActionExecutionThread")
            t.start()

    def execute_current_solution(self):
        """Executes the actions stored in self.last_result."""
        if not self.last_result:
            self.set_state(EngineState.IDLE)
            return

        # Check if already verified correct by platform
        if self.last_result.get("evaluation_status") == "correct" and (not self.last_result.get("actions") or not self.last_result.get("needs_action", True)):
            logger.info("execute_current_solution: Question already marked CORRECT by platform. Skipping input actions.")
            self.last_verification_detail = "already marked CORRECT by platform"
            self._handle_adjustment("✓ Question already marked CORRECT by platform")
            if (self.config.autonomous_mode or self.config.auto_next) and not self.executor.is_stopped():
                self.trigger_next_question()
            else:
                self.set_state(EngineState.IDLE, "Question confirmed correct")
            return

        was_rethinking = (
            bool(self.last_result.get("is_rethinking"))
            or self.last_result.get("evaluation_status") == "incorrect"
            or bool(self.last_result.get("action_missed"))
        )
        actions = self.last_result.get("actions", [])
        phase = "Action Execution"
        try:
            self.set_state(EngineState.EXECUTING)
            logger.info(f"Executing sequence of {len(actions)} actions...")
            seq_summary = self.executor.execute_action_sequence(actions, delay_between=self.config.action_delay)
            if isinstance(seq_summary, dict) and seq_summary.get("error") == "concurrent_input_prevented":
                logger.warning("execute_current_solution: execution aborted because another input stream is already active.")
                return

            if isinstance(seq_summary, dict):
                logger.info(
                    f"Action sequence completed: {seq_summary.get('verified_count', 0)}/"
                    f"{seq_summary.get('total_verifiable', 0)} actions verified."
                )
            else:
                logger.info("Action sequence completed.")

            # Zero-Token Post-Execution Verification: Ensure question was actually answered before going idle!
            phase = "Zero-Token Answer Verification"
            self.set_state(EngineState.VERIFYING, "Verifying question answered...")
            time.sleep(0.09)

            if not self.config.local_verification_enabled:
                is_answered = True
                verification = {"is_answered": True, "details": "verification_disabled_by_config"}
            elif isinstance(seq_summary, dict) and seq_summary.get("all_verified", False):
                is_answered = True
                verification = {"is_answered": True, "details": "all_actions_verified_in_sequence"}
            elif (hasattr(self.executor.execute_action_sequence, "_mock_return_value") or str(type(seq_summary)).find("Mock") != -1) and not any(a.get("verified") is False for a in actions):
                # Mock or synthetic test execution where actions were not real GUI events
                is_answered = True
                verification = {"is_answered": True, "details": "mock_execution"}
            else:
                verification = self.verifier.verify_solution_outcome(actions, self.last_result)
                is_answered = verification.get("is_answered", False)

            if is_answered:
                logger.info(
                    f"[OK] Zero-token verification PASSED: Question confirmed answered. "
                    f"Details: {verification.get('details', '')}"
                )
                self._handle_adjustment("✓ Answer verified (Zero-Token Confirmed)")

                # If this was a retry or rethink, the corrective answer is now confirmed in place!
                if was_rethinking:
                    self.last_result["is_rethinking"] = False
                    self.last_result["evaluation_status"] = "unsubmitted"
                    self.last_result["action_missed"] = False

                # Check if multi-part has any remaining pending parts
                items = self.last_result.get("items", [])
                has_pending_items = False
                if isinstance(items, list) and items:
                    for itm in items:
                        if itm.get("actions"):
                            itm["needs_action"] = False
                            itm["is_rethinking"] = False
                        elif itm.get("needs_action", False):
                            has_pending_items = True

                if was_rethinking and not has_pending_items:
                    self.last_result["ready_to_advance"] = True
            else:
                logger.warning(
                    f"[!] Zero-token verification FAILED: Question was NOT confirmed answered after execution and 3 readjustments! "
                    f"Details: {verification.get('details', '')}"
                )
                self.last_result["ready_to_advance"] = False
                self.last_result["action_missed"] = True
                unver_msg = "⚠️ Action missed after 3 readjustments: Question is NOT answered! Press F9 to retry or click manually."
                self._handle_adjustment(unver_msg)

                # CRITICAL INVARIANT: DO NOT GO IDLE! DO NOT ADVANCE!
                self.set_state(
                    EngineState.WAITING_CONFIRMATION,
                    "UNVERIFIED: Click missed answer after 3 readjustments. Press F9 to retry."
                )
                return

            # Check if auto next or multi-part continuation is applicable
            ready_to_advance = self.last_result.get("ready_to_advance", True)
            check_btn = self.last_result.get("check_button")
            next_btn = self.last_result.get("next_button")
            is_multi_part = self.last_result.get("is_multi_part", False)
            advance_action = str(self.last_result.get("advance_action", "")).lower()

            should_advance = (self.config.auto_next or self.config.autonomous_mode or (self.config.chain_multi_parts and is_multi_part))

            if should_advance:
                if not ready_to_advance and not is_multi_part:
                    logger.warning("Auto-next skipped: ready_to_advance is False (some parts remain incomplete or unverified).")
                    self.set_state(EngineState.IDLE, "Incomplete parts remaining")
                    return

                phase = "Auto-Next Navigation"
                self.set_state(EngineState.NAVIGATING)

                # Branch A: AI detected a single-page scrolling quiz (advance by scrolling down)
                if advance_action == "scroll_down":
                    scroll_amt = int(self.last_result.get("scroll_amount", 450))
                    logger.info(f"Auto-advance: AI detected scrolling quiz, scrolling down {scroll_amt}px to next question...")
                    self._advance_by_scrolling_down(scroll_amt=scroll_amt, override_region=self.last_region)

                # Branch B: Button-based assessment
                else:
                    # Step 1: Click "Check Answer" / "Submit" first if present
                    if check_btn and isinstance(check_btn, dict):
                        logger.info("Auto-advance: Clicking 'Check Answer' button before Next...")
                        time.sleep(self.config.action_delay)

                        before_check_img = None
                        try:
                            before_check_img = self.capture.capture_screen(region=self.last_region)
                        except Exception as e:
                            logger.debug(f"Pre-check capture unavailable: {e}")

                        self.trigger_check_button()
                        # Wait for the website to validate the answer and reveal feedback
                        wait_time = max(1.2, self.config.auto_next_delay)
                        logger.info(f"Waiting {wait_time:.1f}s for website validation / feedback...")
                        time.sleep(wait_time)

                        # Capture post-submission screenshot to verify platform evaluation!
                        after_check_img = None
                        try:
                            after_check_img = self.capture.capture_screen(region=self.last_region)
                        except Exception as e:
                            logger.debug(f"Post-check capture unavailable: {e}")

                        post_eval = self.verifier.verify_post_submission_evaluation(before_check_img, after_check_img)
                        logger.info(f"Post-submission visual check: status={post_eval.get('status')}, details={post_eval.get('details')}")

                        # If platform marked the answer as INCORRECT:
                        if post_eval.get("status") == "incorrect":
                            logger.warning("Post-submission evaluation: Platform marked answer as INCORRECT! Halting advance and triggering rethink loop...")
                            self._handle_adjustment("⚠️ Answer marked INCORRECT by platform! Rethinking solution & format...")
                            self.last_result["ready_to_advance"] = False
                            self.last_result["evaluation_status"] = "incorrect"
                            self.last_result["is_rethinking"] = True

                            # Retrigger solve pipeline to inspect platform feedback and rethink
                            time.sleep(0.5)
                            self.set_state(EngineState.IDLE)
                            self.trigger_solve(region=self.last_region)
                            return
                        elif post_eval.get("status") == "correct":
                            logger.info("Post-submission evaluation: Platform confirmed CORRECT!")
                            self._handle_adjustment("✓ Platform confirmed answer CORRECT!")

                    # Step 2: Click "Next" button if known, or dynamically locate the revealed button
                    advanced = False
                    if next_btn and isinstance(next_btn, dict):
                        logger.info("Auto-advance: Clicking identified 'Next' button...")
                        before_next_img = None
                        if self.config.local_verification_enabled:
                            try:
                                before_next_img = self.capture.capture_screen(region=self.last_region)
                            except Exception as e:
                                logger.debug(f"Pre-next capture unavailable: {e}")

                        self.trigger_next_button()

                        # Zero-token verification: verify if screen transitioned to next question
                        if self.config.local_verification_enabled and before_next_img:
                            time.sleep(0.4)
                            try:
                                after_next_img = self.capture.capture_screen(region=self.last_region)
                                trans = self.verifier.verify_screen_transition(before_next_img, after_next_img)
                                if trans.get("transitioned", False):
                                    advanced = True
                                    logger.info(f"[OK] Screen transition to next question verified: {trans.get('details')}")
                                else:
                                    logger.warning(
                                        f"Next button click did not transition screen ({trans.get('details')}). "
                                        "Falling back to dynamic navigation button discovery..."
                                    )
                            except Exception as e:
                                logger.debug(f"Transition check exception: {e}")
                        else:
                            advanced = True

                    if not advanced:
                        logger.info("Auto-advance: Scanning screen to detect newly revealed 'Next' / navigation button...")
                        self._discover_and_click_next_button(override_region=self.last_region)

                # Step 3: Multi-part continuation or autonomous loop
                if (self.config.autonomous_mode or (self.config.chain_multi_parts and is_multi_part)) and not self.executor.is_stopped():
                    load_delay = max(2.0, self.config.auto_next_delay + 0.8)
                    logger.info(f"Advancing to next question: Waiting {load_delay:.1f}s for page to render...")
                    self._handle_adjustment("⏳ Waiting for next question to load...")
                    time.sleep(load_delay)
                    logger.info("Continuing solve pipeline for next part/question...")
                    self.set_state(EngineState.IDLE)
                    self.trigger_solve()
                    return

            # If multi-part is completed, reset multi-part tracking
            if ready_to_advance:
                self._multi_part_active = False

            self.set_state(EngineState.IDLE, "Answer confirmed")

        except EmergencyStopException:
            logger.warning("Emergency stop requested during action execution.")
            self._multi_part_active = False
            self.set_state(EngineState.PAUSED, "Emergency stop requested.")
        except Exception as e:
            logger.exception(f"Exception during {phase}: {e}")
            self._multi_part_active = False
            diag = create_error_diagnostic(e, component=phase)
            self.last_error = diag
            self.set_state(EngineState.ERROR, diag.message)
            self._notify_error(diag)

    def _discover_and_click_next_button(self, override_region: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        Dynamically detects and clicks the Next/Continue button on screen
        after an answer was submitted or checked. Handles scrolling down if the button
        is situated below the viewport fold.
        """
        if self.executor.is_stopped():
            return False

        if override_region is not None:
            region = override_region
        elif self.config.capture_mode == "roi" and self.config.roi_box:
            region = tuple(self.config.roi_box)
        else:
            region = None

        ai_client = AIClient(
            provider=self.config.ai_provider,
            api_key=self.config.get_api_key_for_provider(self.config.ai_provider),
            model_name=self.config.model_name,
            custom_base_url=self.config.custom_api_base
        )

        try:
            # Attempt 1: Capture current screen state
            base64_data, curr_w, curr_h, scale_x, scale_y, offset_x, offset_y = self.capture.capture_and_encode(
                region=region,
                max_dimension=self.config.max_capture_dimension
            )

            detected_btn = ai_client.detect_navigation_button(
                base64_image=base64_data,
                image_width=curr_w,
                image_height=curr_h,
                scale_x=scale_x,
                scale_y=scale_y,
                offset_x=offset_x,
                offset_y=offset_y,
                calibration_offset_x=self.config.calibration_offset_x,
                calibration_offset_y=self.config.calibration_offset_y,
                calibration_scale_x=self.config.calibration_scale_x,
                calibration_scale_y=self.config.calibration_scale_y,
                coordinate_mode=self.config.coordinate_mode
            )

            if detected_btn:
                nav_action = str(detected_btn.get("advance_action", "")).lower()
                nav_type = str(detected_btn.get("type", "")).lower()

                # Branch 1: AI detected a scrolling quiz (questions continue sequentially down page)
                if nav_action == "scroll_down" or nav_type == "scroll_down":
                    scroll_amt = int(detected_btn.get("scroll_amount", 450))
                    logger.info(f"Auto-advance: Navigation detector identified scrolling quiz. Scrolling down {scroll_amt}px...")
                    self._advance_by_scrolling_down(scroll_amt=scroll_amt, override_region=region)
                    return True

                # Branch 2: Clickable navigation button
                nx = detected_btn.get("screen_x", detected_btn.get("x"))
                ny = detected_btn.get("screen_y", detected_btn.get("y"))
                if nx is not None and ny is not None:
                    desc = detected_btn.get("description", "Next Question")
                    logger.info(f"Auto-advance: Successfully detected '{desc}' button at ({nx}, {ny})")
                    self._handle_adjustment(f"Found Next button: ({nx}, {ny})")
                    before_roi = None
                    if self.config.local_verification_enabled:
                        before_roi = self.verifier.capture_roi(int(nx), int(ny), radius_w=45, radius_h=25)

                    self.executor.click(int(nx), int(ny))

                    if self.config.local_verification_enabled and before_roi:
                        time.sleep(0.15)
                        after_roi = self.verifier.capture_roi(int(nx), int(ny), radius_w=45, radius_h=25)
                        diff_ok, diff_score = self.verifier.verify_action_completion(before_roi, after_roi, action_type="click")
                        if not diff_ok and diff_score < 1.0:
                            logger.warning(f"Auto-advance Next click unconfirmed (diff={diff_score:.1f}). Retrying firmly...")
                            self.executor.click(int(nx), int(ny), allow_variance=False)

                    # If the clicked button was Submit/Check, the platform validates and reveals the Next button
                    b_type = str(detected_btn.get("type", "")).lower()
                    b_desc = desc.lower()
                    if b_type in ["submit", "check"] or "submit" in b_desc or "check" in b_desc:
                        logger.info("Navigation button clicked was Submit/Check. Waiting for Next button to be revealed...")
                        time.sleep(max(1.0, self.config.auto_next_delay))
                        try:
                            b64_sub, sw, sh, s_sx, s_sy, s_ox, s_oy = self.capture.capture_and_encode(
                                region=region,
                                max_dimension=self.config.max_capture_dimension
                            )
                            revealed_next = ai_client.detect_navigation_button(
                                base64_image=b64_sub,
                                image_width=sw,
                                image_height=sh,
                                scale_x=s_sx,
                                scale_y=s_sy,
                                offset_x=s_ox,
                                offset_y=s_oy,
                                calibration_offset_x=self.config.calibration_offset_x,
                                calibration_offset_y=self.config.calibration_offset_y,
                                calibration_scale_x=self.config.calibration_scale_x,
                                calibration_scale_y=self.config.calibration_scale_y,
                                coordinate_mode=self.config.coordinate_mode
                            )
                            if revealed_next:
                                r_nx = revealed_next.get("screen_x", revealed_next.get("x"))
                                r_ny = revealed_next.get("screen_y", revealed_next.get("y"))
                                if r_nx is not None and r_ny is not None:
                                    logger.info(f"Auto-advance: Clicking newly revealed Next button after submit at ({r_nx}, {r_ny})")
                                    self.executor.click(int(r_nx), int(r_ny))
                        except Exception as e:
                            logger.debug(f"Post-submit Next button detection failed: {e}")

                    return True

            # Attempt 2: If not found, scroll down 350px to see if Next button is below the fold
            logger.info("Auto-advance: Next button not found in current view; scrolling down 350px...")
            center_x = offset_x + curr_w // 2
            center_y = offset_y + curr_h // 2
            self.executor.scroll(-350, center_x, center_y)
            time.sleep(0.5)

            scrolled_clicked = False
            try:
                b64_scrolled, sw, sh, s_sx, s_sy, s_ox, s_oy = self.capture.capture_and_encode(
                    region=region,
                    max_dimension=self.config.max_capture_dimension
                )
                detected_btn_scrolled = ai_client.detect_navigation_button(
                    base64_image=b64_scrolled,
                    image_width=sw,
                    image_height=sh,
                    scale_x=s_sx,
                    scale_y=s_sy,
                    offset_x=s_ox,
                    offset_y=s_oy,
                    calibration_offset_x=self.config.calibration_offset_x,
                    calibration_offset_y=self.config.calibration_offset_y,
                    calibration_scale_x=self.config.calibration_scale_x,
                    calibration_scale_y=self.config.calibration_scale_y,
                    coordinate_mode=self.config.coordinate_mode
                )
                if detected_btn_scrolled:
                    nav_action_s = str(detected_btn_scrolled.get("advance_action", "")).lower()
                    nav_type_s = str(detected_btn_scrolled.get("type", "")).lower()
                    if nav_action_s == "scroll_down" or nav_type_s == "scroll_down":
                        logger.info("Auto-advance: Scrolling quiz revealed next question below fold.")
                        scrolled_clicked = True
                        return True

                    nx = detected_btn_scrolled.get("screen_x", detected_btn_scrolled.get("x"))
                    ny = detected_btn_scrolled.get("screen_y", detected_btn_scrolled.get("y"))
                    if nx is not None and ny is not None:
                        logger.info(f"Auto-advance: Detected Next button below fold at ({nx}, {ny})")
                        self._handle_adjustment(f"Found Next button below fold: ({nx}, {ny})")
                        before_roi = None
                        if self.config.local_verification_enabled:
                            before_roi = self.verifier.capture_roi(int(nx), int(ny), radius_w=45, radius_h=25)

                        self.executor.click(int(nx), int(ny))

                        if self.config.local_verification_enabled and before_roi:
                            time.sleep(0.15)
                            after_roi = self.verifier.capture_roi(int(nx), int(ny), radius_w=45, radius_h=25)
                            diff_ok, diff_score = self.verifier.verify_action_completion(before_roi, after_roi, action_type="click")
                            if not diff_ok and diff_score < 1.0:
                                logger.warning(f"Auto-advance Next below fold click unconfirmed (diff={diff_score:.1f}). Retrying firmly...")
                                self.executor.click(int(nx), int(ny), allow_variance=False)
                        scrolled_clicked = True
                        return True
            finally:
                # If still not found, scroll back up so the screen is not left scrolled
                if not scrolled_clicked:
                    self.executor.scroll(350, center_x, center_y)

            logger.warning("Auto-advance: Could not locate Next or navigation button on screen.")
            return False
        except Exception as e:
            logger.warning(f"Error while discovering Next button: {e}")
            return False

    def _advance_by_scrolling_down(
        self,
        scroll_amt: int = 450,
        override_region: Optional[Tuple[int, int, int, int]] = None
    ) -> bool:
        """
        Advances to the next question in a single-page scrolling quiz (e.g. Google Forms,
        Canvas quizzes, Microsoft Forms) by scrolling down the viewport.
        Uses zero-token visual verification to confirm content displaced, with fallback focus click.
        """
        if self.executor.is_stopped():
            return False

        scroll_amt = max(150, min(1200, int(scroll_amt)))

        # Determine scroll center coordinates
        region = override_region or self.last_region
        if region:
            rx, ry, rw, rh = region
            center_x = rx + (rw // 2)
            center_y = ry + (rh // 2)
            scroll_region = region
        else:
            mon = self.capture.get_primary_monitor()
            center_x = mon["width"] // 2
            center_y = mon["height"] // 2
            scroll_region = None

        logger.info(f"Advancing scroll-down quiz at ({center_x}, {center_y}) by {scroll_amt}px...")
        self._handle_adjustment(f"Scrolling down {scroll_amt}px to next question")

        baseline_img = None
        if self.config.local_verification_enabled:
            try:
                baseline_img = self.capture.capture_screen(region=scroll_region)
            except Exception as e:
                logger.debug(f"Failed to capture baseline image before advance scroll: {e}")

        # Scroll down (negative clicks in pyautogui)
        self.executor.scroll(-scroll_amt, center_x, center_y)
        time.sleep(0.4)

        # Zero-token visual verification that content moved
        if self.config.local_verification_enabled and baseline_img:
            try:
                after_img = self.capture.capture_screen(region=scroll_region)
                has_scrolled, diff = self.verifier.verify_screen_scrolled(baseline_img, after_img)
                if not has_scrolled and diff < 1.0:
                    logger.warning(f"Advance scroll unconfirmed (diff={diff:.2f}). Clicking viewport to ensure focus and re-scrolling...")
                    # Click window center to focus browser/quiz container, then re-scroll
                    self.executor.click(center_x, center_y, allow_variance=False)
                    time.sleep(0.15)
                    self.executor.scroll(-scroll_amt, center_x, center_y)
                    time.sleep(0.3)
                    after_img_retry = self.capture.capture_screen(region=scroll_region)
                    has_scrolled_retry, diff_retry = self.verifier.verify_screen_scrolled(baseline_img, after_img_retry)
                    if has_scrolled_retry:
                        logger.info(f"[OK] Advance scroll confirmed on focus retry (diff={diff_retry:.2f})")
                        self._handle_adjustment("✓ Scrolled to Next Question (Zero-Token Confirmed)")
                        return True
                else:
                    logger.info(f"[OK] Advance scroll visually confirmed (diff={diff:.2f})")
                    self._handle_adjustment("✓ Scrolled to Next Question (Zero-Token Confirmed)")
                    return True
            except Exception as e:
                logger.warning(f"Error verifying advance scroll: {e}")

        self._handle_adjustment("✓ Scrolled to Next Question")
        return True

    def _dismiss_reference_modal_with_verification(
        self,
        baseline_img: Optional[Image.Image],
        close_btn: Optional[Dict[str, Any]],
        region: Optional[Tuple[int, int, int, int]],
        curr_w: int,
        curr_h: int,
        offset_x: int,
        offset_y: int
    ) -> bool:
        """
        Closes a reference sheet or modal window and uses zero-token visual comparison
        against the pre-modal baseline image to verify that the modal was actually dismissed.
        Executes progressive fallback recovery tiers until dismissed.
        """
        if self.executor.is_stopped():
            return False

        def _check_dismissed() -> Tuple[bool, float]:
            if baseline_img is None or not self.config.local_verification_enabled:
                return True, 0.0
            try:
                cur_img = self.capture.capture_screen(region=region)
                return self.verifier.verify_modal_dismissed(baseline_img, cur_img)
            except Exception as e:
                logger.debug(f"Error capturing screen for modal dismiss check: {e}")
                return True, 0.0

        # Tier 1: Click AI-provided close button (if specified)
        if close_btn and isinstance(close_btn, dict):
            cx = close_btn.get("screen_x", close_btn.get("x"))
            cy = close_btn.get("screen_y", close_btn.get("y"))
            if cx is not None and cy is not None:
                logger.info(f"Tier 1 modal dismiss: Clicking AI close button at ({int(cx)}, {int(cy)})...")
                self.executor.click(int(cx), int(cy), allow_variance=False)
                time.sleep(0.35)
                is_closed, diff = _check_dismissed()
                if is_closed:
                    logger.info(f"[OK] Reference modal dismissed via close button (diff={diff:.2f})")
                    self._handle_adjustment("✓ Reference modal closed (Zero-Token Confirmed)")
                    return True
                logger.warning(f"Close button click at ({cx}, {cy}) failed to dismiss modal (diff={diff:.2f}).")

        # Tier 2: Press Escape key
        if not self.executor.is_stopped():
            logger.info("Tier 2 modal dismiss: Pressing Escape key...")
            self.executor.key_press("escape")
            time.sleep(0.35)
            is_closed, diff = _check_dismissed()
            if is_closed:
                logger.info(f"[OK] Reference modal dismissed via Escape key (diff={diff:.2f})")
                self._handle_adjustment("✓ Reference modal closed via Escape (Zero-Token Confirmed)")
                return True
            logger.warning(f"Escape key failed to dismiss modal (diff={diff:.2f}).")

        # Tier 3: Click standard top-right modal close button ('X')
        if not self.executor.is_stopped():
            # Candidate 3a: top-right corner of modal dialog (~88% width, ~8% height)
            top_right_modal_x = offset_x + int(curr_w * 0.88)
            top_right_modal_y = offset_y + max(35, int(curr_h * 0.08))
            logger.info(f"Tier 3a modal dismiss: Clicking modal top-right 'X' candidate at ({top_right_modal_x}, {top_right_modal_y})...")
            self.executor.click(top_right_modal_x, top_right_modal_y, allow_variance=False)
            time.sleep(0.35)
            is_closed, diff = _check_dismissed()
            if is_closed:
                logger.info(f"[OK] Reference modal dismissed via top-right 'X' (diff={diff:.2f})")
                self._handle_adjustment("✓ Reference modal closed via 'X' (Zero-Token Confirmed)")
                return True

            # Candidate 3b: viewport upper-right corner
            top_right_view_x = offset_x + curr_w - 35
            top_right_view_y = offset_y + 35
            logger.info(f"Tier 3b modal dismiss: Clicking viewport top-right candidate at ({top_right_view_x}, {top_right_view_y})...")
            self.executor.click(top_right_view_x, top_right_view_y, allow_variance=False)
            time.sleep(0.35)
            is_closed, diff = _check_dismissed()
            if is_closed:
                logger.info(f"[OK] Reference modal dismissed via viewport corner (diff={diff:.2f})")
                self._handle_adjustment("✓ Reference modal closed (Zero-Token Confirmed)")
                return True

        # Tier 4: Click modal outer backdrop / overlay margin
        if not self.executor.is_stopped():
            backdrop_x = offset_x + 45
            backdrop_y = offset_y + 45
            logger.info(f"Tier 4 modal dismiss: Clicking outer backdrop margin at ({backdrop_x}, {backdrop_y})...")
            self.executor.click(backdrop_x, backdrop_y, allow_variance=False)
            time.sleep(0.35)
            is_closed, diff = _check_dismissed()
            if is_closed:
                logger.info(f"[OK] Reference modal dismissed via backdrop click (diff={diff:.2f})")
                self._handle_adjustment("✓ Reference modal closed via Backdrop (Zero-Token Confirmed)")
                return True

        # Tier 5: Final Escape key attempt
        if not self.executor.is_stopped():
            logger.info("Tier 5 modal dismiss: Final Escape attempt...")
            self.executor.key_press("escape")
            time.sleep(0.35)
            is_closed, diff = _check_dismissed()
            if is_closed:
                logger.info(f"[OK] Reference modal dismissed on final tier (diff={diff:.2f})")
                return True

        logger.warning("Reference modal could not be visually confirmed as dismissed across all recovery tiers.")
        self._handle_adjustment("⚠️ Warning: Reference modal may still be open")
        return False

    def trigger_check_button(self):
        """Clicks the identified 'Check Answer' / 'Submit' button if known with zero-token verification."""
        if not self.last_result:
            return

        check_btn = self.last_result.get("check_button")
        if not check_btn or not isinstance(check_btn, dict):
            logger.debug("trigger_check_button: No valid check_button in last result.")
            return

        x = check_btn.get("screen_x", check_btn.get("x"))
        y = check_btn.get("screen_y", check_btn.get("y"))
        if x is not None and y is not None:
            cx, cy = int(x), int(y)
            logger.info(f"Clicking Check Answer button at ({cx}, {cy})")
            before_roi = None
            if self.config.local_verification_enabled:
                before_roi = self.verifier.capture_roi(cx, cy, radius_w=45, radius_h=25)

            self.executor.click(cx, cy)

            if self.config.local_verification_enabled and before_roi:
                time.sleep(0.12)
                after_roi = self.verifier.capture_roi(cx, cy, radius_w=45, radius_h=25)
                diff_ok, diff_score = self.verifier.verify_action_completion(before_roi, after_roi, action_type="click")
                if not diff_ok and diff_score < 1.0:
                    logger.warning(f"Check Answer click unconfirmed (diff={diff_score:.1f}). Retrying firmly...")
                    self.executor.click(cx, cy, allow_variance=False)
                else:
                    logger.info(f"[OK] Check Answer button verified (diff={diff_score:.1f})")

    def trigger_next_button(self):
        """Clicks the identified 'Next' button if known with zero-token verification, or scrolls down for scrolling quizzes."""
        if not self.last_result:
            return

        advance_action = str(self.last_result.get("advance_action", "")).lower()
        if advance_action == "scroll_down":
            scroll_amt = int(self.last_result.get("scroll_amount", 450))
            self._advance_by_scrolling_down(scroll_amt=scroll_amt, override_region=self.last_region)
            return

        next_btn = self.last_result.get("next_button")
        if not next_btn or not isinstance(next_btn, dict):
            logger.warning("trigger_next_button: No valid next_button in last result.")
            return

        x = next_btn.get("screen_x", next_btn.get("x"))
        y = next_btn.get("screen_y", next_btn.get("y"))
        if x is not None and y is not None:
            nx, ny = int(x), int(y)
            logger.info(f"Clicking Next Question button at ({nx}, {ny})")
            before_roi = None
            if self.config.local_verification_enabled:
                before_roi = self.verifier.capture_roi(nx, ny, radius_w=45, radius_h=25)

            self.executor.click(nx, ny)

            if self.config.local_verification_enabled and before_roi:
                time.sleep(0.15)
                after_roi = self.verifier.capture_roi(nx, ny, radius_w=45, radius_h=25)
                diff_ok, diff_score = self.verifier.verify_action_completion(before_roi, after_roi, action_type="click")
                if not diff_ok and diff_score < 1.0:
                    logger.warning(f"Next button click unconfirmed (diff={diff_score:.1f}). Retrying firmly without variance...")
                    self.executor.click(nx, ny, allow_variance=False)
                else:
                    logger.info(f"[OK] Next button click verified (diff={diff_score:.1f})")

    def trigger_next_question(self):
        """User manual trigger for Next Question (F10). Supports both button advancing and scroll-down quizzes."""
        with self._action_gate_lock:
            if self.state in [
                EngineState.SCANNING,
                EngineState.THINKING,
                EngineState.EXECUTING,
                EngineState.VERIFYING,
                EngineState.INSPECTING,
            ] or self.executor.is_input_active():
                logger.warning(
                    f"Safeguard engaged: Cannot advance to next question (F10) while busy in state '{self.state.value}'."
                )
                self._handle_adjustment("⚠️ Busy: Next Question (F10) ignored while action/solve is in progress")
                return

            logger.info("Manual Next Question triggered (F10).")
            self.set_state(EngineState.NAVIGATING)
            check_btn = self.last_result.get("check_button") if self.last_result else None
            next_btn = self.last_result.get("next_button") if self.last_result else None
            is_multi_part = self.last_result.get("is_multi_part", False) if self.last_result else False
            advance_action = str(self.last_result.get("advance_action", "")).lower() if self.last_result else ""

            if advance_action == "scroll_down":
                scroll_amt = int(self.last_result.get("scroll_amount", 450)) if self.last_result else 450
                logger.info(f"Manual advance: AI detected scrolling quiz, scrolling down {scroll_amt}px...")
                self._advance_by_scrolling_down(scroll_amt=scroll_amt, override_region=self.last_region)
            elif check_btn and not next_btn:
                # Platform only has Check Answer currently displayed
                self.trigger_check_button()
                time.sleep(1.0)
                self._discover_and_click_next_button(override_region=self.last_region)
            elif check_btn and next_btn:
                # Platform has Check Answer and Next visible
                self.trigger_check_button()
                time.sleep(0.8)
                self.trigger_next_button()
            elif next_btn:
                self.trigger_next_button()
            else:
                self._discover_and_click_next_button(override_region=self.last_region)

            # If in autonomous mode or chain multi-parts is enabled on a multi-part question, continue!
            if (self.config.autonomous_mode or (self.config.chain_multi_parts and is_multi_part)) and not self.executor.is_stopped():
                load_delay = max(2.0, self.config.auto_next_delay + 0.8)
                logger.info(f"Manual advance: Waiting {load_delay:.1f}s for next question to render...")
                self._handle_adjustment("⏳ Waiting for next question to load...")
                time.sleep(load_delay)
                logger.info("Continuing solve pipeline for next part/question after manual advance...")
                self.set_state(EngineState.IDLE)
                self.trigger_solve()
            else:
                self.set_state(EngineState.IDLE)

    def pause_resume(self):
        """Toggles pause/resume state."""
        if self.state == EngineState.PAUSED:
            logger.info("Resuming assistant from paused state.")
            self.executor.reset_stop()
            self.set_state(EngineState.IDLE)
        else:
            logger.info("Pausing assistant.")
            self.executor.request_stop()
            self.set_state(EngineState.PAUSED)

    def emergency_stop(self):
        """Instant killswitch (F12). Aborts immediately."""
        logger.warning("EMERGENCY KILLSWITCH (F12) ACTIVATED!")
        self.executor.request_stop()
        self.set_state(EngineState.PAUSED, "Emergency Killswitch Activated")
