"""
Configuration manager for AVA School Assistant 2.
Handles loading, saving, and updating user preferences and API credentials.
"""

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List


def get_base_directory() -> str:
    """
    Returns the appropriate base application directory.
    If packaged via PyInstaller, returns the directory containing the executable,
    or the project directory if running from dist.
    If running as source script, returns the directory of the script.
    """
    if "AVA_APP_DIR" in os.environ and os.path.exists(os.environ["AVA_APP_DIR"]):
        return os.environ["AVA_APP_DIR"]

    # If running frozen (PyInstaller executable)
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # If running from dist/AVA_School_Assistant_2/, check if parent repository has config.json or main.py
        parent_dir = os.path.dirname(os.path.dirname(exe_dir))
        if os.path.exists(os.path.join(parent_dir, "config.json")) or os.path.exists(os.path.join(parent_dir, "main.py")):
            return parent_dir
        # If running from current working directory
        cwd = os.path.abspath(os.getcwd())
        if os.path.exists(os.path.join(cwd, "config.json")) or os.path.exists(os.path.join(cwd, "config.default.json")):
            return cwd
        return exe_dir

    # Running as standard Python script
    cwd = os.path.abspath(os.getcwd())
    if os.path.exists(os.path.join(cwd, "config.json")) or os.path.exists(os.path.join(cwd, "main.py")):
        return cwd

    # Avoid '_internal' directory if somehow resolved
    file_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(file_dir) == "_internal":
        return os.path.dirname(file_dir)
    return file_dir


def get_config_file_path() -> str:
    """Resolves the active user config.json path across environments."""
    if "AVA_CONFIG_PATH" in os.environ and os.path.exists(os.environ["AVA_CONFIG_PATH"]):
        return os.environ["AVA_CONFIG_PATH"]

    # Check candidate locations in order
    candidates: List[str] = []
    cwd = os.path.abspath(os.getcwd())
    candidates.append(os.path.join(cwd, "config.json"))

    base_dir = get_base_directory()
    if base_dir != cwd:
        candidates.append(os.path.join(base_dir, "config.json"))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "config.json"))

    for path in candidates:
        if os.path.exists(path):
            return path

    # If file doesn't exist yet, prefer saving in CWD if writable, else base_dir
    return os.path.join(base_dir, "config.json")


def get_default_config_file_path() -> str:
    """Resolves the default configuration template path."""
    candidates: List[str] = []
    cwd = os.path.abspath(os.getcwd())
    candidates.append(os.path.join(cwd, "config.default.json"))

    base_dir = get_base_directory()
    candidates.append(os.path.join(base_dir, "config.default.json"))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "config.default.json"))
        internal_dir = os.path.join(exe_dir, "_internal")
        candidates.append(os.path.join(internal_dir, "config.default.json"))

    for path in candidates:
        if os.path.exists(path):
            return path

    return os.path.join(base_dir, "config.default.json")


CONFIG_DIR = get_base_directory()
CONFIG_FILE_PATH = get_config_file_path()
DEFAULT_CONFIG_FILE_PATH = get_default_config_file_path()

