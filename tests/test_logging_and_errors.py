"""
Automated unit and integration tests for AVA School Assistant 2's
logging and error diagnostic systems.
"""

import unittest
import os
import json
import logging
from config import AppConfig, ConfigManager
from core.logger import (
    get_logger,
    setup_logging,
    set_debug_mode,
    set_log_level,
    is_debug_mode,
    get_log_buffer,
    LogEntry,
    MemoryLogBuffer
)
from core.error_handler import (
    create_error_diagnostic,
    generate_troubleshooting_hint,
    ErrorDiagnostic
)
from core.ai_client import format_api_error, AIClient
from core.assistant_engine import AssistantEngine, EngineState


class TestLoggingAndDiagnostics(unittest.TestCase):

    def setUp(self):
        # Reset logging to default for tests
        setup_logging(log_level="INFO", log_to_file=False, debug_mode=False)

    def test_logger_initialization_and_debug_mode(self):
        logger = get_logger("test")
        self.assertIsNotNone(logger)
        self.assertFalse(is_debug_mode())

        set_debug_mode(True)
        self.assertTrue(is_debug_mode())
        self.assertEqual(logging.getLogger("ava").level, logging.DEBUG)

        set_debug_mode(False)
        self.assertFalse(is_debug_mode())
        self.assertEqual(logging.getLogger("ava").level, logging.INFO)

        set_log_level("WARNING")
        self.assertEqual(logging.getLogger("ava").level, logging.WARNING)

    def test_memory_log_buffer_filtering_and_limits(self):
        buf = MemoryLogBuffer(max_entries=5)

        # Add entries
        buf.append(LogEntry(1.0, "12:00:00.000", "DEBUG", 10, "ava.test", "Debug message"))
        buf.append(LogEntry(2.0, "12:00:01.000", "INFO", 20, "ava.test", "Info message with keyword"))
        buf.append(LogEntry(3.0, "12:00:02.000", "WARNING", 30, "ava.test", "Warning message"))
        buf.append(LogEntry(4.0, "12:00:03.000", "ERROR", 40, "ava.test", "Error message with keyword"))
        buf.append(LogEntry(5.0, "12:00:04.000", "CRITICAL", 50, "ava.test", "Critical issue"))

        # Test count
        entries = buf.get_entries()
        self.assertEqual(len(entries), 5)

        # Test buffer capping
        buf.append(LogEntry(6.0, "12:00:05.000", "INFO", 20, "ava.test", "Overflow entry"))
        entries = buf.get_entries()
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[-1].message, "Overflow entry")

        # Test level filtering
        err_entries = buf.get_entries(level="ERROR")
        self.assertTrue(all(e.level_no >= 40 for e in err_entries))

        # Test search filtering
        keyword_entries = buf.get_entries(search="keyword")
        self.assertEqual(len(keyword_entries), 2)  # Entries 2 and 4 are retained

    def test_memory_log_buffer_listeners(self):
        buf = MemoryLogBuffer(max_entries=10)
        received = []

        def listener(entry: LogEntry):
            received.append(entry)

        buf.add_listener(listener)
        test_entry = LogEntry(1.0, "12:00:00.000", "INFO", 20, "ava.test", "Hello Listener")
        buf.append(test_entry)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message, "Hello Listener")

        buf.remove_listener(listener)
        buf.append(LogEntry(2.0, "12:00:01.000", "INFO", 20, "ava.test", "Second Message"))
        self.assertEqual(len(received), 1)

    def test_error_diagnostic_generation_and_hints(self):
        # 1. Test API key authentication hint
        try:
            raise ValueError("Gemini API Error 401: API_KEY_INVALID")
        except Exception as e:
            diag = create_error_diagnostic(e, component="AI Vision (Gemini)")
            self.assertEqual(diag.exception_type, "ValueError")
            self.assertIn("Authentication Failed", diag.troubleshooting_hint)
            self.assertIn("API key", diag.troubleshooting_hint)
            self.assertIn("Traceback", diag.to_clipboard_text())

        # 2. Test Rate Limit hint
        try:
            raise RuntimeError("OpenAI API Error 429: Rate limit exceeded or quota exhausted")
        except Exception as e:
            diag = create_error_diagnostic(e, component="AI Vision (OpenAI)")
            self.assertIn("Rate Limit", diag.troubleshooting_hint)
            self.assertIn("HTTP 429", diag.troubleshooting_hint)

        # 3. Test JSONDecodeError hint
        try:
            json.loads("{ invalid json content }")
        except Exception as e:
            diag = create_error_diagnostic(e, component="JSON Parser")
            self.assertIn("JSON", diag.troubleshooting_hint)
            self.assertIn("JSONDecodeError", diag.exception_type)

        # 4. Test Screen Capture hint
        try:
            raise RuntimeError("Unable to capture screen: BitBlt failed")
        except Exception as e:
            diag = create_error_diagnostic(e, component="Screen Capture")
            self.assertIn("Screen Capture Restricted", diag.troubleshooting_hint)

    def test_ai_client_format_api_error(self):
        # Gemini structured response
        gemini_json = json.dumps({
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
                "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo"}]
            }
        })
        formatted_gemini = format_api_error("Gemini", 400, gemini_json)
        self.assertIn("API key not valid", formatted_gemini)
        self.assertIn("INVALID_ARGUMENT", formatted_gemini)
        self.assertIn("400", formatted_gemini)

        # OpenAI structured response
        openai_json = json.dumps({
            "error": {
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "type": "insufficient_quota",
                "code": "insufficient_quota"
            }
        })
        formatted_openai = format_api_error("OpenAI", 429, openai_json)
        self.assertIn("exceeded your current quota", formatted_openai)
        self.assertIn("insufficient_quota", formatted_openai)

        # Non-JSON fallback
        raw_text = "<html>502 Bad Gateway</html>"
        formatted_raw = format_api_error("Custom", 502, raw_text)
        self.assertIn("502 Bad Gateway", formatted_raw)

    def test_assistant_engine_error_capture_and_dispatch(self):
        engine = AssistantEngine()
        notified_errors = []

        engine.add_error_listener(lambda diag: notified_errors.append(diag))

        # Manually trigger an error state transition
        try:
            raise RuntimeError("Synthetic pipeline failure during test")
        except Exception as e:
            diag = create_error_diagnostic(e, component="Test Pipeline")
            engine.last_error = diag
            engine.set_state(EngineState.ERROR, diag.message)
            engine._notify_error(diag)

        self.assertEqual(engine.state, EngineState.ERROR)
        self.assertIsNotNone(engine.last_error)
        self.assertEqual(engine.last_error.title, "RuntimeError in Test Pipeline")
        self.assertEqual(engine.last_error.message, "Synthetic pipeline failure during test")
        self.assertEqual(len(notified_errors), 1)
        self.assertEqual(notified_errors[0].component, "Test Pipeline")

    def test_config_debug_fields_and_persistence(self):
        cfg = AppConfig(
            debug_mode=True,
            log_level="DEBUG",
            log_to_file=True,
            max_log_entries=1000
        )
        self.assertTrue(cfg.debug_mode)
        self.assertEqual(cfg.log_level, "DEBUG")
        self.assertEqual(cfg.max_log_entries, 1000)

        # Serialization
        d = cfg.to_dict()
        self.assertTrue(d["debug_mode"])
        self.assertEqual(d["log_level"], "DEBUG")
        self.assertEqual(d["max_log_entries"], 1000)

        # Deserialization
        restored = AppConfig.from_dict(d)
        self.assertTrue(restored.debug_mode)
        self.assertEqual(restored.log_level, "DEBUG")
        self.assertEqual(restored.max_log_entries, 1000)

    def test_anthropic_error_formatting(self):
        anthropic_json = json.dumps({
            "error": {
                "type": "invalid_request_error",
                "message": "max_tokens: 1500 is greater than allowed maximum."
            }
        })
        formatted = format_api_error("Anthropic", 400, anthropic_json)
        self.assertIn("Anthropic API Error (400)", formatted)
        self.assertIn("invalid_request_error", formatted)
        self.assertIn("max_tokens", formatted)

    def test_error_diagnostic_formatting_and_dict(self):
        try:
            raise KeyError("missing_field")
        except Exception as e:
            diag = create_error_diagnostic(e, component="JSON Coordinate Parser", raw_details='{"bad": 1}')
            summary = diag.to_summary_text()
            self.assertIn("JSON Coordinate Parser", summary)
            self.assertIn("missing_field", summary)

            d = diag.to_dict()
            self.assertEqual(d["component"], "JSON Coordinate Parser")
            self.assertEqual(d["exception_type"], "KeyError")
            self.assertIn("bad", d["raw_details"])

            report = diag.to_clipboard_text()
            self.assertIn("ERROR DIAGNOSTIC REPORT", report)
            self.assertIn("Raw API / Context Payload", report)


if __name__ == "__main__":
    unittest.main()
