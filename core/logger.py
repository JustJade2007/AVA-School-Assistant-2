"""
Unified Logging System for AVA School Assistant 2.
Provides console logging, rotating file logging, an in-memory ring buffer for live UI inspection,
and dynamic log-level adjustment for debug users.
"""

import os
import sys
import time
import logging
import threading
from logging.handlers import RotatingFileHandler
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Callable, Dict, Any

def _resolve_app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT_DIR = _resolve_app_root()
LOG_DIR = os.path.join(ROOT_DIR, "logs")
DEFAULT_LOG_FILE = os.path.join(LOG_DIR, "ava_assistant.log")


@dataclass
class LogEntry:
    """Structured representation of an individual log record."""
    timestamp: float
    formatted_time: str
    level_name: str
    level_no: int
    logger_name: str
    message: str
    traceback: Optional[str] = None

    def to_formatted_line(self) -> str:
        """Returns standard single-line formatted text."""
        tb_part = f"\n{self.traceback}" if self.traceback else ""
        return f"[{self.formatted_time}] [{self.level_name:<7}] [{self.logger_name}] {self.message}{tb_part}"


class MemoryLogBuffer:
    """Thread-safe ring buffer keeping the most recent log entries in memory."""

    def __init__(self, max_entries: int = 500):
        self.max_entries = max_entries
        self._buffer: deque = deque(maxlen=max_entries)
        self._listeners: List[Callable[[LogEntry], None]] = []
        self._lock = threading.Lock()

    def set_max_entries(self, max_entries: int):
        with self._lock:
            self.max_entries = max_entries
            new_buffer = deque(self._buffer, maxlen=max_entries)
            self._buffer = new_buffer

    def append(self, entry: LogEntry):
        with self._lock:
            self._buffer.append(entry)
            listeners_copy = list(self._listeners)

        for listener in listeners_copy:
            try:
                listener(entry)
            except Exception:
                pass

    def get_entries(
        self,
        level: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[LogEntry]:
        """Retrieves filtered log entries."""
        with self._lock:
            entries = list(self._buffer)

        # Filter by minimum log level if requested
        if level and level.upper() != "ALL":
            target_level_no = getattr(logging, level.upper(), logging.INFO)
            entries = [e for e in entries if e.level_no >= target_level_no]

        # Filter by search string (case-insensitive)
        if search:
            query = search.lower()
            entries = [
                e for e in entries
                if query in e.message.lower()
                or query in e.logger_name.lower()
                or (e.traceback and query in e.traceback.lower())
            ]

        if limit is not None and limit > 0:
            entries = entries[-limit:]

        return entries

    def get_all_formatted(self, level: Optional[str] = None, search: Optional[str] = None) -> str:
        entries = self.get_entries(level=level, search=search)
        return "\n".join(e.to_formatted_line() for e in entries)

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def add_listener(self, callback: Callable[[LogEntry], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[LogEntry], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)


class MemoryLogHandler(logging.Handler):
    """Logging handler that pipes formatted records into the MemoryLogBuffer."""

    def __init__(self, buffer: MemoryLogBuffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            tb = None
            if record.exc_info:
                if self.formatter:
                    tb = self.formatter.formatException(record.exc_info)
                else:
                    tb = logging.Formatter().formatException(record.exc_info)

            # Extract formatted time
            t = record.created
            formatted_time = time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t % 1) * 1000):03d}"

            # Only use message without timestamp prefix for storage if available
            raw_msg = record.getMessage() if hasattr(record, "getMessage") else str(record.msg)

            entry = LogEntry(
                timestamp=t,
                formatted_time=formatted_time,
                level_name=record.levelname,
                level_no=record.levelno,
                logger_name=record.name,
                message=raw_msg,
                traceback=tb
            )
            self.buffer.append(entry)
        except Exception:
            self.handleError(record)


# Global instances
_memory_buffer = MemoryLogBuffer(max_entries=500)
_memory_handler = MemoryLogHandler(_memory_buffer)
_file_handler: Optional[RotatingFileHandler] = None
_console_handler: Optional[logging.StreamHandler] = None
_is_initialized = False
_current_debug_mode = False


