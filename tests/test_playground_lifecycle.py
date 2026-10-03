"""Focused regression tests for Playground window lifecycle handling."""

import unittest
from unittest.mock import MagicMock, patch

try:
    from ui.playground.workspace import PlaygroundWorkspace
    from ui.app import AVASchoolAssistantApp
except ModuleNotFoundError as exc:
    PlaygroundWorkspace = None
    AVASchoolAssistantApp = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Playground UI dependencies unavailable: {IMPORT_ERROR}")
class TestPlaygroundLifecycle(unittest.TestCase):

    def make_workspace(self):
        workspace = PlaygroundWorkspace.__new__(PlaygroundWorkspace)
        workspace._is_closing = False
        workspace.project = MagicMock()
        workspace.destroy = MagicMock()
        workspace.on_exit = MagicMock()
        return workspace

    def test_closing_playground_twice_is_idempotent(self):
        workspace = self.make_workspace()

        with patch("ui.playground.workspace.os.makedirs"):
            workspace._on_close_requested()
            workspace._on_close_requested()

        self.assertTrue(workspace._is_closing)
        workspace.destroy.assert_called_once_with()
        workspace.on_exit.assert_called_once_with()
        workspace.project.save_to_file.assert_called_once_with("projects/last_session.avaproj")

    def test_callback_scheduled_before_close_is_ignored_after_close(self):
        workspace = self.make_workspace()
        scheduled = []
        workspace.after = lambda delay, callback: scheduled.append(callback)
        workspace.winfo_exists = MagicMock(return_value=True)
        callback = MagicMock()

        workspace._after_if_open(0, callback)
        workspace._is_closing = True
        scheduled[0]()

        callback.assert_not_called()
        workspace.winfo_exists.assert_not_called()

    def test_snipping_completion_does_not_restore_after_close(self):
        workspace = self.make_workspace()
        workspace.withdraw = MagicMock()
        workspace.deiconify = MagicMock()
        workspace.master = MagicMock()
        workspace.winfo_exists = MagicMock(return_value=False)

        with patch("ui.playground.workspace.SnippingOverlay") as overlay:
            workspace._snip_rubric()
            on_snip = overlay.call_args.kwargs["on_snip_complete"]
            on_snip((1, 2, 3, 4))

        workspace.deiconify.assert_not_called()

    def test_stale_playground_reference_is_cleared(self):
        app = AVASchoolAssistantApp.__new__(AVASchoolAssistantApp)
        stale_window = MagicMock()
        stale_window.winfo_exists.return_value = False
        app.playground_window = stale_window
        app.hud_window = None
        app.home_window = None
        app.hotkey_manager = MagicMock()
        app.engine = MagicMock()

        app._do_return_to_home()

        self.assertIsNone(app.playground_window)
        stale_window.destroy.assert_not_called()

    def test_live_playground_is_destroyed_and_cleared(self):
        app = AVASchoolAssistantApp.__new__(AVASchoolAssistantApp)
        live_window = MagicMock()
        live_window.winfo_exists.return_value = True
        app.playground_window = live_window
        app.hud_window = None
        app.home_window = None
        app.hotkey_manager = MagicMock()
        app.engine = MagicMock()

        app._do_return_to_home()

        self.assertIsNone(app.playground_window)
        live_window.destroy.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
