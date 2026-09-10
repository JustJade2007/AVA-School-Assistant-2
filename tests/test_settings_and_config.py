"""
Unit and integration tests for SettingsWindow UI, model autofill, and ConfigManager persistence.
"""

import os
import json
import tempfile
import unittest
import customtkinter as ctk

from config import (
    AppConfig,
    ConfigManager,
    AVAILABLE_MODELS,
    get_base_directory,
    get_config_file_path,
    get_default_config_file_path,
)
from ui.settings_view import SettingsWindow


class TestSettingsAndConfig(unittest.TestCase):
    """Tests for configuration lifecycle, path resolution, and SettingsWindow UI."""

    def test_path_resolution_and_no_internal_leak(self):
        """Verifies that path resolution stays in root/base and never points into _internal."""
        base_dir = get_base_directory()
        self.assertFalse(base_dir.endswith("_internal"))
        
        cfg_path = get_config_file_path()
        self.assertTrue(cfg_path.endswith("config.json"))
        self.assertNotIn("_internal", cfg_path)

        default_path = get_default_config_file_path()
        self.assertTrue(default_path.endswith("config.default.json"))
        self.assertTrue(os.path.exists(default_path), "config.default.json must exist as template")

    def test_default_config_template_structure(self):
        """Verifies that config.default.json contains all essential fields and safe empty credentials."""
        default_path = get_default_config_file_path()
        with open(default_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("ai_provider", data)
        self.assertIn("model_name", data)
        self.assertIn("api_key", data)
        # Verify secrets are empty in the template
        self.assertEqual(data["api_key"], "")
        self.assertIn("hotkeys", data)
        self.assertIn("trigger_solve", data["hotkeys"])

    def test_settings_window_model_autofill_and_provider_switch(self):
        """Tests that SettingsWindow initializes without error and model autofill works."""
        root = ctk.CTk()
        root.withdraw()
        try:
            win = SettingsWindow(master=root)
            
            # 1. Check that hotkey_entries is present and populated
            self.assertIsInstance(win.hotkey_entries, dict)
            self.assertIn("trigger_solve", win.hotkey_entries)
            self.assertIn("close_app", win.hotkey_entries)
            
            # 2. Check combo_model is initialized and populated with models
            provider = win.combo_provider.get().lower()
            expected_models = AVAILABLE_MODELS.get(provider, [])
            combo_values = win.combo_model.cget("values")
            self.assertEqual(list(combo_values), expected_models)
            
            # 3. Test switching provider to 'openai'
            win.combo_provider.set("openai")
            win._on_provider_changed("openai")
            self.assertEqual(win.combo_model.get(), "gpt-4o")
            self.assertIn("gpt-4o", win.combo_model.cget("values"))
            
            # 4. Test switching provider to 'anthropic'
            win.combo_provider.set("anthropic")
            win._on_provider_changed("anthropic")
            self.assertEqual(win.combo_model.get(), "claude-3-7-sonnet-latest")
            
            # 5. Test manual autofill button handler
            win.combo_model.set("")
            win._autofill_default_model()
            self.assertEqual(win.combo_model.get(), "claude-3-7-sonnet-latest")

            win.destroy()
        finally:
            root.destroy()

    def test_settings_save_and_reload_persistence(self):
        """Tests that modifying widgets in SettingsWindow saves and persists to ConfigManager."""
        root = ctk.CTk()
        root.withdraw()
        try:
            cm = ConfigManager()
            original_reading_delay = cm.config.base_reading_time

            win = SettingsWindow(master=root)
            
            # Change a numeric setting
            test_val = 6.5
            win.slider_base_reading.set(test_val)
            
            # Save and close
            win._save_and_close()

            # Verify through ConfigManager
            self.assertEqual(cm.config.base_reading_time, test_val)
            
            # Re-read from disk
            cm.reload()
            self.assertEqual(cm.config.base_reading_time, test_val)

            # Revert back to original
            cm.update(base_reading_time=original_reading_delay)
            self.assertEqual(cm.config.base_reading_time, original_reading_delay)
        finally:
            root.destroy()

    def test_gemini_api_key_persistence_and_reload(self):
        """Tests that saving Gemini API key via SettingsWindow persists to disk and reloads cleanly."""
        root = ctk.CTk()
        root.withdraw()
        try:
            cm = ConfigManager()
            original_data = dict(cm.config.to_dict())

            win = SettingsWindow(master=root)
            win.combo_provider.set("gemini")
            win._on_provider_changed("gemini")

            test_gemini_key = "AQ.TestGeminiPersistenceKey12345"
            win.entry_api_key.delete(0, "end")
            win.entry_api_key.insert(0, test_gemini_key)

            win._save_and_close()

            # Verify in-memory config
            self.assertEqual(cm.config.gemini_api_key, test_gemini_key)
            self.assertEqual(cm.config.api_key, test_gemini_key)
            self.assertEqual(cm.config.get_api_key_for_provider("gemini"), test_gemini_key)

            # Re-read fresh from disk
            cm.reload()
            self.assertEqual(cm.config.gemini_api_key, test_gemini_key)
            self.assertEqual(cm.config.api_key, test_gemini_key)

            # Restore original
            cm.config = AppConfig.from_dict(original_data)
            cm.save()
        finally:
            root.destroy()

    def test_provider_switching_preserves_distinct_keys(self):
        """Tests that switching providers retains each provider's distinct API key without overwriting."""
        root = ctk.CTk()
        root.withdraw()
        try:
            cm = ConfigManager()
            original_data = dict(cm.config.to_dict())

            win = SettingsWindow(master=root)

            # 1. Enter Gemini key
            win.combo_provider.set("gemini")
            win._on_provider_changed("gemini")
            win.entry_api_key.delete(0, "end")
            win.entry_api_key.insert(0, "AIzaSy_Gemini_Key_999")

            # 2. Switch to OpenAI and enter OpenAI key
            win.combo_provider.set("openai")
            win._on_provider_changed("openai")
            win.entry_api_key.delete(0, "end")
            win.entry_api_key.insert(0, "sk-proj-OpenAI_Key_888")

            # 3. Switch back to Gemini - should restore Gemini key in input
            win.combo_provider.set("gemini")
            win._on_provider_changed("gemini")
            self.assertEqual(win.entry_api_key.get(), "AIzaSy_Gemini_Key_999")

            # 4. Save and close
            win._save_and_close()

            # Verify both are preserved in config
            self.assertEqual(cm.config.gemini_api_key, "AIzaSy_Gemini_Key_999")
            self.assertEqual(cm.config.openai_api_key, "sk-proj-OpenAI_Key_888")

            # Re-read from disk
            cm.reload()
            self.assertEqual(cm.config.gemini_api_key, "AIzaSy_Gemini_Key_999")
            self.assertEqual(cm.config.openai_api_key, "sk-proj-OpenAI_Key_888")

            # Restore original
            cm.config = AppConfig.from_dict(original_data)
            cm.save()
        finally:
            root.destroy()

    def test_window_wm_delete_window_triggers_auto_save(self):
        """Tests that closing SettingsWindow via window titlebar 'X' saves all modified settings."""
        root = ctk.CTk()
        root.withdraw()
        try:
            cm = ConfigManager()
            original_data = dict(cm.config.to_dict())

            win = SettingsWindow(master=root)
            test_key = "AQ.TestWindowCloseAutoSaveKey999"
            win.entry_api_key.delete(0, "end")
            win.entry_api_key.insert(0, test_key)

            test_val = 5.0
            win.slider_base_reading.set(test_val)

            # Simulate clicking the 'X' button
            win._on_window_close()

            self.assertEqual(cm.config.gemini_api_key, test_key)
            self.assertEqual(cm.config.api_key, test_key)
            self.assertEqual(cm.config.base_reading_time, test_val)

            cm.reload()
            self.assertEqual(cm.config.gemini_api_key, test_key)
            self.assertEqual(cm.config.api_key, test_key)
            self.assertEqual(cm.config.base_reading_time, test_val)

            # Restore original
            cm.config = AppConfig.from_dict(original_data)
            cm.save()
        finally:
            root.destroy()

    def test_from_dict_and_get_api_key_fallbacks(self):
        """Tests that AppConfig.from_dict parses aliases and fallback resolution functions correctly."""
        # Test direct aliases
        cfg = AppConfig.from_dict({"GOOGLE_API_KEY": "test_google_key", "ai_provider": "gemini"})
        self.assertEqual(cfg.gemini_api_key, "test_google_key")
        self.assertEqual(cfg.get_api_key_for_provider("gemini"), "test_google_key")

        # Test generic api_key propagation
        cfg2 = AppConfig.from_dict({"api_key": "test_generic_key", "ai_provider": "gemini"})
        self.assertEqual(cfg2.gemini_api_key, "test_generic_key")
        self.assertEqual(cfg2.get_api_key_for_provider("gemini"), "test_generic_key")

        # Test export retains both
        dict_data = cfg2.to_dict()
        self.assertEqual(dict_data["api_key"], "test_generic_key")
        self.assertEqual(dict_data["gemini_api_key"], "test_generic_key")


if __name__ == "__main__":
    unittest.main()

