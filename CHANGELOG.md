# Changelog

All notable changes to AVA School Assistant 2 will be documented in this file.

The version format is `1.2.3.a`:
- **1**: MAJOR changes or completion
- **2**: Major feature/reworks
- **3**: New features or major bug update
- **a**: Basic bug fixes

---

## [1.3.0.a] - 2026-09-06

### Added
- **Platform Evaluation Status & Answer Rethinking Architecture (`core/prompt.py`, `core/ai_client.py`, `core/local_verifier.py`, `core/assistant_engine.py`, `ui/hud_overlay.py`)**:
  - **Explicit Platform Evaluation Categorization**: Vision prompt and response models now formally categorize the visual status of questions into three distinct states:
    - `"correct"`: The platform has visually graded the question as correct (green checkmarks, green input borders, success banners, "Correct!" feedback).
    - `"incorrect"`: The platform has visually graded the question as incorrect (red "X", red borders, error banners, "Try again", "Incorrect" messages).
    - `"unsubmitted"`: The question is fresh, unattempted, or currently in progress without platform evaluation feedback.
  - **Mandatory Rethinking on Incorrect Answers (`is_rethinking`, `rethink_reasoning`)**:
    - When a question or sub-part is marked `"incorrect"`, AVA is strictly prohibited from considering the question answered or advancing.
    - AVA triggers a dual-dimension rethink:
      1. **Academic Problem Reasoning**: Reads platform error text, explanations, or remaining attempt counters; re-evaluates problem assumptions, calculations, and alternate solution paths.
      2. **Input Entry & Formatting Methodology**: Reconsiders how the answer must be entered (e.g. simplified fraction vs decimal, including/excluding units, rounding precision, coordinate formatting, case sensitivity).
    - AI emits `clear_first: true` on corrective actions so previous incorrect text inputs are completely replaced.
  - **Zero-Token Platform Evaluation Marker Detection (`detect_platform_evaluation_markers`)**:
    - Uses local computer vision to detect dominant color clusters without extra AI tokens: prominent red clusters indicate platform rejection, while green clusters indicate verified success.
  - **Post-Submission Feedback Capture (`verify_post_submission_evaluation`)**:
    - When auto-advancing after clicking "Check Answer" / "Submit", AVA captures the post-submission screen. If the platform introduces red error feedback indicating an incorrect answer, AVA immediately intercepts the auto-advance, prevents advancing or going idle, and triggers the rethink cycle.
  - **Multi-Part Evaluation Propagation**:
    - In multi-part questions, if any individual sub-part is marked `"incorrect"`, the top-level status is set to `"incorrect"` and `ready_to_advance` is forced to `False`. Correct parts are marked untouched while incorrect parts are rethought and corrected.
  - **HUD Overlay Evaluation Badges & Strategy Banner**:
    - Displays prominent badges in the HUD: `✓ PLATFORM: CORRECT` (green), `❌ PLATFORM: INCORRECT -> RETHINKING` (crimson), and `● PLATFORM: UNCHECKED / DRAFT` (slate).
    - Renders an interactive, high-visibility "🔄 RETHINKING INCORRECT ANSWER" banner detailing the model's rethink strategy and academic/formatting corrections.

### Tests
- Added 9 unit and integration tests in `tests/test_question_evaluation_and_rethinking.py` verifying status classification, rethink triggering, zero-token color cluster detection, post-submission interception, and advance prevention on incorrect answers (all 74 tests passing).

---

## [1.2.3.b] - 2026-09-06

