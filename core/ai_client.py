"""
Unified Multimodal AI Client for AVA School Assistant 2.
Directly communicates via standard REST APIs (Gemini, OpenAI, Anthropic, OpenRouter)
to process screenshots and return structured solving and coordinate data.
"""

import json
import re
import random
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
        extra_images: Optional[List[str]] = None,
        mark_registry: Optional[Dict[int, Tuple[int, int]]] = None
    ) -> Dict[str, Any]:
        """
        Sends the screenshot to the chosen AI model, parses structured solution,
        and scales action coordinates to global screen pixel coordinates.
        Supports extra_images for supplementary reference views or scrolled content.
        Supports mark_registry for zero-token Set-of-Marks grounding and coordinate snapping.
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
        has_multi_view = bool(extra_images and len(extra_images) > 0)
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
            coordinate_mode=coordinate_mode,
            has_multi_view=has_multi_view,
            mark_registry=mark_registry
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

        btn_type = str(result.get("button_type", "")).lower().strip()

        target_btn = None
        target_key = "next_button"
        if result.get("submit_button"):
            target_btn = result.get("submit_button")
            target_key = "submit_button"
            if not btn_type:
                btn_type = "submit"
        elif result.get("next_button"):
            target_btn = result.get("next_button")
            target_key = "next_button"
            if not btn_type:
                btn_type = "next"
        elif result.get("check_button"):
            target_btn = result.get("check_button")
            target_key = "check_button"
            if not btn_type:
                btn_type = "check"
        else:
            for fallback_key in ["button", "continue_button", "navigation_button", "action_button"]:
                if result.get(fallback_key):
                    target_btn = result.get(fallback_key)
                    target_key = fallback_key
                    break

        if target_btn and isinstance(target_btn, dict):
            # Scale coordinates back to global desktop screen space
            self._map_coordinates(
                result={target_key: target_btn},
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
                coordinate_mode=coordinate_mode,
                has_multi_view=False
            )
            target_btn["advance_action"] = result.get("advance_action", "click_button")

            # Determine / refine button_type
            desc = str(target_btn.get("description", "")).lower()
            if not btn_type:
                if any(w in desc for w in ["submit quiz", "submit assignment", "turn in", "hand in", "finish quiz", "finish test", "complete test", "submit all"]):
                    btn_type = "submit"
                elif any(w in desc for w in ["check", "verify", "submit answer"]):
                    btn_type = "check"
                elif "submit" in desc:
                    btn_type = "submit"
                else:
                    btn_type = "next"
            target_btn["button_type"] = btn_type
            return target_btn

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

    def double_check_solution(
        self,
        base64_image: str,
        question: str,
        intended_answer: str,
        intended_actions: Optional[List[Dict[str, Any]]] = None,
        image_width: int = 1000,
        image_height: int = 1000,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        offset_x: int = 0,
        offset_y: int = 0,
        calibration_offset_x: int = 0,
        calibration_offset_y: int = 0,
        calibration_scale_x: float = 1.0,
        calibration_scale_y: float = 1.0,
        coordinate_mode: str = "normalized_1000",
        mark_registry: Optional[Dict[int, Tuple[int, int]]] = None
    ) -> Dict[str, Any]:
        """
        Visually double-checks the current screenshot after actions have been executed,
        verifying whether the on-screen selected options or typed answers accurately match
        the target correct answer. If a mistake is detected (e.g. wrong option, unclicked option),
        returns mapped corrective actions to resolve it.
        """
        if not self.api_key:
            return {"double_check_passed": True, "messed_up": False, "issue_type": "none", "details": "API key not configured", "corrective_actions": []}

        from core.prompt import get_double_check_prompt
        prompt = get_double_check_prompt(
            image_width=image_width,
            image_height=image_height,
            question=question,
            intended_answer=intended_answer,
            intended_actions=intended_actions
        )

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
                return {"double_check_passed": True, "messed_up": False, "issue_type": "none", "details": f"Unsupported provider: {self.provider}", "corrective_actions": []}
        except Exception as e:
            logger.warning(f"Double-check vision call failed: {e}")
            return {"double_check_passed": True, "messed_up": False, "issue_type": "none", "details": f"Vision call error: {e}", "corrective_actions": []}

        try:
            result = self._extract_json(raw_response_text)
        except Exception as e:
            logger.warning(f"Could not parse double-check JSON: {e}")
            return {"double_check_passed": True, "messed_up": False, "issue_type": "none", "details": f"JSON parse error: {e}", "corrective_actions": []}

        # Normalize fields
        messed_up = bool(result.get("messed_up", False))
        double_check_passed = bool(result.get("double_check_passed", not messed_up))
        if messed_up:
            double_check_passed = False

        issue_type = str(result.get("issue_type", "none" if not messed_up else "other")).lower().strip()
        details = str(result.get("details", "")).strip()
        selected_summary = str(result.get("currently_selected_summary", "")).strip()
        corrective_actions = result.get("corrective_actions", [])
        if not isinstance(corrective_actions, list):
            corrective_actions = []

        # Map corrective action coordinates if needed
        if corrective_actions:
            corr_dict = {"actions": corrective_actions}
            self._map_coordinates(
                result=corr_dict,
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
                coordinate_mode=coordinate_mode,
                has_multi_view=False,
                mark_registry=mark_registry
            )
            corrective_actions = corr_dict.get("actions", [])

        return {
            "double_check_passed": double_check_passed,
            "messed_up": messed_up,
            "issue_type": issue_type,
            "currently_selected_summary": selected_summary,
            "details": details,
            "corrective_actions": corrective_actions
        }

    def generate_text_response(
        self,
        prompt: str,
        system_instruction: str = "",
        model_override: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """
        Generates a direct text response for written schoolwork, explanations, and essays
        using the configured AI provider (Gemini, OpenAI, Anthropic, or Custom).
        """
        if not self.api_key:
            raise RuntimeError("API Key is missing.")

        model = (model_override or self.model_name).strip()
        headers = {"Content-Type": "application/json"}

        if self.provider == "gemini":
            candidate_models = [model, "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
            seen = set()
            models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

            for mod in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={self.api_key}"
                payload: Dict[str, Any] = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature},
                }
                if system_instruction:
                    payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            return "".join(p.get("text", "") for p in parts).strip()
                        return ""
                    logger.debug(f"Gemini text generation failed for model {mod} (HTTP {resp.status_code}): {resp.text}")
                except Exception as e:
                    logger.debug(f"Gemini text request exception on {mod}: {e}")
                    continue

            raise RuntimeError(f"All Gemini models failed to generate text response.")

        elif self.provider == "openai":
            url = f"{self.custom_base_url if self.provider == 'custom' else 'https://api.openai.com/v1'}/chat/completions"
            oa_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            resp = requests.post(url, headers=oa_headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error("OpenAI", resp.status_code, resp.text)
                raise RuntimeError(err_msg)
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        elif self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            ant_headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
            if system_instruction:
                payload["system"] = system_instruction

            resp = requests.post(url, headers=ant_headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error("Anthropic", resp.status_code, resp.text)
                raise RuntimeError(err_msg)
            data = resp.json()
            return data["content"][0]["text"].strip()

        elif self.provider == "custom":
            url = f"{self.custom_base_url}/chat/completions"
            oa_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            resp = requests.post(url, headers=oa_headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error("Custom", resp.status_code, resp.text)
                raise RuntimeError(err_msg)
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        raise RuntimeError(f"Unsupported provider: {self.provider}")

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
                parts.append({"text": f"Supplementary image {idx + 1} (reference sheet, dropdown options, or scrolled view):"})
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
        coordinate_mode: str = "normalized_1000",
        has_multi_view: bool = False,
        mark_registry: Optional[Dict[int, Tuple[int, int]]] = None
    ):
        """
        Translates coordinates from model output space to real screen desktop space,
        accounting for [0, 1000] normalized grid, high-DPI scaling, and user calibration.
        Supports visual grounding mark_registry for explicit mark IDs and proximity snapping.
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

        def _get_mark_coords(entry: Any) -> Tuple[float, float, Optional[int], Optional[int]]:
            if isinstance(entry, dict):
                norm_x = float(entry.get("norm_x", entry.get("x", 0)))
                norm_y = float(entry.get("norm_y", entry.get("y", 0)))
                sx = entry.get("screen_x")
                sy = entry.get("screen_y")
                return norm_x, norm_y, (int(sx) if sx is not None else None), (int(sy) if sy is not None else None)
            elif isinstance(entry, (list, tuple)):
                return float(entry[0]), float(entry[1]), None, None
            return 0.0, 0.0, None, None

        def _resolve_mark_or_snap(obj: Dict[str, Any], label: str = ""):
            """Resolves explicit Set-of-Marks ID or snaps near-miss coordinates to candidate anchors."""
            if not mark_registry:
                return

            # Case 1: Explicit mark provided (e.g. "mark": 3 or "mark": "3")
            raw_mark = obj.get("mark")
            if raw_mark is not None:
                try:
                    mark_id = int(str(raw_mark).strip().strip("[]"))
                    if mark_id in mark_registry:
                        mx, my, msx, msy = _get_mark_coords(mark_registry[mark_id])
                        logger.info(f"Visual grounding: Resolved {label} mark [{mark_id}] -> norm=({mx}, {my}), screen=({msx}, {msy})")
                        obj["x"] = mx
                        obj["y"] = my
                        obj["grounded_mark"] = mark_id
                        if msx is not None and msy is not None:
                            obj["screen_x"] = msx
                            obj["screen_y"] = msy
                        return
                except (ValueError, TypeError):
                    pass

            # Case 2: Proximity snapping if model gave (x, y) close to a detected mark anchor
            if "x" in obj and "y" in obj:
                try:
                    ox = float(obj["x"])
                    oy = float(obj["y"])
                    best_dist = 999999.0
                    best_mark = None
                    best_norm = None
                    best_screen = None
                    for mid, m_entry in mark_registry.items():
                        mx, my, msx, msy = _get_mark_coords(m_entry)
                        dist = ((ox - mx) ** 2 + (oy - my) ** 2) ** 0.5
                        if dist < best_dist:
                            best_dist = dist
                            best_mark = mid
                            best_norm = (mx, my)
                            best_screen = (msx, msy)

                    # Snap if within 28 normalized units (~2.8% of screen)
                    if best_norm and best_dist <= 28.0:
                        logger.info(
                            f"Visual grounding: Snapped {label} ({ox:.0f}, {oy:.0f}) to anchor "
                            f"mark [{best_mark}] ({best_norm[0]}, {best_norm[1]}), dist={best_dist:.1f}"
                        )
                        obj["x"] = best_norm[0]
                        obj["y"] = best_norm[1]
                        obj["mark"] = best_mark
                        obj["grounded_mark"] = best_mark
                        if best_screen and best_screen[0] is not None and best_screen[1] is not None:
                            obj["screen_x"] = best_screen[0]
                            obj["screen_y"] = best_screen[1]
                except (ValueError, TypeError):
                    pass

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
            if not has_multi_view:
                # In single-view captures, no scrolled lower view exists; force in_scrolled_view to False
                action["in_scrolled_view"] = False

            # Set-of-Marks ID resolution and proximity snapping
            _resolve_mark_or_snap(action, context_label or action_type)

            # Support box_2d: [ymin, xmin, ymax, xmax]
            if "box_2d" in action and isinstance(action["box_2d"], (list, tuple)) and len(action["box_2d"]) == 4:
                b = action["box_2d"]
                ymin, xmin, ymax, xmax = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                # Check if coordinates are 0..1 normalized instead of 0..1000
                if max(ymin, xmin, ymax, xmax) <= 1.0:
                    ymin *= 1000.0
                    xmin *= 1000.0
                    ymax *= 1000.0
                    xmax *= 1000.0
                action["box_2d"] = [ymin, xmin, ymax, xmax]
                # If x or y are not provided, use the geometric center of the box
                if "x" not in action or "y" not in action:
                    action["x"] = (xmin + xmax) / 2.0
                    action["y"] = (ymin + ymax) / 2.0

                bx1, by1 = _translate_point(xmin, ymin)
                bx2, by2 = _translate_point(xmax, ymax)
                action["box_screen"] = [min(bx1, bx2), min(by1, by2), max(bx1, bx2), max(by1, by2)]
                action["box_width"] = abs(bx2 - bx1)
                action["box_height"] = abs(by2 - by1)

            if "x" in action and "y" in action:
                if "screen_x" not in action or "screen_y" not in action:
                    sx, sy = _translate_point(float(action["x"]), float(action["y"]))
                    action["screen_x"] = sx
                    action["screen_y"] = sy
                else:
                    sx, sy = action["screen_x"], action["screen_y"]
                desc = action.get("description", "")
                prefix = f"[{context_label}] " if context_label else ""
                box_info = f" box={action['box_screen']}" if "box_screen" in action else ""
                logger.info(
                    f"Target mapped {prefix}[{action_type}]: model=({action['x']}, {action['y']}) -> "
                    f"screen=({sx}, {sy}){box_info} [cal_offset=+({calibration_offset_x},{calibration_offset_y}), "
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

        def _process_choice(choice: Dict[str, Any]):
            _resolve_mark_or_snap(choice, choice.get("label", "choice"))
            if "box_2d" in choice and isinstance(choice["box_2d"], (list, tuple)) and len(choice["box_2d"]) == 4:
                b = choice["box_2d"]
                ymin, xmin, ymax, xmax = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                if max(ymin, xmin, ymax, xmax) <= 1.0:
                    ymin *= 1000.0
                    xmin *= 1000.0
                    ymax *= 1000.0
                    xmax *= 1000.0
                choice["box_2d"] = [ymin, xmin, ymax, xmax]
                if "x" not in choice or "y" not in choice:
                    choice["x"] = (xmin + xmax) / 2.0
                    choice["y"] = (ymin + ymax) / 2.0
                bx1, by1 = _translate_point(xmin, ymin)
                bx2, by2 = _translate_point(xmax, ymax)
                choice["box_screen"] = [min(bx1, bx2), min(by1, by2), max(bx1, bx2), max(by1, by2)]
            if "x" in choice and "y" in choice:
                sx, sy = _translate_point(float(choice["x"]), float(choice["y"]))
                choice["screen_x"] = sx
                choice["screen_y"] = sy

        # Process top-level choices if present
        if "choices" in result and isinstance(result["choices"], list):
            for ch in result["choices"]:
                _process_choice(ch)

        # Process multi-part items if present
        items = result.get("items", [])
        combined_actions = []
        if isinstance(items, list) and items:
            for item in items:
                part_id = item.get("part_id", "Part")
                needs_action = item.get("needs_action", True)
                item_choices = item.get("choices", [])
                if isinstance(item_choices, list):
                    for ch in item_choices:
                        _process_choice(ch)

                item_actions = item.get("actions", [])
                if isinstance(item_actions, list):
                    for act in item_actions:
                        if item_choices:
                            act["choices"] = item_choices
                        _process_action(act, context_label=part_id)
                        if needs_action:
                            combined_actions.append(act)

        # Also process top-level actions (backwards compatibility / single part)
        top_actions = result.get("actions", [])
        if isinstance(top_actions, list) and top_actions:
            for act in top_actions:
                if "choices" in result and "choices" not in act:
                    act["choices"] = result["choices"]
                _process_action(act)
        else:
            result["actions"] = combined_actions

        # Choice-to-Action Fallback Synthesis:
        # If no explicit actions were returned, but choices and an answer exist,
        # synthesize the click action targeting the matching choice to prevent false cut-off scrolling!
        if not result.get("actions") and result.get("needs_action") is not False:
            ans_str = str(result.get("answer") or result.get("correct_answer") or "").strip().lower()
            all_choices = result.get("choices")
            if not all_choices and isinstance(result.get("items"), list):
                for itm in result["items"]:
                    if itm.get("choices"):
                        all_choices = itm["choices"]
                        if not ans_str:
                            ans_str = str(itm.get("correct_answer") or itm.get("answer") or "").strip().lower()
                        break

            if isinstance(all_choices, list) and all_choices and ans_str:
                matched_choice = None
                # Pass 1: exact label/text match or substring match
                for ch in all_choices:
                    lbl = str(ch.get("label", "")).strip().lower()
                    txt = str(ch.get("text", "")).strip().lower()
                    if (lbl and (lbl in ans_str or ans_str in lbl)) or (txt and (txt in ans_str or ans_str in txt)):
                        matched_choice = ch
                        break

                # Pass 2: Option letter match (e.g. 'A', 'B', 'C', 'D')
                if not matched_choice:
                    for ch in all_choices:
                        lbl = str(ch.get("label", "")).strip().lower()
                        for letter in ["a", "b", "c", "d", "e"]:
                            if (f"option {letter}" in ans_str or f"({letter})" in ans_str
                                or ans_str.startswith(f"{letter}.") or ans_str.startswith(f"{letter})")
                                or ans_str == letter or ans_str.startswith(f"choice {letter}")):
                                if (f"option {letter}" in lbl or f"({letter})" in lbl
                                    or lbl.startswith(f"{letter}.") or lbl.startswith(f"{letter})")
                                    or lbl == letter or lbl.startswith(f"choice {letter}")):
                                    matched_choice = ch
                                    break
                        if matched_choice:
                            break

                if matched_choice:
                    synth_act = {
                        "type": "click",
                        "x": matched_choice.get("x"),
                        "y": matched_choice.get("y"),
                        "box_2d": matched_choice.get("box_2d"),
                        "description": f"Select {matched_choice.get('label', 'chosen option')}",
                        "in_scrolled_view": False,
                        "choices": all_choices
                    }
                    _process_action(synth_act, context_label="Synthesized Choice")
                    result["actions"] = [synth_act]
                    logger.info(f"Synthesized click action from matched choice '{matched_choice.get('label')}': screen=({synth_act.get('screen_x')}, {synth_act.get('screen_y')})")

        # In single-view captures, strictly force in_scrolled_view to False on ALL final actions
        if not has_multi_view and isinstance(result.get("actions"), list):
            for act in result["actions"]:
                act["in_scrolled_view"] = False

        # Normalize aliases if present
        if "submit_button" in result and not result.get("check_button"):
            s_btn = result["submit_button"]
            if isinstance(s_btn, dict):
                s_desc = str(s_btn.get("description", "")).lower()
                is_final_submit = any(k in s_desc for k in ["quiz", "assignment", "turn in", "finish", "all", "complete"])
                if not is_final_submit and any(k in s_desc for k in ["check", "verify", "answer"]):
                    result["check_button"] = s_btn
        if "continue_button" in result and not result.get("next_button"):
            result["next_button"] = result["continue_button"]

        # Map check_button, next_button, submit_button, reference_button, close_button, and dropdown_button coordinates
        for btn_key in ["check_button", "next_button", "submit_button", "reference_button", "close_button", "dropdown_button"]:
            btn = result.get(btn_key)
            if btn and isinstance(btn, dict):
                _resolve_mark_or_snap(btn, btn_key)
                if "box_2d" in btn and isinstance(btn["box_2d"], (list, tuple)) and len(btn["box_2d"]) == 4:
                    b = btn["box_2d"]
                    ymin, xmin, ymax, xmax = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                    if max(ymin, xmin, ymax, xmax) <= 1.0:
                        ymin *= 1000.0
                        xmin *= 1000.0
                        ymax *= 1000.0
                        xmax *= 1000.0
                    btn["box_2d"] = [ymin, xmin, ymax, xmax]
                    btn["x"] = (xmin + xmax) / 2.0
                    btn["y"] = (ymin + ymax) / 2.0
                    bx1, by1 = _translate_point(xmin, ymin)
                    bx2, by2 = _translate_point(xmax, ymax)
                    btn["box_screen"] = [min(bx1, bx2), min(by1, by2), max(bx1, bx2), max(by1, by2)]
                    btn["box_width"] = abs(bx2 - bx1)
                    btn["box_height"] = abs(by2 - by1)

                if "x" in btn and "y" in btn:
                    sx, sy = _translate_point(float(btn["x"]), float(btn["y"]))
                    btn["screen_x"] = sx
                    btn["screen_y"] = sy
                    logger.info(f"Target mapped [{btn_key}]: model=({btn['x']}, {btn['y']}) -> screen=({sx}, {sy})")

        # Propagate in_scrolled_view to navigation buttons only when a multi-view scrolled view actually exists
        has_scrolled_actions = any(bool(a.get("in_scrolled_view")) for a in result.get("actions", []))
        for nav_key in ["check_button", "next_button", "submit_button", "reference_button", "close_button", "dropdown_button"]:
            btn = result.get(nav_key)
            if btn and isinstance(btn, dict):
                if not has_multi_view:
                    # In single-view captures, no scrolled lower view exists; everything is in the primary view
                    btn["in_scrolled_view"] = False
                elif "in_scrolled_view" not in btn:
                    # If multi-view was captured, only propagate if actions explicitly targeted the scrolled lower view AND button is in lower view
                    by = float(btn.get("y", 1000))
                    btn["in_scrolled_view"] = bool(has_scrolled_actions and by >= 350)

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

            # INVARIANT: An unsubmitted question with 0 actions can NEVER be marked ready to advance
            # UNLESS the answer is already filled out and confirmed right on screen (needs_action is False).
            if (
                result.get("evaluation_status") == "unsubmitted"
                and not result.get("actions")
                and not any(itm.get("actions") for itm in items if isinstance(itm, dict))
                and result.get("needs_action") is not False
            ):
                q_text = str(result.get("question", "")).strip().lower()
                is_interstitial = (
                    not q_text
                    or any(w in q_text for w in ["continue", "next question", "section complete", "ready to move", "interstitial"])
                    and not any(w in q_text for w in ["what", "which", "solve", "find", "choose", "select", "calculate", "evaluate", "how", "simplify", "graph", "equation"])
                )
                if not is_interstitial:
                    logger.warning("Unsubmitted question has zero actions and needs action. Forcing ready_to_advance = False to prevent skipping unanswered question.")
                    result["ready_to_advance"] = False

        result.setdefault("platform_feedback", "")

        if not result.get("answer"):
            result["answer"] = result.get("summary") or "Answer determined"

        if not result.get("question"):
            result["question"] = result.get("summary") or "Question detected"

    def generate_text_response(
        self,
        prompt: str,
        system_instruction: str = "",
        model_override: Optional[str] = None
    ) -> str:
        """
        Sends a pure text generation query to the configured AI provider.
        Utilizes model_override if provided (e.g. gemini-3.8-flash).
        """
        if not self.api_key:
            raise ValueError("API Key is empty.")

        target_model = (model_override or self.model_name).strip()
        logger.debug(f"generate_text_response: calling provider '{self.provider}' model '{target_model}'...")

        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload: Dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7
                }
            }
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error("Gemini", resp.status_code, resp.text)
                logger.error(f"Gemini text generation failed: {err_msg}")
                raise RuntimeError(err_msg)

            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response structure from Gemini: {data}")

        elif self.provider in ["openai", "custom"]:
            base_url = self.custom_base_url if self.provider == "custom" else "https://api.openai.com/v1"
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": 0.7
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error(self.provider.title(), resp.status_code, resp.text)
                logger.error(f"{self.provider} text generation failed: {err_msg}")
                raise RuntimeError(err_msg)

            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response structure from {self.provider}: {data}")

        elif self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": target_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.7
            }
            if system_instruction:
                payload["system"] = system_instruction

            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_msg = format_api_error("Anthropic", resp.status_code, resp.text)
                logger.error(f"Anthropic text generation failed: {err_msg}")
                raise RuntimeError(err_msg)

            data = resp.json()
            try:
                return data["content"][0]["text"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response structure from Anthropic: {data}")

        raise ValueError(f"Unsupported AI provider: {self.provider}")

    def extract_text_from_image(
        self,
        base64_image: str,
        prompt: str = "Extract all text, rubric criteria, scoring guidelines, and assignment instructions from this image verbatim without markdown wrapping."
    ) -> str:
        """Extracts text content and instructions from an image for rubric ingestion."""
        if not self.api_key:
            raise ValueError("API Key is empty.")

        if self.provider == "gemini":
            return self._call_gemini(base64_image, prompt)
        elif self.provider == "openai":
            return self._call_openai(base64_image, prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(base64_image, prompt)
        elif self.provider == "custom":
            return self._call_custom(base64_image, prompt)
        return ""
