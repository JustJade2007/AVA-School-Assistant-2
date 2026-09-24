"""
Single Instance Manager for AVA School Assistant 2.
Ensures only one copy of AVA runs at any given time. If a second instance is
launched (e.g. user double-clicks AVA_School_Assistant_2.exe while already running),
it detects the active instance, sends an activation signal, restores any minimized
windows, brings the running application to the foreground, and exits cleanly.
"""

import os
import sys
import time
import socket
import threading
import tempfile
from typing import Optional, Callable, List, Tuple
from core.logger import get_logger

logger = get_logger("single_instance")

MUTEX_NAME = "Local\\AVASchoolAssistant2_SingleInstance_Mutex"
DEFAULT_PORT = 49285
LOCKFILE_PATH = os.path.join(tempfile.gettempdir(), "ava_school_assistant_2.ipc")

# Win32 Constants
SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWNA = 8
HWND_TOP = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2

# Known AVA Window Titles
AVA_WINDOW_TITLES = (
    "AVA • Command Hub",
    "AVA_HUD_Cloaked",
    "Playground",
    "AVA • Settings",
    "AVA School Assistant 2"
)


def _is_windows() -> bool:
    return sys.platform == "win32"


def force_foreground_window(hwnd: int) -> bool:
    """
    Brings the specified Win32 window HWND to the foreground, even if the calling
    process is not currently the foreground process, using the AttachThreadInput API.
    """
    if not _is_windows() or not hwnd:
        return False

    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.IsWindow(hwnd):
        return False

    try:
        # If minimized, restore first
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        fore_hwnd = user32.GetForegroundWindow()
        cur_thread_id = kernel32.GetCurrentThreadId()
        fore_thread_id = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0

        attached = False
        if fore_thread_id != 0 and fore_thread_id != cur_thread_id:
            attached = bool(user32.AttachThreadInput(cur_thread_id, fore_thread_id, True))

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

        if attached:
            user32.AttachThreadInput(cur_thread_id, fore_thread_id, False)

        return True
    except Exception as e:
        logger.debug(f"Error in force_foreground_window for HWND {hwnd}: {e}")
        return False


