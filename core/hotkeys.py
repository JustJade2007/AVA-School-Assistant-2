"""
Global Hotkey Manager for AVA School Assistant 2.
Listens for system-wide key combinations and dispatches callbacks asynchronously.
"""

import threading
from typing import Dict, Callable, Optional
from pynput import keyboard


from core.logger import get_logger

logger = get_logger("hotkeys")


def normalize_hotkey_str(key_str: str) -> str:
    """
    Converts human strings like 'F8', 'ctrl+alt+x', 'Shift+F9' to pynput format:
    '<f8>', '<ctrl>+<alt>+x', '<shift>+<f9>'.
    """
    parts = [p.strip().lower() for p in key_str.split("+") if p.strip()]
    normalized_parts = []
    special_keys = {
        "ctrl": "<ctrl>",
        "alt": "<alt>",
        "shift": "<shift>",
        "cmd": "<cmd>",
        "esc": "<esc>",
        "space": "<space>",
        "enter": "<enter>",
        "tab": "<tab>",
        "backspace": "<backspace>",
        "delete": "<delete>",
    }

    for part in parts:
        if part in special_keys:
            normalized_parts.append(special_keys[part])
        elif part.startswith("f") and part[1:].isdigit():
            normalized_parts.append(f"<{part}>")
        elif len(part) == 1:
            normalized_parts.append(part)
        else:
            normalized_parts.append(f"<{part}>")

    return "+".join(normalized_parts)


class GlobalHotkeyManager:
    """Manages system-wide hotkeys and event dispatching."""

    def __init__(self):
        self.callbacks: Dict[str, Callable[[], None]] = {}
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._lock = threading.Lock()

    def register_hotkey(self, name: str, key_str: str, callback: Callable[[], None]):
        """Registers a named callback for a hotkey."""
        with self._lock:
            self.callbacks[name] = (key_str, callback)

    def start(self):
        """Starts the global hotkey listener."""
        with self._lock:
            self.stop()
            hotkey_mapping = {}
            for name, (key_str, cb) in self.callbacks.items():
                pynput_key = normalize_hotkey_str(key_str)
                # Dispatch on background thread to prevent blocking keyboard hook
                hotkey_mapping[pynput_key] = self._create_dispatcher(name, cb)

            try:
                self._listener = keyboard.GlobalHotKeys(hotkey_mapping)
                self._listener.daemon = True
                self._listener.start()
                logger.info(f"Hotkey listener started with mappings: {list(hotkey_mapping.keys())}")
            except Exception as e:
                logger.error(f"Failed to start hotkey listener: {e}")

    def stop(self):
        """Stops the global hotkey listener."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _create_dispatcher(self, name: str, callback: Callable[[], None]):
        def handler():
            logger.info(f"Hotkey triggered: {name}")
            # Spawn in thread so long operations don't freeze the pynput loop
            t = threading.Thread(target=callback, daemon=True)
            t.start()
        return handler