# Available default model choices
AVAILABLE_MODELS = {
    "gemini": [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
    ],
    "anthropic": [
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
    "custom": [
        "custom-model",
    ]
}


@dataclass
class AppConfig:
    # AI Provider & Model
    ai_provider: str = "gemini"
    api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    custom_api_key: str = ""
    model_name: str = "gemini-3.6-flash"
    custom_api_base: str = "https://openrouter.ai/api/v1"

    # Execution Behavior
    # autonomous_mode: True = acts automatically; False = asks for confirmation before clicking/typing
    autonomous_mode: bool = False
    # auto_next: True = automatically clicks Next/Submit button after answering
    auto_next: bool = False
    auto_next_delay: float = 2.0
    action_delay: float = 0.5
    # auto_inspect_references: True = inspects modals, reference sheets, or scrolled content if requested by AI
    auto_inspect_references: bool = True

    # Humanization / Anti-bot detection
    humanize_mouse: bool = True
    mouse_speed: float = 0.4
    typing_speed: float = 0.04
    reading_delay_enabled: bool = True
    base_reading_time: float = 4.0
    click_variance_enabled: bool = True
    smart_typos_enabled: bool = True
    local_verification_enabled: bool = True
    chain_multi_parts: bool = True

    # Anti-Screen Capture Cloaking
    anti_capture_enabled: bool = True
    overlay_topmost: bool = True
    overlay_opacity: float = 0.95
    overlay_x: int = 40
    overlay_y: int = 40

    # Capture & Display Resolution Settings
    capture_mode: str = "fullscreen"  # "fullscreen" or "roi"
    roi_box: Optional[list] = None  # [x1, y1, x2, y2] if capture_mode == "roi"
    max_capture_dimension: int = 2880  # 2880, 1920, 2560, or 0 for native unscaled

    # Coordinate Calibration Settings
    calibration_offset_x: int = 0      # Fine-tuning horizontal offset in pixels
    calibration_offset_y: int = 0      # Fine-tuning vertical offset in pixels
    calibration_scale_x: float = 1.0   # Horizontal scaling multiplier
    calibration_scale_y: float = 1.0   # Vertical scaling multiplier
    coordinate_mode: str = "normalized_1000"  # "normalized_1000", "raw_pixels", "auto"

    # Logging and Diagnostics
    debug_mode: bool = False
    log_level: str = "INFO"
    log_to_file: bool = True
    max_log_entries: int = 500

    # Keybinds
    hotkeys: Dict[str, str] = field(default_factory=lambda: {
        "trigger_solve": "F8",
        "confirm_action": "F9",
        "next_question": "F10",
        "pause_resume": "F7",
        "emergency_stop": "F12",
        "toggle_overlay": "F6",
        "close_app": "Ctrl+Shift+Q",
        "snip_solve": "F4"
    })

    def get_api_key_for_provider(self, provider: Optional[str] = None) -> str:
        """Returns the best available API key for the specified or active provider."""
        prov = (provider or self.ai_provider or "gemini").lower()
        if prov == "gemini":
            if self.gemini_api_key and self.gemini_api_key.strip():
                return self.gemini_api_key.strip()
            if self.api_key and self.api_key.strip():
                return self.api_key.strip()
            return os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
        elif prov == "openai":
            if self.openai_api_key and self.openai_api_key.strip():
                return self.openai_api_key.strip()
            if self.api_key and self.api_key.strip() and self.ai_provider == "openai":
                return self.api_key.strip()
            return os.environ.get("OPENAI_API_KEY", "").strip()
        elif prov == "anthropic":
            if self.anthropic_api_key and self.anthropic_api_key.strip():
                return self.anthropic_api_key.strip()
            if self.api_key and self.api_key.strip() and self.ai_provider == "anthropic":
                return self.api_key.strip()
            return os.environ.get("ANTHROPIC_API_KEY", "").strip()
        elif prov == "custom":
            if self.custom_api_key and self.custom_api_key.strip():
                return self.custom_api_key.strip()
            if self.api_key and self.api_key.strip() and self.ai_provider == "custom":
                return self.api_key.strip()
            return os.environ.get("CUSTOM_API_KEY", "").strip()
        return self.api_key.strip()

    def to_dict(self) -> Dict[str, Any]:
        # Ensure active provider key and generic api_key remain synchronized
        active_key = self.get_api_key_for_provider(self.ai_provider)
        if active_key:
            self.api_key = active_key
            prov = (self.ai_provider or "gemini").lower()
            if prov == "gemini" and not self.gemini_api_key:
                self.gemini_api_key = active_key
            elif prov == "openai" and not self.openai_api_key:
                self.openai_api_key = active_key
            elif prov == "anthropic" and not self.anthropic_api_key:
                self.anthropic_api_key = active_key
            elif prov == "custom" and not self.custom_api_key:
                self.custom_api_key = active_key
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        valid_keys = cls.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}

        # Recognize environment variable names or common aliases if written to JSON directly
        gemini_aliases = ["gemini_api_key", "GEMINI_API_KEY", "GOOGLE_API_KEY", "google_api_key"]
        for alias in gemini_aliases:
            if alias in data and str(data[alias]).strip():
                filtered_data["gemini_api_key"] = str(data[alias]).strip()
                break

        openai_aliases = ["openai_api_key", "OPENAI_API_KEY"]
        for alias in openai_aliases:
            if alias in data and str(data[alias]).strip():
                filtered_data["openai_api_key"] = str(data[alias]).strip()
                break

        anthropic_aliases = ["anthropic_api_key", "ANTHROPIC_API_KEY"]
        for alias in anthropic_aliases:
            if alias in data and str(data[alias]).strip():
                filtered_data["anthropic_api_key"] = str(data[alias]).strip()
                break

        custom_aliases = ["custom_api_key", "CUSTOM_API_KEY"]
        for alias in custom_aliases:
            if alias in data and str(data[alias]).strip():
                filtered_data["custom_api_key"] = str(data[alias]).strip()
                break

        # Cross-populate between generic api_key and provider-specific key
        provider = str(filtered_data.get("ai_provider", data.get("ai_provider", "gemini"))).lower()
        api_key = str(filtered_data.get("api_key", "")).strip()

        if provider == "gemini":
            if not filtered_data.get("gemini_api_key") and api_key:
                filtered_data["gemini_api_key"] = api_key
            elif filtered_data.get("gemini_api_key") and not api_key:
                filtered_data["api_key"] = filtered_data["gemini_api_key"]
        elif provider == "openai":
            if not filtered_data.get("openai_api_key") and api_key:
                filtered_data["openai_api_key"] = api_key
            elif filtered_data.get("openai_api_key") and not api_key:
                filtered_data["api_key"] = filtered_data["openai_api_key"]
        elif provider == "anthropic":
            if not filtered_data.get("anthropic_api_key") and api_key:
                filtered_data["anthropic_api_key"] = api_key
            elif filtered_data.get("anthropic_api_key") and not api_key:
                filtered_data["api_key"] = filtered_data["anthropic_api_key"]
        elif provider == "custom":
            if not filtered_data.get("custom_api_key") and api_key:
                filtered_data["custom_api_key"] = api_key
            elif filtered_data.get("custom_api_key") and not api_key:
                filtered_data["api_key"] = filtered_data["custom_api_key"]

        # Merge hotkeys dictionary to preserve any missing defaults
        if "hotkeys" in filtered_data and isinstance(filtered_data["hotkeys"], dict):
            default_hotkeys = cls().hotkeys
            default_hotkeys.update(filtered_data["hotkeys"])
            filtered_data["hotkeys"] = default_hotkeys
        return cls(**filtered_data)


