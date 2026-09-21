"""
Error Diagnostic and Troubleshooting System for AVA School Assistant 2.
Captures full tracebacks, classifies error types, and generates actionable
troubleshooting recommendations for debug users and developers.
"""

import os
import re
import sys
import time
import urllib.parse
import platform
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

    def to_sanitized_clipboard_text(self, config: Optional[Any] = None) -> str:
        """Returns a sanitized markdown report guaranteed to contain no keys or personal info."""
        raw = self.to_clipboard_text()
        return sanitize_sensitive_info(raw, config=config)

    def to_github_issue_url(self, config: Optional[Any] = None, repo: Optional[str] = None) -> str:
        """Generates a pre-filled GitHub issue URL matching the bug report template."""
        return generate_github_issue_url(self, config=config, repo=repo)

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


def sanitize_sensitive_info(text: str, config: Optional[Any] = None) -> str:
    """
    Strips all API keys, bearer tokens, passwords, private secrets,
    usernames in paths, hostnames, and email addresses from the string.
    Ensures zero secret leakage when copying or transmitting error logs.
    """
    if not text:
        return ""

    sanitized = text

    # 1. Redact known API keys from configuration if provided
    if config:
        candidate_keys = [
            getattr(config, "api_key", ""),
            getattr(config, "gemini_api_key", ""),
            getattr(config, "openai_api_key", ""),
            getattr(config, "anthropic_api_key", ""),
            getattr(config, "custom_api_key", ""),
        ]
        if isinstance(config, dict):
            for k in ("api_key", "gemini_api_key", "openai_api_key", "anthropic_api_key", "custom_api_key"):
                candidate_keys.append(config.get(k, ""))

        for key in candidate_keys:
            if key and isinstance(key, str) and len(key.strip()) >= 6:
                sanitized = sanitized.replace(key.strip(), "[REDACTED_KEY]")

    # 2. Redact known API Key Token patterns (Google AI Studio, OpenAI, Anthropic, Bearer)
    sanitized = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_GEMINI_KEY]", sanitized)
    sanitized = re.sub(r"sk-(?:proj-)?[a-zA-Z0-9\-_]{20,}", "[REDACTED_OPENAI_KEY]", sanitized)
    sanitized = re.sub(r"sk-ant-[a-zA-Z0-9\-_]{20,}", "[REDACTED_ANTHROPIC_KEY]", sanitized)
    sanitized = re.sub(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{15,}", "Bearer [REDACTED_TOKEN]", sanitized)
    sanitized = re.sub(
        r"""(?i)(["']?(?:api[_-]?key|secret|token|password|auth|authorization)["']?\s*[:=]\s*["']?)([^"',\s]{6,})(["']?)""",
        r"\1[REDACTED_SECRET]\3",
        sanitized
    )

    # 3. Redact personal user paths (Windows: C:\\Users\\<username>\\... or Linux/macOS: /home/<username>/...)
    usernames = set()
    for var in ("USERNAME", "USER", "LOGNAME"):
        val = os.environ.get(var)
        if val and len(val.strip()) >= 2:
            usernames.add(val.strip())
    try:
        import getpass
        u = getpass.getuser()
        if u and len(u.strip()) >= 2:
            usernames.add(u.strip())
    except Exception:
        pass

    for user in usernames:
        sanitized = re.sub(
            rf"(?i)([\\/](?:Users|home)[\\/]){re.escape(user)}([\\/])",
            r"\1[USERNAME]\2",
            sanitized
        )
        sanitized = re.sub(
            rf"([a-zA-Z]:[\\/][^\\/\n\r]+[\\/]){re.escape(user)}([\\/])",
            r"\1[USERNAME]\2",
            sanitized
        )

    # 4. Redact Hostnames / Machine names if present
    hosts = set()
    for var in ("COMPUTERNAME", "HOSTNAME"):
        val = os.environ.get(var)
        if val and len(val.strip()) >= 3:
            hosts.add(val.strip())
    try:
        node = platform.node()
        if node and len(node.strip()) >= 3:
            hosts.add(node.strip())
    except Exception:
        pass

    for host in hosts:
        if host.lower() not in ("localhost", "windows", "desktop", "laptop"):
            sanitized = re.sub(rf"\b{re.escape(host)}\b", "[HOSTNAME]", sanitized)

    # 5. Redact Email addresses
    sanitized = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]", sanitized)

    return sanitized