### Fixed
- **API Key Persistence Across Application Restarts (`config.py`, `ui/settings_view.py`, `ui/app.py`, `core/assistant_engine.py`)**:
  - **Provider-Specific Key Attributes (`AppConfig`)**: Added explicit storage fields (`gemini_api_key`, `openai_api_key`, `anthropic_api_key`, `custom_api_key`) in `AppConfig` so keys are never stripped, overwritten, or discarded when users switch providers or edit `config.json`.
  - **Dynamic Alias and Environment Fallback (`get_api_key_for_provider`)**: Enhanced key resolution with automatic fallback chains across provider-specific fields, generic `api_key`, and system environment variables (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
  - **Settings Window Auto-Save on Titlebar Close (`WM_DELETE_WINDOW`)**: Intercepted the window close protocol so closing Settings via the title bar "✕" button automatically commits all entered keys and preferences rather than discarding them.
  - **Auto-Persist on Successful Test Connection**: When the user clicks "Test API Connection" and the provider connects successfully, verified credentials are now automatically committed to `config.json` immediately.
  - **Per-Provider Key Isolation in UI**: Switching between Gemini, OpenAI, Anthropic, or Custom in the Settings dropdown now caches the entered key for the previous provider and restores the selected provider's key in the input box.
  - **Application Exit Flush**: Added auto-save of any active Settings window and an explicit `config_manager.save()` flush during application shutdown in `ui/app.py`.

### Tests
- Added 4 new test cases in `tests/test_settings_and_config.py` verifying Gemini API key persistence, provider switching isolation, `WM_DELETE_WINDOW` auto-save, and alias fallback resolution (65/65 tests passing).

---

## [1.2.3.a] - 2026-09-06

### Added
- **AI-Detected Scrolling Quiz Advancing (`core/prompt.py`, `core/ai_client.py`, `core/assistant_engine.py`)**:
  - **Dynamic Single-Page Assessment Detection**: Added vision prompt instructions for single-page scrolling quizzes (e.g. Google Forms, Canvas single-page quizzes, Microsoft Forms, test worksheets) where questions are stacked vertically down a continuous page without a "Next" button between questions.
  - **Pure AI Detection (Zero Settings)**: Strictly governed by AI visual understanding rather than user configuration toggles. AVA dynamically distinguishes between button-based assessments (`advance_action: "click_button"`) and continuous scrolling quizzes (`advance_action: "scroll_down"` with `scroll_amount`).
  - **Zero-Token Advance Scroll Verification (`_advance_by_scrolling_down`)**: Zero-token computer vision differencing (`verify_screen_scrolled`) visually confirms that content was displaced before triggering the next question solve. If no displacement is detected (e.g. unfocused iframe/quiz viewport), AVA clicks the viewport center to acquire focus and re-scrolls.
  - **Multi-Pipeline Integration**: Supported across autonomous mode loop, `auto_next`, multi-part problem continuation, and manual user advance (F10 hotkey).

### Tests
- Added 4 new test cases in `tests/test_supplementary_and_navigation.py` verifying AI detection of scrolling quizzes, `_advance_by_scrolling_down` execution, focus-retry recovery, and manual F10 advance (61/61 tests passing).

---

## [1.2.2.a] - 2026-09-06

### Added
- **Universal Zero-Token Action Verification System (`core/local_verifier.py`, `core/automation.py`, `core/assistant_engine.py`)**:
  - **Zero-Token Reference Modal Dismissal (`verify_modal_dismissed`)**: AVA captures a pre-open baseline screenshot before inspecting any supplementary reference material. After attempting to close the reference sheet, AVA compares the current screen against the pre-open baseline using local computer vision differencing without consuming AI tokens.
  - **Multi-Tier Reference Dismissal Recovery (`_dismiss_reference_modal_with_verification`)**: If an AI-suggested close button fails to close the reference sheet, AVA autonomously executes progressive fallback tiers:
    - **Tier 1**: Click AI close button coordinate (with `allow_variance=False`).
    - **Tier 2**: Press `Escape` key.
    - **Tier 3**: Click standard top-right modal dismiss button position ('X') on the modal window and viewport corners.
    - **Tier 4**: Click outer modal backdrop margin (closing backdrop-dismissible modals).
    - **Tier 5**: Final `Escape` key press.
    At every tier, visual dismissal is confirmed before resuming the solve pipeline, preventing reference overlays from blocking questions.
  - **Zero-Token Viewport Scroll Displacement & Restoration (`verify_screen_scrolled`)**: Confirms that scroll-down inspection actions actually displaced viewport content. If 0 movement is detected (e.g. unfocused scroll container), AVA focuses the container center and re-scrolls. Confirms scroll-up restoration matches the pre-scroll baseline image.
  - **Zero-Token Drag-and-Drop Verification (`verify_drag_completion`)**: Captures start and destination ROIs before and after dragging to confirm item pickup from source and placement at target; automatically retries with extended hold duration if unconfirmed.
  - **Zero-Token Navigation Verification (`verify_screen_transition`)**: Verifies visual response and page transition after clicking "Check Answer" or "Next Question" buttons; retries with visual center snapping if missed.
  - **Comprehensive Action Logging**: Every single action (`click`, `double_click`, `type_text`, `drag`, `key_press`, `scroll`, `delay`) now records verified boolean and verification reason.

### Tests
- Added 7 new test cases in `tests/test_supplementary_and_navigation.py` and `tests/test_zero_token_verification.py` verifying multi-tier modal recovery, scroll displacement verification, drag completion detection, and navigation transitions (57/57 tests passing).

---

## [1.2.1.a] - 2026-09-05

### Fixed
- **Scrapped Moving Past Target / Overshoot in Mouse Trajectories (`core/automation.py`)**:
  - Eliminated the overshoot mechanism in `move_mouse_humanized` that calculated an overshoot coordinate `(ov_x, ov_y)` past the answer box. This previously caused the cursor to move to the box, overshoot past it, click outside the box (unfocusing the input field), and move back before typing.
  - The cursor now follows a smooth, humanized cubic Bézier arc directly into the exact target coordinates without travelling past or overshooting input boxes.
  - Set `allow_variance=False` when focusing input boxes in `type_text` so the click lands dead center on the box coordinate rather than risking edge jitter.
  - Reduced default Gaussian jitter radius in `apply_click_variance` to a subtle 1-2px range.
  - Added unit test `test_mouse_moves_directly_without_overshoot` verifying direct-to-target execution (50/50 test suite passing).

---

## [1.2.0.a] - 2026-09-05

### Added
- **Supplementary Material & Reference Sheet Inspection Engine**:
  - **Modal / Reference Sheet Opening & Auto-Dismiss (`core/assistant_engine.py`)**: When an academic question relies on a reference sheet, formula table, periodic table, or currency translation chart hidden behind a button or link, AVA now identifies the button, clicks to open the modal view, captures a high-resolution screenshot of the reference material, and immediately closes the reference modal (via its close button or Esc) to cleanly restore the question on screen before solving.
  - **Scrolled View Inspection with Coordinate Invariance**: When question parts, prompt cards, or options extend below the viewport fold, AVA scrolls down, captures a screenshot of the content below the fold, and automatically scrolls back up by the exact inverse delta before answering, ensuring all UI coordinates remain perfectly aligned with the original screen layout.
  - **Multi-Image AI Vision Pipeline (`core/ai_client.py`)**: Updated Gemini, OpenAI (`gpt-4o`), Anthropic Claude, and Custom OpenAI-compatible endpoints to accept multiple images simultaneously (`extra_images`), providing full context to the AI vision models without local lossy stitching.
  - **New HUD State (`ui/hud_overlay.py`)**: Added `EngineState.INSPECTING` (`"● Inspecting Supplementary Material..."` in vibrant magenta) to provide transparent feedback during reference sheet or scrolled view exploration.
  - **Configuration (`config.py`, `config.default.json`)**: Added `auto_inspect_references: bool = True` (enabled by default).

- **Dynamic Navigation & Auto-Next Advance Engine**:
  - **Autonomous Mode Advancing**: Solved issue where `execute_current_solution` failed to advance when in autonomous mode without explicit `auto_next` enabled. `autonomous_mode` now continuously advances through questions seamlessly.
  - **Platform Check-Before-Next Workflow**: Educational platforms (Edgenuity, IXL, DeltaMath, Canvas, Pearson) requiring a "Check Answer" or "Submit" click before revealing the "Next" button are now natively handled. AVA clicks "Check Answer", waits for the platform validation delay (`auto_next_delay`), dynamically inspects the screen for the newly revealed Next button, and clicks it.
  - **Dynamic Next Button Discovery (`AIClient.detect_navigation_button`)**: Dedicated, focused navigation locator prompt identifies "Next", "Continue", "Next Question", "Submit", or forward arrow buttons even if they were not present in the initial question screenshot.
  - **Below-the-Fold Navigation Discovery**: If a "Next" button is positioned below the visible fold after checking, AVA scrolls down 350px, re-captures, locates the navigation button, and advances.
  - **Manual Advance (F10) Discovery**: Pressing F10 now automatically detects and clicks the Next button even if the button was not previously known in `last_result`.

### Tests
- Added `tests/test_supplementary_and_navigation.py` covering multi-image payloads, reference modal inspection and auto-dismiss, scroll and restore coordinate invariance, autonomous mode advancing, and revealed button discovery (total test suite: 49 passing tests).

---

## [1.1.2.a] - 2026-09-05

### Added
- **Zero-Token Answer Verification & Recovery System**:
  - **Local Computer Vision Verification (`core/local_verifier.py`)**: Sub-millisecond zero-AI-token analysis using Pillow and mss to verify answer states without consuming external AI tokens.
  - **Radio Button & Checkbox Active-State Heuristics**: Concentric ring contrast profiling detecting inner bullet dots, colored active fills, and checkbox checkmark strokes across both light and dark themes.
  - **Text Input Glyphs Verification**: Pre- and post-typing image differencing and static glyph density detection confirming text blanks were filled.
  - **Option Row Highlight Detection**: Container-level tint and color change analysis across option cards upon selection.
  - **Smart Leftward Radio/Checkbox Recovery Probing**: If an AI click lands on option text or outside the control, automatically scans leftward in the option row band for the circular or rectangular control and performs an autonomous zero-variance recovery click.
- **Engine State & Idle Guard Invariants (`core/assistant_engine.py`)**:
  - Added new `EngineState.VERIFYING` state during zero-token post-execution checks.
  - **Absolute Invariant**: AVA will **never** transition to `IDLE` and will **never** advance (`auto_next`) if an action fails to confirm an answered state.
  - If actions fail verification after execution and recovery probing, AVA immediately sets `ready_to_advance = False`, halts, and transitions to `EngineState.WAITING_CONFIRMATION` with clear notice: `"UNVERIFIED: Click missed answer. Press F9 to retry."`.
- **HUD Visual Alerts & 1-Click Retry UI (`ui/hud_overlay.py`)**:
  - Amber warning state on unverified actions: `⚠️ Action Missed: Question Not Answered!`.
  - Dynamic confirm button switches to an amber retry action: `[🔄 Retry Answer (F9)]`.
  - Seamless 1-click retry allowing users to re-run the solution or adjust manually without losing context.
- **Diagnostics & Windows Console Resilience**:
  - Protected console output against Windows `cp1252` `UnicodeEncodeError` by sanitizing log handlers and applying safe ASCII prefixes (`[OK]`, `[!]`).
  - Added `tests/test_zero_token_verification.py` verifying detection algorithms, element band discovery, and engine idle-prevention invariants.

### Fixed
- **GUI Answer Display & Multi-Part Alias Synchronization**:
  - Fixed issue where the answer was no longer appearing in the HUD overlay card.
  - Added top-level `"question"`, `"answer"`, and `"reasoning"` requirements into the vision system prompt schema in `core/prompt.py`.
  - Added automatic question/answer synthesis in `core/ai_client.py` so responses structured solely as `items` compose clean top-level answers (e.g. `Part 1: Option A | Part 2: 144`).
  - Updated `_update_result_ui` in `ui/hud_overlay.py` to support all field aliases (`question`/`question_text`/`summary`, `answer`/`correct_answer`/`proposed_answer`) across both main display labels and individual item cards.

---

## [1.1.1.a] - 2026-09-05

### Fixed
- **Settings Dashboard Initialization & AttributeError**:
  - Fixed `AttributeError: 'SettingsWindow' object has no attribute 'hotkey_entries'` during `_build_keys_tab()` which previously caused `__init__` to abort before `_load_values()` was ever called.
  - Pre-initialized `hotkey_entries` and `model_chips` dictionary and list in `SettingsWindow.__init__`.
- **Application Config Retention & Persistence**:
  - Eliminated issue where changed settings were discarded or replaced with empty defaults upon saving.
  - Added entry content clearing (`delete(0, "end")`) prior to inserting values in `_load_values()`.
  - Added hotkey dictionary merging in `_save_and_close()` so missing or blank hotkey fields do not wipe existing keybind configurations.
  - Added multi-tier config path resolution (`get_base_directory()`, `get_config_file_path()`, `get_default_config_file_path()`) in `config.py` preventing packaged executables from reading/writing into `_internal` and ensuring the project's root `config.json` is consistently loaded.
- **AI Model Autofill & Quick Presets**:
  - Fixed empty model dropdown (`combo_model`) by pre-populating available models immediately based on the active AI provider.
  - Added interactive **"✨ Autofill"** button next to Model Name to instantly autofill the top recommended model for the selected provider (`gemini-3.6-flash`, `gpt-4o`, `claude-3-7-sonnet-latest`).
  - Added clickable **Quick Preset Chips** (`⚡ 3.6-flash`, `⚡ 3.5-flash-lite`, `⚡ 2.5-flash`, `⚡ 2.5-pro`, `🤖 4o`, `🧠 3-7-sonnet`, etc.) under the Model selector for 1-click model switching.
  - Added `preserve_model` support in `_on_provider_changed` to keep configured user models intact on load while dynamically switching models on manual provider selection.
  - Safeguarded `_save_and_close()` to automatically fallback to recommended default models if the model field is left blank.
- **Packaging & Deployment**:
  - Bundled `config.default.json` in PyInstaller spec `datas`.
  - Rebuilt standalone executable distribution in `dist/AVA_School_Assistant_2/`.

---

## [1.1.0.a] - 2026-09-05

### Added
- **Human-like Anti-Bot Automation Suite**:
  - **Reading Deliberation Delay**: Calculates realistic human reading times based on question word count (~220 WPM) before answering, with subtle idle cursor wandering across lines of text to mimic natural eye scanning.
  - **Instant Skip on `F9`**: Allows users to instantly bypass reading or review delays by pressing `F9` or clicking the Skip Wait button.
  - **Zero-AI-Token Local Visual Verification** (`core/local_verifier.py`): Sub-millisecond ROI pixel difference verification ensuring target elements visually responded (e.g. radio selected, checkbox checked) without consuming external AI tokens.
  - **Visual Center Snapping**: Automatically scans candidate boundaries and snaps off-center clicks to true visual centroids.
  - **Dynamic Fill-In-The-Blank Layout Shift Tracking**: Fast local template correlation that pre-captures subsequent blank templates before typing into Blank 1 and dynamically adjusts coordinates if the field expands.
  - **Smart Typo Simulation**: Realistic adjacent-key slips on word tokens with human realization pauses and Backspace correction. Pure numbers, math equations, formulas, and code remain 100% typo-free.
  - **Gaussian Click Jitter**: Off-center variance ensuring clicks never land on the exact mathematical center pixel.
  - **Continuous Multi-Part Chain Completion**: Automatically continues solving sequential multi-part questions across Check/Next without stopping until the entire question is completed.
- **Execution & Behavior Settings**:
  - Added UI toggles and sliders in `ui/settings_view.py` for reading deliberation, base reading pause, click jitter, smart typos, local verification, and multi-part chaining.
- **Configuration Security & Secret Protection**:
  - Added clean `config.default.json` template (with empty `api_key: ""` and default preferences) tracked in git.
  - Added `config.json`, `*.local.json`, `*.secret.json`, and log directories to `.gitignore` to prevent any personal API keys or credentials from ever being leaked to version control.
  - Updated `ConfigManager.load()` in `config.py` to seamlessly fallback to `config.default.json` when a local user `config.json` is not yet present.
- **Standalone Executable**:
  - Rebuilt standalone distribution at `dist/AVA_School_Assistant_2/AVA_School_Assistant_2.exe`.
