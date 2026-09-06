"""
Unified Multimodal AI Client for AVA School Assistant 2.
Directly communicates via standard REST APIs (Gemini, OpenAI, Anthropic, OpenRouter)
to process screenshots and return structured solving and coordinate data.
"""

import json
import re
from typing import Dict, Any, Optional, Tuple, List
import requests

from core.prompt import get_vision_system_prompt
from core.logger import get_logger

logger = get_logger("ai")


def format_api_error(provider: str, status_code: int, response_text: str) -> str:
    """Parses structured JSON error details from API responses into a readable error message."""
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            if "error" in data:
                err = data["error"]
                if isinstance(err, dict):
                    msg = err.get("message", "")
                    status = err.get("status", "")
                    err_type = err.get("type", "")
                    code = err.get("code", status_code)
                    details = err.get("details", [])

                    extras = []
                    if status:
                        extras.append(f"status: {status}")
                    if err_type:
                        extras.append(f"type: {err_type}")
                    if code and str(code) != str(status_code):
                        extras.append(f"code: {code}")
                    if details:
                        extras.append(f"details: {details}")

                    extra_str = f" [{', '.join(extras)}]" if extras else ""
                    return f"{provider.title()} API Error ({status_code}){extra_str}: {msg}"
                elif isinstance(err, str):
                    return f"{provider.title()} API Error ({status_code}): {err}"
    except Exception:
        pass

    # Fallback to raw text without trailing whitespace
    clean_text = response_text.strip()
    return f"{provider.title()} API Error ({status_code}): {clean_text}"