def generate_github_issue_url(
    diagnostic: ErrorDiagnostic,
    config: Optional[Any] = None,
    repo: Optional[str] = None,
    max_body_chars: int = 3500
) -> str:
    """
    Builds a pre-filled GitHub issue URL matching .github/ISSUE_TEMPLATE/bug_report.md.
    Pre-populates the issue title, environment details (OS, version, AI model),
    troubleshooting recommendations, and sanitized error traceback.
    Guarantees no API keys or personal information are included.
    """
    target_repo = repo
    if not target_repo and config and hasattr(config, "github_repo"):
        target_repo = config.github_repo
    if not target_repo:
        try:
            from config import GITHUB_REPO
            target_repo = GITHUB_REPO
        except ImportError:
            target_repo = "JustJade2007/AVA-School-Assistant-2"

    app_version = "2.2.1.a"
    try:
        from config import APP_VERSION
        app_version = APP_VERSION
    except ImportError:
        pass

    ai_provider = "gemini"
    model_name = "gemini-3.8-flash"
    if config:
        ai_provider = getattr(config, "ai_provider", ai_provider)
        model_name = getattr(config, "model_name", model_name)
        if isinstance(config, dict):
            ai_provider = config.get("ai_provider", ai_provider)
            model_name = config.get("model_name", model_name)

    os_info = f"{platform.system()} {platform.release()}"

    clean_title = sanitize_sensitive_info(diagnostic.title, config=config).strip()
    clean_title = clean_title.replace("\n", " ").replace("\r", "")
    if len(clean_title) > 90:
        clean_title = clean_title[:87] + "..."

    clean_message = sanitize_sensitive_info(diagnostic.message, config=config).strip()
    clean_hint = sanitize_sensitive_info(diagnostic.troubleshooting_hint, config=config).strip()
    clean_tb = sanitize_sensitive_info(diagnostic.traceback_str or "No traceback attached.", config=config).strip()

    body_header = (
        f"**Describe the Bug**\n"
        f"Automated Worker encountered an error during {diagnostic.component}:\n"
        f"> {clean_message}\n\n"
        f"**To Reproduce**\n"
        f"1. Launched Automated Worker (HUD Mode).\n"
        f"2. Started screen solving / task execution.\n"
        f"3. Encountered error in component: `{diagnostic.component}`.\n\n"
        f"**Expected Behavior**\n"
        f"Expected screen parsing and action execution to succeed without exceptions.\n\n"
        f"**Desktop Environment:**\n"
        f"- OS: {os_info}\n"
        f"- App Version: {app_version}\n"
        f"- AI Provider: {ai_provider}\n"
        f"- AI Model: {model_name}\n\n"
        f"**School Work Context (if applicable):**\n"
        f"- Feature involved: Automated Worker (HUD Overlay)\n"
        f"- Exception Type: `{diagnostic.exception_type}`\n"
        f"- Timestamp: `{diagnostic.timestamp}`\n\n"
        f"**Troubleshooting Suggestion:**\n"
        f"{clean_hint}\n\n"
        f"**Additional Context / Error Traceback:**\n"
    )

    overhead = len(body_header) + 20
    available_tb_len = max(500, max_body_chars - overhead)

    if len(clean_tb) > available_tb_len:
        tb_snippet = clean_tb[-available_tb_len:]
        clean_tb = f"... [Earlier frames truncated for URL length. Full log copied to clipboard] ...\n{tb_snippet}"

    body_full = f"{body_header}```text\n{clean_tb}\n```\n"
    final_body = sanitize_sensitive_info(body_full, config=config)

    issue_title = f"BUG: [{diagnostic.component}] {clean_title}"
    params = {
        "title": issue_title,
        "body": final_body,
        "labels": "bug"
    }

    query_str = urllib.parse.urlencode(params)
    return f"https://github.com/{target_repo}/issues/new?{query_str}"