def find_existing_ava_windows() -> List[Tuple[int, str]]:
    """
    Finds all active Win32 top-level windows matching known AVA window titles.
    Returns a list of (hwnd, title) tuples.
    """
    if not _is_windows():
        return []

    import ctypes
    user32 = ctypes.windll.user32

    matching_windows = []

    def enum_cb(hwnd, lparam):
        if not user32.IsWindow(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            for known in AVA_WINDOW_TITLES:
                if known.lower() in title.lower():
                    # Root top-level window
                    root_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
                    matching_windows.append((root_hwnd, title))
                    break
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return matching_windows


def _read_ipc_port() -> int:
    """Reads the active instance IPC port from the lockfile if present."""
    try:
        if os.path.exists(LOCKFILE_PATH):
            with open(LOCKFILE_PATH, "r", encoding="utf-8") as f:
                port_str = f.read().strip()
                if port_str.isdigit():
                    return int(port_str)
    except Exception:
        pass
    return DEFAULT_PORT


def _write_ipc_port(port: int) -> None:
    """Writes the active instance IPC port to the lockfile."""
    try:
        with open(LOCKFILE_PATH, "w", encoding="utf-8") as f:
            f.write(str(port))
    except Exception as e:
        logger.debug(f"Could not write IPC lockfile: {e}")


def _remove_ipc_lockfile() -> None:
    """Removes the IPC lockfile on shutdown."""
    try:
        if os.path.exists(LOCKFILE_PATH):
            os.remove(LOCKFILE_PATH)
    except Exception:
        pass


def signal_running_instance() -> bool:
    """
    Attempts to signal the running instance via local loopback IPC to bring itself to foreground.
    """
    port = _read_ipc_port()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect(("127.0.0.1", port))
        s.sendall(b"ACTIVATE\n")
        s.close()
        logger.info(f"Activation signal sent to running instance on port {port}.")
        return True
    except Exception as e:
        logger.debug(f"Could not signal running instance on port {port}: {e}")
        return False


def bring_existing_instance_to_foreground() -> bool:
    """
    Coordinates signaling the existing instance via IPC and restoring/focusing
    its Win32 windows using native OS calls.
    """
    # 1. Send internal activate signal
    signaled = signal_running_instance()

    # 2. Find matching Win32 windows and restore / foreground them
    windows = find_existing_ava_windows()
    foregrounded = False

    for hwnd, title in windows:
        logger.info(f"Restoring and focusing existing window: '{title}' (HWND: {hwnd})")
        if force_foreground_window(hwnd):
            foregrounded = True

    return signaled or foregrounded


class SingleInstanceManager:
    """
    Lifecycle coordinator for single-instance enforcement and IPC activation listener.
    """

    def __init__(self):
        self._mutex_handle = None
        self._server_socket: Optional[socket.socket] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_activate: Optional[Callable[[], None]] = None

    def acquire_or_activate(self, on_activate: Optional[Callable[[], None]] = None) -> bool:
        """
        Attempts to acquire the single-instance mutex.
        If another instance already holds the mutex:
          - Restores and brings that instance to foreground.
          - Returns False (caller should exit).
        If this is the primary instance:
          - Holds the mutex.
          - Starts the IPC listener.
          - Returns True (caller continues startup).
        """
        self._on_activate = on_activate

        if _is_windows():
            import ctypes
            kernel32 = ctypes.windll.kernel32
            ERROR_ALREADY_EXISTS = 183

            # Create or open named mutex
            self._mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_err = kernel32.GetLastError()

            if last_err == ERROR_ALREADY_EXISTS:
                logger.info("Another instance of AVA School Assistant 2 is already running.")
                bring_existing_instance_to_foreground()
                return False

        # Start IPC activation server
        self._start_ipc_server()
        return True

    def _start_ipc_server(self) -> None:
        """Starts a background loopback server listening for activation requests."""
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Try default port, fallback to dynamic ephemeral port if busy
            try:
                self._server_socket.bind(("127.0.0.1", DEFAULT_PORT))
            except Exception:
                self._server_socket.bind(("127.0.0.1", 0))

            bound_port = self._server_socket.getsockname()[1]
            self._server_socket.listen(3)
            _write_ipc_port(bound_port)

            self._running = True
            self._listener_thread = threading.Thread(
                target=self._listen_loop,
                name="SingleInstanceIPCListener",
                daemon=True
            )
            self._listener_thread.start()
            logger.debug(f"SingleInstance IPC listener active on port {bound_port}")
        except Exception as e:
            logger.warning(f"Could not start SingleInstance IPC listener: {e}")

    def _listen_loop(self) -> None:
        while self._running and self._server_socket:
            try:
                conn, _ = self._server_socket.accept()
                try:
                    data = conn.recv(1024)
                    if b"ACTIVATE" in data:
                        logger.info("Received ACTIVATE request from second instance.")
                        if self._on_activate:
                            try:
                                self._on_activate()
                            except Exception as ex:
                                logger.error(f"Error executing on_activate callback: {ex}")
                finally:
                    conn.close()
            except Exception:
                if not self._running:
                    break

    def cleanup(self) -> None:
        """Releases mutex and shuts down IPC listener."""
        self._running = False
        _remove_ipc_lockfile()

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        if _is_windows() and self._mutex_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None


# Global singleton instance manager
_instance_manager: Optional[SingleInstanceManager] = None


def check_single_instance(on_activate: Optional[Callable[[], None]] = None) -> bool:
    """
    Public entry point for single instance enforcement.
    Returns True if this is the only instance (proceed to run).
    Returns False if an instance is already running (caller must exit).
    """
    global _instance_manager
    if _instance_manager is None:
        _instance_manager = SingleInstanceManager()
    return _instance_manager.acquire_or_activate(on_activate=on_activate)


def cleanup_single_instance() -> None:
    """Releases mutex and socket resources."""
    global _instance_manager
    if _instance_manager:
        _instance_manager.cleanup()
        _instance_manager = None
