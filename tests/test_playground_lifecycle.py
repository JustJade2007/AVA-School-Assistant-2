"""Focused regression tests for Playground window lifecycle handling."""

import unittest
from unittest.mock import MagicMock, patch

try:
    from ui.playground.workspace import PlaygroundWorkspace
    from ui.app import AVASchoolAssistantApp
    from core.playground.project_model import SectionDraft
except ModuleNotFoundError as exc:
    PlaygroundWorkspace = None
    AVASchoolAssistantApp = None
    SectionDraft = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Playground UI dependencies unavailable: {IMPORT_ERROR}")
class TestPlaygroundLifecycle(unittest.TestCase):

    def make_workspace(self):
        workspace = PlaygroundWorkspace.__new__(PlaygroundWorkspace)
        workspace._is_closing = False
        workspace._is_generating = False
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

    def test_navigating_to_empty_section_triggers_auto_draft(self):
        workspace = self.make_workspace()
        workspace.current_section_idx = 0
        empty_section = SectionDraft(title="Intro", goal_summary="Explain the topic")
        workspace.project.sections = [empty_section]
        workspace.sec_goal_label = MagicMock()
        workspace.raw_text_box = MagicMock()
        workspace.final_text_box = MagicMock()
        workspace.final_text_box.get = MagicMock(return_value="")
        workspace.approval_badge = MagicMock()
        workspace._update_sec_word_stats = MagicMock()
        workspace._start_drafting_section = MagicMock()

        workspace._load_active_section_into_editor()

        workspace._start_drafting_section.assert_called_once_with(empty_section)

    def test_navigating_to_drafted_section_does_not_auto_draft(self):
        workspace = self.make_workspace()
        workspace.current_section_idx = 0
        drafted_section = SectionDraft(title="Intro", final_text="Already has content.")
        workspace.project.sections = [drafted_section]
        workspace.sec_goal_label = MagicMock()
        workspace.raw_text_box = MagicMock()
        workspace.final_text_box = MagicMock()
        workspace.final_text_box.get = MagicMock(return_value="Already has content.")
        workspace.approval_badge = MagicMock()
        workspace._update_sec_word_stats = MagicMock()
        workspace._start_drafting_section = MagicMock()

        workspace._load_active_section_into_editor()

        workspace._start_drafting_section.assert_not_called()

    def test_start_drafting_section_skips_when_already_generating(self):
        workspace = self.make_workspace()
        workspace._is_generating = True
        workspace.draft_ai_btn = MagicMock()
        workspace.engine = MagicMock()

        section = SectionDraft(title="Body")
        workspace._start_drafting_section(section)

        workspace.draft_ai_btn.configure.assert_not_called()
        workspace.engine.draft_section.assert_not_called()

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