class AIClient:
    """Client for querying multimodal LLMs with screenshot data."""

    def __init__(
        self,
        provider: str = "gemini",
        api_key: str = "",
        model_name: str = "gemini-3.6-flash",
        custom_base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 45
    ):
        self.provider = provider.lower()
        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.custom_base_url = custom_base_url.rstrip("/")
        self.timeout = timeout

    def test_connection(self) -> Tuple[bool, str]:
        """Verifies if the current provider and API key can connect successfully."""
        if not self.api_key:
            return False, "API Key is empty."

        logger.info(f"Testing connection for provider '{self.provider}'...")
        try:
            if self.provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    logger.info("Successfully connected to Google Gemini API!")
                    return True, "Successfully connected to Google Gemini API!"
                err_msg = format_api_error("Gemini", resp.status_code, resp.text)
                logger.error(f"Gemini connection test failed: {err_msg}")
                return False, err_msg

            elif self.provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    logger.info("Successfully connected to OpenAI API!")
                    return True, "Successfully connected to OpenAI API!"
                err_msg = format_api_error("OpenAI", resp.status_code, resp.text)
                logger.error(f"OpenAI connection test failed: {err_msg}")
                return False, err_msg

            elif self.provider == "anthropic":
                url = "https://api.anthropic.com/v1/models"
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                }
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    logger.info("Successfully connected to Anthropic Claude API!")
                    return True, "Successfully connected to Anthropic Claude API!"
                err_msg = format_api_error("Anthropic", resp.status_code, resp.text)
                logger.error(f"Anthropic connection test failed: {err_msg}")
                return False, err_msg

            elif self.provider == "custom":
                url = f"{self.custom_base_url}/models"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Successfully connected to custom endpoint ({self.custom_base_url})!")
                    return True, f"Successfully connected to custom endpoint ({self.custom_base_url})!"
                err_msg = format_api_error("Custom", resp.status_code, resp.text)
                logger.error(f"Custom endpoint connection test failed: {err_msg}")
                return False, err_msg

            logger.error(f"Unknown provider: {self.provider}")
            return False, f"Unknown provider: {self.provider}"
        except Exception as e:
            err_msg = f"Connection failed: {str(e)}"
            logger.error(f"Connection test exception: {e}")
            return False, err_msg

    def solve_screen(
        self,
        base64_image: str,
        image_width: int,
        image_height: int,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
        calibration_offset_x: int = 0,
        calibration_offset_y: int = 0,
        calibration_scale_x: float = 1.0,
        calibration_scale_y: float = 1.0,
        coordinate_mode: str = "normalized_1000",
        extra_images: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Sends the screenshot to the chosen AI model, parses structured solution,
        and scales action coordinates to global screen pixel coordinates.
        Supports extra_images for supplementary reference views or scrolled content.
        """
        if not self.api_key:
            raise ValueError("API Key is not configured. Please set your API key in Settings.")

        prompt = get_vision_system_prompt(image_width, image_height)

        raw_response_text = ""
        if self.provider == "gemini":
            raw_response_text = self._call_gemini(base64_image, prompt, extra_images=extra_images)
        elif self.provider == "openai":
            raw_response_text = self._call_openai(base64_image, prompt, extra_images=extra_images)
        elif self.provider == "anthropic":
            raw_response_text = self._call_anthropic(base64_image, prompt, extra_images=extra_images)
        elif self.provider == "custom":
            raw_response_text = self._call_custom(base64_image, prompt, extra_images=extra_images)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        # Parse JSON
        result = self._extract_json(raw_response_text)

        # Scale coordinates back to global desktop screen space
        self._map_coordinates(
            result=result,
            scale_x=scale_x,
            scale_y=scale_y,
            offset_x=offset_x,
            offset_y=offset_y,
            image_width=image_width,
            image_height=image_height,
            calibration_offset_x=calibration_offset_x,
            calibration_offset_y=calibration_offset_y,
            calibration_scale_x=calibration_scale_x,
            calibration_scale_y=calibration_scale_y,
            coordinate_mode=coordinate_mode
        )

        return result

    def detect_navigation_button(
        self,
        base64_image: str,
        image_width: int,
        image_height: int,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
        calibration_offset_x: int = 0,
        calibration_offset_y: int = 0,
        calibration_scale_x: float = 1.0,
        calibration_scale_y: float = 1.0,
        coordinate_mode: str = "normalized_1000"
    ) -> Optional[Dict[str, Any]]:
        """
        Locates the Next, Continue, Submit, or Arrow button on screen after answering or checking.
        Returns the mapped button dict with screen_x and screen_y, or None if not found.
        """
        if not self.api_key:
            return None

        from core.prompt import get_navigation_detection_prompt
        prompt = get_navigation_detection_prompt(image_width, image_height)

        raw_response_text = ""
        try:
            if self.provider == "gemini":
                raw_response_text = self._call_gemini(base64_image, prompt)
            elif self.provider == "openai":
                raw_response_text = self._call_openai(base64_image, prompt)
            elif self.provider == "anthropic":
                raw_response_text = self._call_anthropic(base64_image, prompt)
            elif self.provider == "custom":
                raw_response_text = self._call_custom(base64_image, prompt)
            else:
                return None
        except Exception as e:
            logger.warning(f"Navigation detection call failed: {e}")
            return None

        try:
            result = self._extract_json(raw_response_text)
        except Exception as e:
            logger.warning(f"Could not parse navigation detection JSON: {e}")
            return None

        next_btn = result.get("next_button")
        if not next_btn and result.get("button"):
            next_btn = result.get("button")

        if next_btn and isinstance(next_btn, dict):
            # Scale coordinates back to global desktop screen space
            self._map_coordinates(
                result={"next_button": next_btn},
                scale_x=scale_x,
                scale_y=scale_y,
                offset_x=offset_x,
                offset_y=offset_y,
                image_width=image_width,
                image_height=image_height,
                calibration_offset_x=calibration_offset_x,
                calibration_offset_y=calibration_offset_y,
                calibration_scale_x=calibration_scale_x,
                calibration_scale_y=calibration_scale_y,
                coordinate_mode=coordinate_mode
            )
            next_btn["advance_action"] = result.get("advance_action", "click_button")
            return next_btn

        advance_action = str(result.get("advance_action", "")).lower()
        if advance_action == "scroll_down" or (result.get("found") and not next_btn and result.get("scroll_amount")):
            scroll_amt = int(result.get("scroll_amount", 450))
            logger.info(f"Navigation detected scrolling quiz: advancing by scrolling down {scroll_amt}px")
            return {
                "type": "scroll_down",
                "advance_action": "scroll_down",
                "scroll_amount": scroll_amt,
                "description": f"Scroll down {scroll_amt}px to next question"
            }

        return None

    def _call_gemini(self, base64_image: str, prompt: str, extra_images: Optional[List[str]] = None) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )
        headers = {"Content-Type": "application/json"}
        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64_image
                }
            }
        ]
        if extra_images:
            for idx, extra_b64 in enumerate(extra_images):
                parts.append({"text": f"Supplementary image {idx + 1} (reference sheet or scrolled view):"})
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": extra_b64
                    }
                })

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }

        logger.debug(f"Calling Gemini endpoint for model {self.model_name}...")
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            err_msg = format_api_error("Gemini", resp.status_code, resp.text)
            logger.error(f"Gemini API request failed (HTTP {resp.status_code}): {resp.text}")
            raise RuntimeError(err_msg)

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected response structure from Gemini: {data}")
            raise RuntimeError(f"Unexpected response structure from Gemini: {data}")

    def _call_openai(self, base64_image: str, prompt: str, base_url: Optional[str] = None, extra_images: Optional[List[str]] = None) -> str:
        target_url = f"{base_url or 'https://api.openai.com/v1'}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        user_content = [
            {
                "type": "text",
                "text": "Solve the schoolwork question shown in this screenshot and provide the GUI actions."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                    "detail": "high"
                }
            }
        ]
        if extra_images:
            for idx, extra_b64 in enumerate(extra_images):
                user_content.append({
                    "type": "text",
                    "text": f"Supplementary image {idx + 1} (reference sheet or scrolled view):"
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{extra_b64}",
                        "detail": "high"
                    }
                })

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1500
        }

        provider_name = "Custom" if base_url else "OpenAI"
        logger.debug(f"Calling {provider_name} chat completions at {target_url}...")
        resp = requests.post(target_url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            err_msg = format_api_error(provider_name, resp.status_code, resp.text)
            logger.error(f"{provider_name} API request failed (HTTP {resp.status_code}): {resp.text}")
            raise RuntimeError(err_msg)

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            logger.error(f"Unexpected response structure from {provider_name}: {data}")
            raise RuntimeError(f"Unexpected response structure from {provider_name}: {data}")

    def _call_anthropic(self, base64_image: str, prompt: str, extra_images: Optional[List[str]] = None) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image
                }
            }
        ]
        if extra_images:
            for idx, extra_b64 in enumerate(extra_images):
                user_content.append({
                    "type": "text",
                    "text": f"Supplementary image {idx + 1} (reference sheet or scrolled view):"
                })
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": extra_b64
                    }
                })
        user_content.append({
            "type": "text",
            "text": "Solve the question and return the JSON actions."
        })

        payload = {
            "model": self.model_name,
            "max_tokens": 1500,
            "system": prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "temperature": 0.1
        }

        logger.debug(f"Calling Anthropic messages endpoint for model {self.model_name}...")
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            err_msg = format_api_error("Anthropic", resp.status_code, resp.text)
            logger.error(f"Anthropic API request failed (HTTP {resp.status_code}): {resp.text}")
            raise RuntimeError(err_msg)

        data = resp.json()
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError):
            logger.error(f"Unexpected response structure from Anthropic: {data}")
            raise RuntimeError(f"Unexpected response structure from Anthropic: {data}")

    def _call_custom(self, base64_image: str, prompt: str, extra_images: Optional[List[str]] = None) -> str:
        return self._call_openai(base64_image, prompt, base_url=self.custom_base_url, extra_images=extra_images)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extracts and parses JSON object from model output."""
        cleaned = text.strip()
        # Remove markdown fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.debug(f"Direct JSON parse failed: {e}. Attempting regex boundary search...")
            # Attempt to find first { and last }
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            logger.error(f"Could not parse valid JSON from AI output (length={len(text)}). Output starts with: {cleaned[:300]}")
            raise ValueError(f"Could not parse valid JSON from AI output (length={len(text)}):\n{cleaned[:300]}")

    def _map_coordinates(
        self,
        result: Dict[str, Any],
        scale_x: float,
        scale_y: float,
        offset_x: int,
        offset_y: int,
        image_width: Optional[int] = None,
        image_height: Optional[int] = None,
        calibration_offset_x: int = 0,
        calibration_offset_y: int = 0,
        calibration_scale_x: float = 1.0,
        calibration_scale_y: float = 1.0,
        coordinate_mode: str = "normalized_1000"
    ):
        """
        Translates coordinates from model output space to real screen desktop space,
        accounting for [0, 1000] normalized grid, high-DPI scaling, and user calibration.
        """
        # Determine target physical dimensions of the captured region
        if image_width is not None and image_width > 0:
            target_w = float(image_width * scale_x)
        else:
            target_w = float(1000 * scale_x)

        if image_height is not None and image_height > 0:
            target_h = float(image_height * scale_y)
        else:
            target_h = float(1000 * scale_y)

        def _translate_point(raw_x: float, raw_y: float) -> Tuple[int, int]:
            # Detect whether to treat coordinate as normalized (0..1000) or raw pixel space
            use_normalized = True
            if coordinate_mode == "raw_pixels":
                use_normalized = False
            elif coordinate_mode == "auto":
                if raw_x > 1000 or raw_y > 1000:
                    use_normalized = False

            if use_normalized:
                base_x = (raw_x / 1000.0) * target_w
                base_y = (raw_y / 1000.0) * target_h
            else:
                base_x = raw_x * scale_x
                base_y = raw_y * scale_y

            final_x = int(base_x * calibration_scale_x + offset_x + calibration_offset_x)
            final_y = int(base_y * calibration_scale_y + offset_y + calibration_offset_y)
            return final_x, final_y

        def _process_action(action: Dict[str, Any], context_label: str = ""):
            action_type = action.get("type", "action")
            # Support box_2d: [ymin, xmin, ymax, xmax] if provided
            if "box_2d" in action and isinstance(action["box_2d"], (list, tuple)) and len(action["box_2d"]) == 4:
                b = action["box_2d"]
                action["x"] = (b[1] + b[3]) / 2.0
                action["y"] = (b[0] + b[2]) / 2.0

            if "x" in action and "y" in action:
                sx, sy = _translate_point(float(action["x"]), float(action["y"]))
                action["screen_x"] = sx
                action["screen_y"] = sy
                desc = action.get("description", "")
                prefix = f"[{context_label}] " if context_label else ""
                logger.info(
                    f"Target mapped {prefix}[{action_type}]: model=({action['x']}, {action['y']}) -> "
                    f"screen=({sx}, {sy}) [cal_offset=+({calibration_offset_x},{calibration_offset_y}), "
                    f"cal_scale=({calibration_scale_x},{calibration_scale_y})] - {desc}"
                )

            if "from_x" in action and "from_y" in action:
                fx, fy = _translate_point(float(action["from_x"]), float(action["from_y"]))
                action["screen_from_x"] = fx
                action["screen_from_y"] = fy

            if "to_x" in action and "to_y" in action:
                tx, ty = _translate_point(float(action["to_x"]), float(action["to_y"]))
                action["screen_to_x"] = tx
                action["screen_to_y"] = ty

        # Process multi-part items if present
        items = result.get("items", [])
        combined_actions = []
        if isinstance(items, list) and items:
            for item in items:
                part_id = item.get("part_id", "Part")
                needs_action = item.get("needs_action", True)
                item_actions = item.get("actions", [])
                if isinstance(item_actions, list):
                    for act in item_actions:
                        _process_action(act, context_label=part_id)
                        if needs_action:
                            combined_actions.append(act)

        # Also process top-level actions (backwards compatibility / single part)
        top_actions = result.get("actions", [])
        if isinstance(top_actions, list) and top_actions:
            for act in top_actions:
                _process_action(act)
        else:
            result["actions"] = combined_actions

        # Normalize aliases if present
        if "submit_button" in result and not result.get("check_button"):
            result["check_button"] = result["submit_button"]
        if "continue_button" in result and not result.get("next_button"):
            result["next_button"] = result["continue_button"]

        # Map check_button, next_button, reference_button, and close_button coordinates
        for btn_key in ["check_button", "next_button", "reference_button", "close_button"]:
            btn = result.get(btn_key)
            if btn and isinstance(btn, dict):
                if "box_2d" in btn and isinstance(btn["box_2d"], (list, tuple)) and len(btn["box_2d"]) == 4:
                    b = btn["box_2d"]
                    btn["x"] = (b[1] + b[3]) / 2.0
                    btn["y"] = (b[0] + b[2]) / 2.0

                if "x" in btn and "y" in btn:
                    sx, sy = _translate_point(float(btn["x"]), float(btn["y"]))
                    btn["screen_x"] = sx
                    btn["screen_y"] = sy
                    logger.info(f"Target mapped [{btn_key}]: model=({btn['x']}, {btn['y']}) -> screen=({sx}, {sy})")

        # Process and normalize evaluation status, rethinking, and question/answer
        any_incorrect = False
        all_correct = True if (isinstance(items, list) and items) else False
        rethink_reasons = []

        if isinstance(items, list) and items:
            for item in items:
                # Normalize item question & answer aliases
                sub_q = item.get("question") or item.get("question_text") or ""
                item["question"] = sub_q
                item["question_text"] = sub_q

                sub_ans = item.get("correct_answer") or item.get("proposed_answer") or item.get("answer") or ""
                item["correct_answer"] = sub_ans
                item["proposed_answer"] = sub_ans
                item["answer"] = sub_ans

                # Normalize evaluation_status
                raw_eval = str(item.get("evaluation_status", "")).strip().lower()
                raw_state = str(item.get("current_state", "")).strip().lower()

                if raw_eval in ["correct", "graded_correct", "right", "passed"] or raw_state == "answered_correct":
                    item["evaluation_status"] = "correct"
                elif raw_eval in ["incorrect", "wrong", "failed", "error", "graded_incorrect"] or raw_state in ["answered_incorrect", "wrong"]:
                    item["evaluation_status"] = "incorrect"
                else:
                    item["evaluation_status"] = "unsubmitted"

                if item["evaluation_status"] == "incorrect":
                    any_incorrect = True
                    all_correct = False
                    item["is_rethinking"] = True
                    r_reason = item.get("rethink_reasoning") or item.get("reasoning") or ""
                    if r_reason:
                        rethink_reasons.append(r_reason)
                elif item["evaluation_status"] != "correct":
                    all_correct = False

            if not result.get("answer"):
                if len(items) == 1:
                    result["answer"] = items[0].get("correct_answer", "")
                else:
                    ans_parts = []
                    for itm in items:
                        p_label = itm.get("label") or itm.get("part_id") or "Part"
                        p_ans = itm.get("correct_answer", "")
                        if p_ans:
                            ans_parts.append(f"{p_label}: {p_ans}")
                    result["answer"] = " | ".join(ans_parts) if ans_parts else "See sub-parts below"

            if not result.get("question"):
                if len(items) == 1:
                    result["question"] = items[0].get("question_text", "")
                else:
                    result["question"] = result.get("summary") or items[0].get("question_text", "Multi-part question")

            if not result.get("reasoning"):
                if len(items) == 1:
                    result["reasoning"] = items[0].get("reasoning", "")
                else:
                    result["reasoning"] = result.get("summary") or "Multi-part question analyzed."

        # Top-level evaluation_status normalization
        top_eval = str(result.get("evaluation_status", "")).strip().lower()
        if top_eval in ["correct", "graded_correct", "right", "passed"] or all_correct:
            result["evaluation_status"] = "correct"
        elif top_eval in ["incorrect", "wrong", "failed", "error", "graded_incorrect"] or any_incorrect:
            result["evaluation_status"] = "incorrect"
        else:
            result["evaluation_status"] = "unsubmitted"

        # If marked incorrect, ensure rethink flags and reasons are set
        if result["evaluation_status"] == "incorrect":
            result["is_rethinking"] = True
            if not result.get("rethink_reasoning") and rethink_reasons:
                result["rethink_reasoning"] = " | ".join(rethink_reasons)
            elif not result.get("rethink_reasoning"):
                result["rethink_reasoning"] = "Question was marked incorrect by platform. Rethinking academic solution and entry formatting."
            # INVARIANT: An incorrect question can NEVER be marked ready to advance!
            result["ready_to_advance"] = False
        else:
            result.setdefault("is_rethinking", False)
            result.setdefault("rethink_reasoning", "")

        result.setdefault("platform_feedback", "")

        if not result.get("answer"):
            result["answer"] = result.get("summary") or "Answer determined"

        if not result.get("question"):
            result["question"] = result.get("summary") or "Question detected"