class ConfigManager:
    """Singleton manager for saving and loading application settings."""
    _instance: Optional["ConfigManager"] = None

    def __new__(cls, file_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.file_path = file_path or get_config_file_path()
            cls._instance.config = cls._instance.load()
            cls._instance.listeners = []
            cls._instance._sync_logging()
        elif file_path and cls._instance.file_path != file_path:
            cls._instance.file_path = file_path
            cls._instance.config = cls._instance.load()
        return cls._instance

    def _sync_logging(self):
        """Synchronizes logging configuration with active AppConfig settings."""
        try:
            from core.logger import setup_logging, set_debug_mode, set_log_level, get_log_buffer
            setup_logging(
                log_level=self.config.log_level,
                log_to_file=self.config.log_to_file,
                debug_mode=self.config.debug_mode
            )
            get_log_buffer().set_max_entries(self.config.max_log_entries)
        except Exception as e:
            print(f"[ConfigManager] Could not sync logging: {e}")

    def load(self) -> AppConfig:
        active_path = self.file_path or get_config_file_path()
        self.file_path = active_path

        # 1. Prefer user configuration file
        if os.path.exists(active_path):
            try:
                with open(active_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return AppConfig.from_dict(data)
            except Exception as e:
                print(f"[ConfigManager] Error reading config file at {active_path}: {e}. Falling back to default.")

        # 2. Fall back to repository default template
        default_path = get_default_config_file_path()
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return AppConfig.from_dict(data)
            except Exception as e:
                print(f"[ConfigManager] Error reading default config file at {default_path}: {e}.")

        return AppConfig()

    def reload(self) -> AppConfig:
        """Forces a re-read of configuration from disk."""
        self.config = self.load()
        self._sync_logging()
        self._notify_listeners()
        return self.config

    def save(self) -> bool:
        try:
            target_path = self.file_path or get_config_file_path()
            target_dir = os.path.dirname(os.path.abspath(target_path))
            os.makedirs(target_dir, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=4)
            self.file_path = target_path
            self._sync_logging()
            self._notify_listeners()
            return True
        except Exception as e:
            print(f"[ConfigManager] Error saving config file to {self.file_path}: {e}")
            return False

    def update(self, **kwargs) -> bool:
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        return self.save()

    def add_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def _notify_listeners(self):
        for listener in self.listeners:
            try:
                listener(self.config)
            except Exception as e:
                print(f"[ConfigManager] Error notifying listener: {e}")


# Global helper instance
def get_config() -> AppConfig:
    return ConfigManager().config


def update_config(**kwargs) -> bool:
    return ConfigManager().update(**kwargs)