def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = True,
    debug_mode: bool = False,
    max_file_size_mb: int = 5,
    backup_count: int = 3
):
    """
    Initializes root AVA logger with console, memory buffer, and rotating file outputs.
    """
    global _is_initialized, _file_handler, _console_handler, _current_debug_mode
    _current_debug_mode = debug_mode

    root_logger = logging.getLogger("ava")
    effective_level = logging.DEBUG if debug_mode else getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(effective_level)

    # Standard formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s.%(msecs)03d] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    _memory_handler.setFormatter(formatter)
    _memory_handler.setLevel(logging.DEBUG)  # Memory buffer always captures DEBUG if root allows

    # Ensure memory handler is attached
    if _memory_handler not in root_logger.handlers:
        root_logger.addHandler(_memory_handler)

    # Setup Console Handler
    if _console_handler is None:
        if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(errors="replace")
            except Exception:
                pass
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setFormatter(formatter)
        _console_handler.setLevel(effective_level)
        root_logger.addHandler(_console_handler)
    else:
        _console_handler.setLevel(effective_level)

    # Setup File Handler if requested
    if log_to_file:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            if _file_handler is None:
                _file_handler = RotatingFileHandler(
                    DEFAULT_LOG_FILE,
                    maxBytes=max_file_size_mb * 1024 * 1024,
                    backupCount=backup_count,
                    encoding="utf-8"
                )
                _file_handler.setFormatter(formatter)
                _file_handler.setLevel(logging.DEBUG)  # Always capture full detail in file
                root_logger.addHandler(_file_handler)
        except Exception as e:
            root_logger.warning(f"Failed to initialize log file at {DEFAULT_LOG_FILE}: {e}")
    else:
        if _file_handler and _file_handler in root_logger.handlers:
            root_logger.removeHandler(_file_handler)
            _file_handler.close()
            _file_handler = None

    _is_initialized = True
    root_logger.debug(
        f"Logging initialized: level={logging.getLevelName(effective_level)}, "
        f"file={log_to_file}, debug_mode={debug_mode}"
    )


def get_logger(name: str = "ava") -> logging.Logger:
    """Returns a named logger child under the 'ava' root hierarchy."""
    if not _is_initialized:
        setup_logging()

    if name == "ava" or name.startswith("ava."):
        return logging.getLogger(name)
    return logging.getLogger(f"ava.{name}")


def set_debug_mode(enabled: bool):
    """Dynamically enables or disables debug-level logging across all handlers."""
    global _current_debug_mode
    _current_debug_mode = enabled
    root_logger = logging.getLogger("ava")
    new_level = logging.DEBUG if enabled else logging.INFO
    root_logger.setLevel(new_level)

    if _console_handler:
        _console_handler.setLevel(new_level)

    root_logger.info(f"Debug mode {'ENABLED (verbose logging active)' if enabled else 'DISABLED'}")


def set_log_level(level: str):
    """Sets standard logging level (e.g. 'DEBUG', 'INFO', 'WARNING', 'ERROR')."""
    target_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger("ava")
    root_logger.setLevel(target_level)
    if _console_handler:
        _console_handler.setLevel(target_level)
    root_logger.info(f"Log level updated to {level.upper()}")


def is_debug_mode() -> bool:
    return _current_debug_mode


def get_log_buffer() -> MemoryLogBuffer:
    """Returns the in-memory ring buffer for UI subscribers."""
    return _memory_buffer


def get_log_file_path() -> str:
    """Returns the absolute path to the active log file."""
    return DEFAULT_LOG_FILE


def get_log_directory() -> str:
    """Returns the directory containing log files."""
    return LOG_DIR


def clear_log_file() -> bool:
    """Clears the contents of the log file."""
    try:
        if os.path.exists(DEFAULT_LOG_FILE):
            with open(DEFAULT_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"--- Log reset at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        return True
    except Exception as e:
        get_logger().error(f"Failed to clear log file: {e}")
        return False
