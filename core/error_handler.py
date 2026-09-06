"""
Error Diagnostic and Troubleshooting System for AVA School Assistant 2.
Captures full tracebacks, classifies error types, and generates actionable
troubleshooting recommendations for debug users and developers.
"""

import sys
import time
import traceback
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class ErrorDiagnostic:
    """Rich structured diagnostic report for any caught exception."""
    title: str
    message: str
    exception_type: str
    traceback_str: str
    timestamp: str
    component: str
    troubleshooting_hint: str
    raw_details: Optional[str] = None

    def to_summary_text(self) -> str:
        """Returns a clean multi-line summary suitable for HUD and quick review."""
        return f"[{self.component}] {self.title}: {self.message}"

    def to_clipboard_text(self) -> str:
        """Generates a complete Markdown error report for clipboard copying / bug reporting."""
        lines = [
            "================ AVA ERROR DIAGNOSTIC REPORT ================",
            f"Timestamp:      {self.timestamp}",
            f"Component:      {self.component}",
            f"Exception Type: {self.exception_type}",
            f"Summary:        {self.title}",
            f"Message:        {self.message}",
            "",
            "--- Troubleshooting Suggestion ---",
            self.troubleshooting_hint,
            "",
            "--- Python Traceback ---",
            self.traceback_str or "No traceback available.",
        ]
        if self.raw_details:
            lines.extend([
                "",
                "--- Raw API / Context Payload ---",
                self.raw_details
            ])
        lines.append("=============================================================")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_troubleshooting_hint(e: Exception, message: str, component: str) -> str:
    """Analyzes the exception type, message content, and component to recommend actionable fixes."""
    msg_lower = message.lower()
    exc_name = type(e).__name__

    # 1. API Key / Authentication Issues
    if "api key" in msg_lower or "api_key_invalid" in msg_lower or "401" in msg_lower or "unauthorized" in msg_lower:
        return (
            "💡 Authentication Failed:\n"
            "• Verify your API key in Settings (⚙) -> '🤖 AI & Model'.\n"
            "• Ensure there are no accidental spaces or linebreaks pasted.\n"
            "• Click '🔗 Test API Connection' to confirm the key works."
        )

    # 2. Permission / Disabled API
    if "403" in msg_lower or "permission_denied" in msg_lower or "forbidden" in msg_lower:
        return (
            "💡 Permission Denied (HTTP 403):\n"
            "• Ensure the selected model is enabled for your Google Cloud or OpenAI project.\n"
            "• Check if your API key has IP restrictions or API service restrictions enabled."
        )

    # 3. Rate Limit / Quota Exhaustion
    if "429" in msg_lower or "resource_exhausted" in msg_lower or "quota" in msg_lower or "rate limit" in msg_lower:
        return (
            "💡 Rate Limit or Quota Exceeded (HTTP 429):\n"
            "• The model rate limit or daily free-tier quota has been exhausted.\n"
            "• Wait 30-60 seconds and retry, or switch to a faster model (e.g. gemini-3.5-flash-lite or gemini-3.6-flash).\n"
            "• Verify your billing or quota usage in the provider's developer console."
        )

    # 4. Network / Connectivity Issues
    if "connection" in msg_lower or "getaddrinfo failed" in msg_lower or "timeout" in msg_lower or "timed out" in msg_lower:
        return (
            "💡 Network Connection Error:\n"
            "• Unable to reach the AI endpoint. Check your internet connection.\n"
            "• If using a Custom Base URL, ensure the host and port are correct and reachable.\n"
            "• Check if a firewall or VPN is blocking outbound HTTPS requests."
        )

    # 5. Screen Capture Failures
    if "unable to capture screen" in msg_lower or "bitblt" in msg_lower or "screen" in component.lower():
        return (
            "💡 Screen Capture Restricted:\n"
            "• Windows may have locked your desktop session or display.\n"
            "• Ensure your physical monitor is active and AVA is running in your interactive user session.\n"
            "• If using multiple monitors, verify the monitor index in Capture settings."
        )

    # 6. JSON Parse / Output Formatting
    if "json" in msg_lower or "jsondecodeerror" in exc_name.lower():
        return (
            "💡 AI Response JSON Parsing Failed:\n"
            "• The AI model generated text that could not be parsed as valid JSON.\n"
            "• This occasionally happens with smaller or creative models. Retrying (F8) usually succeeds.\n"
            "• Recommended models: Google Gemini 3.6 Flash, Gemini 3.5 Flash-Lite, OpenAI GPT-4o, or Claude 3.7 Sonnet."
        )

    # 7. Hotkey / Keyboard Hook
    if "hotkey" in component.lower() or "pynput" in msg_lower:
        return (
            "💡 Hotkey Binding Conflict:\n"
            "• The requested hotkey might conflict with another background application or Windows shortcut.\n"
            "• Check Settings (⚙) -> '⌨ Hotkeys' and reassign conflicting key combinations."
        )

    # 8. Anti-Capture Cloaking
    if "displayaffinity" in msg_lower or "cloaking" in msg_lower:
        return (
            "💡 Anti-Capture Cloaking Warning:\n"
            "• SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) requires Windows 10 (version 2004+) or Windows 11.\n"
            "• You can disable Anti-Capture in Settings -> '🛡️ Anti-Capture & HUD' if running on unsupported setups."
        )

    # Default fallback
    return (
        "💡 General Troubleshooting:\n"
        "• Review the stack trace below for the exact failure line.\n"
        "• Enable Debug Mode in Settings to see verbose API payload logs.\n"
        "• Use '📋 Copy Error Report' to copy this diagnostic for debugging."
    )


def create_error_diagnostic(
    e: Exception,
    component: str = "Assistant Engine",
    raw_details: Optional[str] = None
) -> ErrorDiagnostic:
    """Factory function to build a complete ErrorDiagnostic object from an exception."""
    exc_type = type(e).__name__
    raw_msg = str(e).strip()

    # Provide a meaningful message if str(e) is empty
    message = raw_msg if raw_msg else f"Unhandled {exc_type} with no message text."

    # Generate title
    if exc_type == "RuntimeError" and ":" in message:
        title = message.split(":")[0].strip()
    elif ":" in message and len(message.split(":")[0]) < 30:
        title = message.split(":")[0].strip()
    else:
        title = f"{exc_type} in {component}"

    # Capture traceback
    tb_str = traceback.format_exc()
    if not tb_str or tb_str.strip() == "NoneType: None":
        # If called outside an except block, format current stack
        tb_str = "".join(traceback.format_stack()[:-1])

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    hint = generate_troubleshooting_hint(e, message, component)

    return ErrorDiagnostic(
        title=title,
        message=message,
        exception_type=exc_type,
        traceback_str=tb_str,
        timestamp=timestamp,
        component=component,
        troubleshooting_hint=hint,
        raw_details=raw_details
    )
