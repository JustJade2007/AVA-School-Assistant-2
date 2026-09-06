"""
Unit and integration tests for Input Stream Safeguards & Concurrency Protection.
Verifies that:
1. Two streams of inputs can NEVER happen at once (e.g. pressing F8 and F9 concurrently).
2. Pressing F9 (confirm_and_execute) while F8 (solve pipeline) is scanning, thinking, or inspecting is safely rejected.
3. Pressing F8 (trigger_solve) while F9 (action execution) is actively executing or verifying is safely rejected.
4. Simultaneous race condition between F8 and F9 atomically permits only one pipeline to run.
5. AutomationExecutor enforces hardware input mutual exclusion: concurrent execute_action_sequence calls are rejected.
6. GlobalHotkeyManager debounces rapid successive triggers of the same shortcut.
7. Manual Next (F10) is rejected while an action sequence or solve pipeline is busy.
"""

import time
import threading
import unittest
from unittest.mock import MagicMock, patch

from core.assistant_engine import AssistantEngine, EngineState
from core.automation import AutomationExecutor
from core.hotkeys import GlobalHotkeyManager
from config import ConfigManager


class TestInputStreamSafeguard(unittest.TestCase):
    """Tests multi-layer concurrency safeguards preventing concurrent input streams."""

    def setUp(self):
        self.config_manager = ConfigManager()
        self.engine = AssistantEngine(config_manager=self.config_manager)

    def test_f9_rejected_while_f8_is_scanning_or_thinking(self):
        """
        Verifies that if F8 is currently running (SCANNING or THINKING),
        pressing F9 (confirm_and_execute) is blocked and does NOT launch an execution thread.
        """
        self.engine.last_result = {
            "actions": [{"type": "click", "screen_x": 300, "screen_y": 300, "verified": True}],
            "ready_to_advance": True
        }

        # 1. State is SCANNING
        self.engine.set_state(EngineState.SCANNING)
        with patch.object(self.engine, "execute_current_solution") as mock_exec:
            self.engine.confirm_and_execute()
            mock_exec.assert_not_called()
        self.assertEqual(self.engine.state, EngineState.SCANNING)

        # 2. State is THINKING
        self.engine.set_state(EngineState.THINKING)
        with patch.object(self.engine, "execute_current_solution") as mock_exec:
            self.engine.confirm_and_execute()
            mock_exec.assert_not_called()
        self.assertEqual(self.engine.state, EngineState.THINKING)

    def test_f8_rejected_while_f9_is_executing_or_verifying(self):
        """
        Verifies that if F9 is currently executing or verifying actions,
        pressing F8 (trigger_solve) is blocked and does NOT start a new solve pipeline.
        """
        # 1. State is EXECUTING
        self.engine.set_state(EngineState.EXECUTING)
        with patch.object(self.engine, "_run_solve_pipeline") as mock_pipe:
            self.engine.trigger_solve()
            mock_pipe.assert_not_called()
        self.assertEqual(self.engine.state, EngineState.EXECUTING)

        # 2. State is VERIFYING
        self.engine.set_state(EngineState.VERIFYING)
        with patch.object(self.engine, "_run_solve_pipeline") as mock_pipe:
            self.engine.trigger_solve()
            mock_pipe.assert_not_called()
        self.assertEqual(self.engine.state, EngineState.VERIFYING)

    def test_f10_rejected_while_engine_is_busy(self):
        """
        Verifies that pressing F10 (trigger_next_question) while the engine is executing
        or solving is blocked to prevent conflicting mouse moves or navigation clicks.
        """
        self.engine.set_state(EngineState.EXECUTING)
        with patch.object(self.engine, "trigger_next_button") as mock_next:
            self.engine.trigger_next_question()
            mock_next.assert_not_called()
        self.assertEqual(self.engine.state, EngineState.EXECUTING)

    def test_simultaneous_f8_and_f9_atomic_mutual_exclusion(self):
        """
        Simulates pressing F8 and F9 at the exact same millisecond from WAITING_CONFIRMATION.
        Verifies that atomic action gating allows exactly ONE to proceed and rejects the other.
        """
        self.engine.last_result = {
            "actions": [{"type": "click", "screen_x": 400, "screen_y": 400, "verified": True}],
            "ready_to_advance": True
        }
        self.engine.set_state(EngineState.WAITING_CONFIRMATION)

        f8_started = False
        f9_started = False
        barrier = threading.Barrier(2)

        def run_f8():
            nonlocal f8_started
            barrier.wait()
            # Intercept actual solve thread spawn to count successful claim
            with patch.object(self.engine, "_run_solve_pipeline"):
                orig_thread_start = threading.Thread.start
                def mock_thread_start(t_self):
                    nonlocal f8_started
                    if "SolvePipelineThread" in str(getattr(t_self, "name", "")):
                        f8_started = True
                    else:
                        orig_thread_start(t_self)
                with patch.object(threading.Thread, "start", mock_thread_start):
                    self.engine.trigger_solve()

        def run_f9():
            nonlocal f9_started
            barrier.wait()
            with patch.object(self.engine, "execute_current_solution"):
                orig_thread_start = threading.Thread.start
                def mock_thread_start(t_self):
                    nonlocal f9_started
                    if "ActionExecutionThread" in str(getattr(t_self, "name", "")):
                        f9_started = True
                    else:
                        orig_thread_start(t_self)
                with patch.object(threading.Thread, "start", mock_thread_start):
                    self.engine.confirm_and_execute()

        t1 = threading.Thread(target=run_f8)
        t2 = threading.Thread(target=run_f9)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Invariant: EXACTLY one of the two must have won the race! Never both!
        self.assertTrue(f8_started ^ f9_started, f"Expected XOR (f8={f8_started}, f9={f9_started})")

    def test_automation_executor_input_stream_lock(self):
        """
        Verifies that AutomationExecutor blocks concurrent execute_action_sequence calls
        at the hardware layer with error='concurrent_input_prevented'.
        """
        executor = AutomationExecutor()
        actions = [{"type": "delay", "seconds": 0.2}]

        # Thread 1 starts executing
        thread1_running = threading.Event()
        thread1_done = threading.Event()
        results = []

        def worker1():
            # Mock delay to hold the lock
            orig_exec = executor.execute_action
            def holding_exec(act):
                thread1_running.set()
                time.sleep(0.3)
            with patch.object(executor, "execute_action", holding_exec):
                res = executor.execute_action_sequence(actions)
                results.append(("worker1", res))
                thread1_done.set()

        t1 = threading.Thread(target=worker1)
        t1.start()

        # Wait until Thread 1 is inside execute_action_sequence
        thread1_running.wait(timeout=2.0)
        self.assertTrue(executor.is_input_active())

        # Thread 2 attempts to execute simultaneously
        res2 = executor.execute_action_sequence(actions)
        self.assertEqual(res2.get("error"), "concurrent_input_prevented")
        self.assertFalse(res2.get("all_verified"))

        thread1_done.wait(timeout=2.0)
        t1.join()

        # Lock must be released cleanly after completion
        self.assertFalse(executor.is_input_active())

    def test_global_hotkey_manager_debounce(self):
        """
        Verifies that GlobalHotkeyManager suppresses rapid duplicate triggers within 200ms.
        """
        mgr = GlobalHotkeyManager(debounce_cooldown=0.20)
        call_count = 0

        def test_callback():
            nonlocal call_count
            call_count += 1

        dispatcher = mgr._create_dispatcher("test_trigger", test_callback)

        # Trigger 1: must fire
        dispatcher()
        # Trigger 2 (immediate): must be debounced
        dispatcher()
        # Trigger 3 (immediate): must be debounced
        dispatcher()

        time.sleep(0.05)
        self.assertEqual(call_count, 1)

        # Wait for cooldown to expire
        time.sleep(0.22)
        dispatcher()
        time.sleep(0.05)
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
