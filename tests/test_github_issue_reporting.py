"""
Unit tests for the Automated Worker GitHub Issue Reporting and Secret Sanitization system.
Validates that:
1. API keys (Gemini, OpenAI, Anthropic, Bearer, etc.) are strictly redacted.
2. Personal user path identifiers (e.g. C:\\Users\\<username>\\...) and emails are sanitized.
3. GitHub issue URL is properly formatted matching the repository bug template.
4. App version, AI model, and error logs are correctly integrated.
"""

import os
import sys
import unittest
import urllib.parse

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AppConfig, APP_VERSION, GITHUB_REPO
from core.error_handler import (
    ErrorDiagnostic,
    create_error_diagnostic,
    sanitize_sensitive_info,
    generate_github_issue_url,
)


class TestGitHubIssueReporting(unittest.TestCase):
    """Unit tests for GitHub bug draft URL generation and secret redaction."""

    def test_sanitize_sensitive_info_keys(self):
        """Verify configured keys and regex patterns are completely masked."""
        fake_config = AppConfig(
            gemini_api_key="AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q",
            openai_api_key="sk-proj-1234567890abcdefghijklmnopqrstuvwxyz",
            anthropic_api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz-AA",
            custom_api_key="my_super_secret_custom_token_123"
        )

        raw_text = (
            "Failed calling Gemini with key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q and "
            "OpenAI fallback sk-proj-1234567890abcdefghijklmnopqrstuvwxyz. "
            "Also tested Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token and "
            "anthropic sk-ant-api03-abcdefghijklmnopqrstuvwxyz-AA. "
            "Custom key was my_super_secret_custom_token_123."
        )

        sanitized = sanitize_sensitive_info(raw_text, config=fake_config)

        self.assertNotIn("AIzaSy", sanitized)
        self.assertNotIn("sk-proj-", sanitized)
        self.assertNotIn("sk-ant-", sanitized)
        self.assertNotIn("my_super_secret_custom_token_123", sanitized)
        self.assertTrue("[REDACTED_GEMINI_KEY]" in sanitized or "[REDACTED_KEY]" in sanitized)
        self.assertTrue("[REDACTED_OPENAI_KEY]" in sanitized or "[REDACTED_KEY]" in sanitized)
        self.assertTrue("[REDACTED_TOKEN]" in sanitized or "[REDACTED_SECRET]" in sanitized)

    def test_sanitize_sensitive_info_personal_info(self):
        """Verify local user path and email addresses are masked."""
        raw_path_text = r"Error in file C:\Users\jacob\OneDrive\Desktop\Coding\AVA\test.py: line 42. Contact dev@schoolassistant.org"
        sanitized = sanitize_sensitive_info(raw_path_text)

        self.assertNotIn("dev@schoolassistant.org", sanitized)
        self.assertIn("[REDACTED_EMAIL]", sanitized)
        self.assertTrue(r"C:\Users\jacob" not in sanitized or r"C:\Users\[USERNAME]" in sanitized)

    def test_generate_github_issue_url_format(self):
        """Verify generated URL matches GitHub issue query schema and contains required metadata."""
        cfg = AppConfig(
            ai_provider="gemini",
            model_name="gemini-3.8-flash",
            gemini_api_key="AIzaSySECRETKEYDONOTEXPOSE1234567890AB"
        )

        diag = ErrorDiagnostic(
            title="ResourceExhausted (429)",
            message="Quota exceeded for model gemini-3.8-flash. Key AIzaSySECRETKEYDONOTEXPOSE1234567890AB exhausted.",
            exception_type="RateLimitError",
            traceback_str='File "C:\\Users\\jacob\\main.py", line 12, in solve\n  raise RateLimitError("Rate limit exceeded")',
            timestamp="2026-09-21 02:00:00",
            component="Automated Worker",
            troubleshooting_hint="Wait 30-60s or switch to gemini-3.5-flash-lite."
        )

        url = generate_github_issue_url(diag, config=cfg)

        # 1. Target URL check
        expected_base = f"https://github.com/{GITHUB_REPO}/issues/new?"
        self.assertTrue(url.startswith(expected_base))

        # 2. Parse query parameters
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        self.assertIn("title", params)
        self.assertIn("body", params)
        self.assertIn("labels", params)

        self.assertEqual(params["labels"], ["bug"])
        title = params["title"][0]
        body = params["body"][0]

        self.assertEqual(title, "BUG: [Automated Worker] ResourceExhausted (429)")
        self.assertIn("**Describe the Bug**", body)
        self.assertIn("**Desktop Environment:**", body)
        self.assertIn(f"App Version: {APP_VERSION}", body)
        self.assertIn("AI Provider: gemini", body)
        self.assertIn("AI Model: gemini-3.8-flash", body)
        self.assertIn("**Additional Context / Error Traceback:**", body)

        # 3. Privacy / Redaction verification
        self.assertNotIn("AIzaSy", body)
        self.assertNotIn("AIzaSy", title)
        self.assertTrue("jacob" not in body.lower() or "[USERNAME]" in body)

    def test_diagnostic_object_methods(self):
        """Verify ErrorDiagnostic convenience methods."""
        try:
            raise ValueError("Testing error dispatch with sk-1234567890abcdef1234567890")
        except Exception as e:
            diag = create_error_diagnostic(e, component="Automated Worker")

        sanitized_text = diag.to_sanitized_clipboard_text()
        self.assertNotIn("sk-", sanitized_text)
        self.assertIn("Traceback", sanitized_text)

        issue_url = diag.to_github_issue_url()
        self.assertIn("https://github.com/", issue_url)
        self.assertIn("ValueError", issue_url)


if __name__ == "__main__":
    unittest.main()
