# Changelog

All notable changes to AVA School Assistant 2 will be documented in this file.

The version format is `1.2.3.a`:
- **1**: MAJOR changes or completion
- **2**: Major feature/reworks
- **3**: New features or major bug update
- **a**: Basic bug fixes

---

## [1.1.3.a] - 2026-09-10

### Added
- **Standalone Executable Distribution Support (`--onefile`)**:
  - Configured PyInstaller specification in `AVA_School_Assistant_2.spec` to build as a self-contained, standalone single-file executable (`--onefile`), eliminating dependency on an external `_internal/` folder.
  - Added `sys._MEIPASS` path candidate resolution in `config.py` (`get_default_config_file_path`) so bundled default templates unpack and load correctly in frozen standalone mode.
  - Updated `core/logger.py` to persist log files alongside the executable in frozen mode (`sys.executable` directory) instead of temporary extract paths.
  - Added `build_exe.bat` for one-click compilation of the standalone portable executable with workpath routed to `%TEMP%` to avoid OneDrive sync lock collisions.
  - Updated `Launch_AVA.bat` to detect and prioritize the standalone `dist\AVA_School_Assistant_2.exe` while preserving backwards compatibility.

---

## [1.1.2.a] - 2026-09-06

### Added
- **Per-Input Failsafe Verification & 3-Stage Zero-Token Recovery**:
  - Immediate zero-token failsafe verification after each individual input action (clicks and keystrokes).
  - 3-stage zero-token recovery on failed typing verification (box contour centroid targeting, double-click activation, inner left-margin offset).
  - Per-input verification results tracked in `execute_action_sequence`; engine gates answer confirmation on zero `failed_inputs`.
- **Dropdown Question Inspection Architecture**:
  - `open_dropdown` / `inspect_dropdown` capability for dropdown-based questions.
  - AVA clicks the dropdown trigger, verifies option expansion, captures the revealed menu as a supplementary view, and dismisses it before selecting.
- **Softlock Prevention on Pre-Next & Second-Next Screen Checks**:
  - If a question is visually graded incorrect (red rejection markers or error alerts), AVA halts advance, sets `evaluation_status = "incorrect"`, and triggers the rethink pipeline.
- **Fill-In-The-Blank Input Box Targeting**:
  - Model outputs `box_2d` bounding boxes; refined contour detection snaps click targets to the center of the middle 50% horizontal span of input fields.
- **Positive Feedback Modal Handling**:
  - Vision prompt prioritizes semantic positive feedback ("Correct!", green checkmarks) over raw pixel heuristics to prevent wasteful rethinking loops.

### Fixed
- **Next Button Duplicate Click Debouncing & Rate Limiting**:
  - Thread-safe navigation rate-limiting (`_can_click_next` with 2.0s minimum interval).
  - Suppressed duplicate clicks from race conditions or secondary fallback scans firing while the page is loading.
  - Replaced single 0.4s transition check with multi-interval polling (up to 1.4s) for SPA rendering delays.
- **Unanswered Question Advance & Skip Prevention**:
  - Enforced safety invariants across prompt rules, coordinate mapping, and solution execution — prohibiting Next when questions remain unsubmitted.
  - AIClient forces `ready_to_advance = False` whenever an unsubmitted question has 0 actions or incomplete items.
  - Hardened platform evaluation heuristics so local green pixel markers cannot override an AI-detected `unsubmitted` status.
  - In multi-part questions, gating advance strictly on completion of all sub-parts (`has_pending_items = False`).
- **Auto-Advance Recovery After Correcting Answers**:
  - Resolved issue where AVA went `IDLE` after re-entering a corrected answer or retrying a missed action.
  - Engine clears `is_rethinking`, resets `action_missed`, and restores `ready_to_advance = True` after successful corrective verification.
- **Screen Transition Verification with Dynamic Navigation Fallback**:
  - `verify_screen_transition` added when clicking known `next_button` elements.
  - Falls back to dynamic navigation button discovery if the clicked Next button does not transition the screen.
  - When dynamic detection clicks Submit/Check, AVA waits for the platform to reveal Next, performs a secondary scan, and clicks it.

### Added
- **Per-Input Failsafe Verification & 3-Stage Zero-Token Recovery (`core/automation.py`, `core/local_verifier.py`, `core/assistant_engine.py`)**:
  - Implemented immediate zero-token failsafe verification after *each* individual input action (clicks and typing keystrokes).
  - If typing verification detects empty input or unconfirmed text insertion, automatically executes 3-stage zero-token recovery (box contour centroid targeting, double-click activation, inner left-margin offset) without extra token expenditure.
  - Per-input verification results tracked in `execute_action_sequence`; `AssistantEngine` gates answer confirmation on zero `failed_inputs`.
- **Dropdown Question Inspection Architecture (`core/prompt.py`, `core/ai_client.py`, `core/assistant_engine.py`)**:
  - Added `open_dropdown` / `inspect_dropdown` capability for dropdown-based questions with arrows or unstated options.
  - AVA clicks the dropdown trigger, visually verifies option expansion, captures the revealed menu as a supplementary view (`extra_images`), and cleanly dismisses the dropdown with Escape before selecting the correct option.
- **Softlock Prevention on Pre-Next & Second-Next Screen Checks (`core/assistant_engine.py`)**:
  - When checking for or clicking the second Next button, AVA inspects the screen with zero-token grading heuristics (`detect_platform_evaluation_markers`).
  - If the question was visually graded incorrect (e.g. red rejection markers or error alerts), AVA halts advance immediately, sets `evaluation_status = "incorrect"`, and triggers the rethink solve pipeline, preventing softlocking in continuous incorrect loops.
- **Fill-In-The-Blank Input Box Targeting (`core/prompt.py`, `core/ai_client.py`, `core/local_verifier.py`, `core/assistant_engine.py`)**:
  - Model outputs `box_2d` bounding boxes for text inputs; client preserves `box_screen`.
  - Refined contour detection snaps click targets to the center of the middle 50% horizontal span of input fields to ensure accurate clicks regardless of screen position.
- **Positive Feedback Modal Handling (`core/prompt.py`, `core/assistant_engine.py`)**:
  - Instructed vision prompt to prioritize semantic positive feedback ("Correct!", green checkmarks) over raw pixel heuristics, preventing wasteful rethinking loops when an answer is already verified correct.

## [0.4.1.a] - 2026-09-06

### Fixed
- **Auto-Advance Recovery After Correcting Answers (`core/assistant_engine.py`)**:
  - Resolved an issue where AVA aborted auto-advance and went `IDLE` ("Incomplete parts remaining") after re-entering a corrected answer or retrying a missed action.
  - When the AI rethinks an incorrect answer or retries a missed click/typing action, zero-token verification verifies that the answer is in place (`is_answered = True`). The engine now immediately clears `is_rethinking`, resets `action_missed`, and restores `ready_to_advance = True` (provided all other parts are completed).
  - AVA proceeds directly to submit/advance and click the Next button without stopping or giving up.
- **Screen Transition Verification with Dynamic Navigation Fallback (`core/assistant_engine.py`)**:
  - Added screen transition verification (`verify_screen_transition`) when clicking known `next_button` elements.
  - If a clicked Next button does not transition the screen (e.g. coordinates shifted, button disabled until post-submit, or platform layout changed), AVA immediately falls back to dynamic navigation button discovery (`_discover_and_click_next_button`) instead of failing silently.
  - When dynamic navigation detection clicks a Submit or Check button, AVA now waits for the platform to reveal the Next button, performs a secondary scan, and clicks the revealed Next button automatically.

## [0.4.0.a] - 2026-09-06

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

## [0.3.3.b] - 2026-09-06

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

## [0.3.3.a] - 2026-09-06
>>>>>>> 684e3ae5687d654aade4b1974ac96fdd75c7e719

### Added
- **Platform Evaluation Status & Answer Rethinking Architecture**:
  - Vision prompt and response models formally categorize question status into `"correct"`, `"incorrect"`, and `"unsubmitted"`.
  - **Mandatory Rethinking on Incorrect Answers**: When `"incorrect"`, AVA triggers a dual-dimension rethink — academic problem reasoning and input/formatting methodology. Emits `clear_first: true` on corrective actions.
  - **Zero-Token Platform Evaluation Marker Detection**: Local CV detects dominant color clusters — red = rejection, green = verified success — without consuming AI tokens.
  - **Post-Submission Feedback Capture**: After clicking "Check Answer"/"Submit", if the platform returns red error feedback, AVA intercepts auto-advance and triggers the rethink cycle.
  - **Multi-Part Evaluation Propagation**: If any sub-part is `"incorrect"`, top-level `ready_to_advance` is forced to `False`; correct parts remain untouched.
  - **HUD Overlay Evaluation Badges**: `✓ PLATFORM: CORRECT`, `❌ PLATFORM: INCORRECT -> RETHINKING`, and `● PLATFORM: UNCHECKED / DRAFT` badges plus a high-visibility rethinking strategy banner.
- **API Key Persistence Across Application Restarts**:
  - Explicit provider-specific storage fields (`gemini_api_key`, `openai_api_key`, `anthropic_api_key`, `custom_api_key`) in `AppConfig`.
  - Automatic fallback chain across provider fields, generic `api_key`, and system environment variables.
  - Closing Settings via titlebar "✕" now auto-commits all entered keys and preferences.
  - Successful "Test API Connection" automatically commits credentials to `config.json`.
  - Switching providers caches the previous key and restores the selected provider's key.
  - `config_manager.save()` flush added on application shutdown.
- **AI-Detected Scrolling Quiz Advancing**:
  - Dynamic detection of single-page scrolling quizzes (Google Forms, Canvas, Microsoft Forms) without a Next button between questions.
  - Purely AI-governed: distinguishes `advance_action: "click_button"` vs `"scroll_down"` with no config toggles.
  - Zero-token `verify_screen_scrolled` confirms content displacement; clicks viewport center to re-focus if no movement detected.
  - Supported in autonomous mode, `auto_next`, multi-part continuation, and manual F10 advance.

---

<<<<<<< HEAD
=======
## [0.3.2.a] - 2026-09-06

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

## [0.3.1.a] - 2026-09-05

### Fixed
- **Scrapped Moving Past Target / Overshoot in Mouse Trajectories (`core/automation.py`)**:
  - Eliminated the overshoot mechanism in `move_mouse_humanized` that calculated an overshoot coordinate `(ov_x, ov_y)` past the answer box. This previously caused the cursor to move to the box, overshoot past it, click outside the box (unfocusing the input field), and move back before typing.
  - The cursor now follows a smooth, humanized cubic Bézier arc directly into the exact target coordinates without travelling past or overshooting input boxes.
  - Set `allow_variance=False` when focusing input boxes in `type_text` so the click lands dead center on the box coordinate rather than risking edge jitter.
  - Reduced default Gaussian jitter radius in `apply_click_variance` to a subtle 1-2px range.
  - Added unit test `test_mouse_moves_directly_without_overshoot` verifying direct-to-target execution (50/50 test suite passing).

---

>>>>>>> 684e3ae5687d654aade4b1974ac96fdd75c7e719
## [0.3.0.a] - 2026-09-05

### Added
- **Universal Zero-Token Action Verification System**:
  - **Reference Modal Dismissal**: Pre-open baseline screenshot compared via local CV after close attempt — no AI tokens consumed.
  - **Multi-Tier Reference Dismissal Recovery**: 5-tier progressive fallback (AI coordinate → Escape → top-right X → backdrop click → final Escape), visually confirmed at each tier.
  - **Viewport Scroll Verification**: Confirms content displacement; re-focuses and re-scrolls if no movement detected; confirms scroll-up restores baseline.
  - **Drag-and-Drop Verification**: Captures start and destination ROIs before/after dragging; retries with extended hold duration if unconfirmed.
  - **Navigation Verification**: Verifies visual page transition after clicking Check/Next; retries with center snapping if missed.
  - **Comprehensive Action Logging**: Every action (`click`, `double_click`, `type_text`, `drag`, `key_press`, `scroll`, `delay`) records a verified boolean and reason.
- **Supplementary Material & Reference Sheet Inspection Engine**:
  - AVA identifies reference sheet buttons, opens the modal, captures a high-resolution screenshot, and closes it before solving.
  - Scrolled view inspection with coordinate invariance: scrolls down to capture below-fold content, scrolls back up by exact inverse delta.
  - Multi-image AI vision pipeline across Gemini, OpenAI, Anthropic, and custom endpoints (`extra_images`).
  - New `EngineState.INSPECTING` HUD state (vibrant magenta).
  - `auto_inspect_references: bool = True` config option added.
- **Dynamic Navigation & Auto-Next Advance Engine**:
  - `autonomous_mode` now continuously advances through questions seamlessly.
  - Platform Check-Before-Next workflow: clicks "Check Answer", waits for validation delay, dynamically finds the revealed Next button.
  - `AIClient.detect_navigation_button` locator for Next/Continue/Submit buttons even if absent in the initial screenshot.
  - Below-the-fold navigation discovery: scrolls down 350px if Next is not visible after checking.
  - F10 manual advance automatically detects and clicks Next even if not previously known.

### Fixed
- **Mouse Trajectory Overshoot Eliminated**:
  - Removed the overshoot mechanism in `move_mouse_humanized` that previously caused clicks to land outside input boxes.
  - Cursor now follows a smooth cubic Bézier arc directly to exact target coordinates.
  - `allow_variance=False` applied when focusing input boxes; Gaussian jitter radius reduced to 1–2px.

---

<<<<<<< HEAD
## [0.2.0.a] - 2026-09-05
=======
## [0.2.2.a] - 2026-09-05
>>>>>>> 684e3ae5687d654aade4b1974ac96fdd75c7e719

### Added
- **Zero-Token Answer Verification & Recovery System**:
  - Sub-millisecond local CV verification via Pillow and mss — no external AI tokens.
  - Radio button & checkbox active-state heuristics: concentric ring contrast profiling, colored fills, checkmark strokes.
  - Text input glyphs verification via pre/post-typing image differencing and static glyph density detection.
  - Option row highlight detection: container-level tint and color change analysis.
  - Smart leftward radio/checkbox recovery probing if the AI click lands on text instead of the control.
- **Engine State & Idle Guard Invariants**:
  - New `EngineState.VERIFYING` state during zero-token post-execution checks.
  - AVA will **never** transition to `IDLE` or auto-advance if an action fails to confirm an answered state.
  - On failed verification: sets `ready_to_advance = False`, transitions to `WAITING_CONFIRMATION`, and notifies `"UNVERIFIED: Click missed answer. Press F9 to retry."`.
- **HUD Visual Alerts & 1-Click Retry**:
  - Amber warning state: `⚠️ Action Missed: Question Not Answered!`.
  - Dynamic confirm button switches to `[🔄 Retry Answer (F9)]`.
- **Human-like Anti-Bot Automation Suite**:
  - Reading deliberation delay based on question word count (~220 WPM) with idle cursor wandering.
  - Instant skip via `F9` or Skip Wait button.
  - Visual center snapping to true visual centroids.
  - Dynamic fill-in-the-blank layout shift tracking via fast local template correlation.
  - Smart typo simulation with human realization pauses and Backspace correction — math/formulas/code always typo-free.
  - Gaussian click jitter for off-center variance.
  - Continuous multi-part chain completion across Check/Next.
- **Execution & Behavior Settings**:
  - UI toggles and sliders for reading deliberation, base reading pause, click jitter, smart typos, local verification, and multi-part chaining.
- **Configuration Security & Secret Protection**:
  - `config.default.json` template tracked in git; `config.json`, `*.local.json`, `*.secret.json`, and log directories added to `.gitignore`.
  - `ConfigManager.load()` falls back to `config.default.json` when a local `config.json` is absent.
- **Diagnostics & Windows Console Resilience**:
  - Protected console output against Windows `cp1252` `UnicodeEncodeError` with safe ASCII log prefixes.

### Fixed
- **GUI Answer Display & Multi-Part Alias Synchronization**:
<<<<<<< HEAD
  - Fixed answer no longer appearing in HUD overlay card.
  - Added top-level `"question"`, `"answer"`, and `"reasoning"` into vision system prompt schema.
  - Automatic question/answer synthesis for `items`-only AI responses.
  - `_update_result_ui` updated to support all field aliases across display labels and item cards.
=======
  - Fixed issue where the answer was no longer appearing in the HUD overlay card.
  - Added top-level `"question"`, `"answer"`, and `"reasoning"` requirements into the vision system prompt schema in `core/prompt.py`.
  - Added automatic question/answer synthesis in `core/ai_client.py` so responses structured solely as `items` compose clean top-level answers (e.g. `Part 1: Option A | Part 2: 144`).
  - Updated `_update_result_ui` in `ui/hud_overlay.py` to support all field aliases (`question`/`question_text`/`summary`, `answer`/`correct_answer`/`proposed_answer`) across both main display labels and individual item cards.

---

## [0.2.1.a] - 2026-09-05

### Fixed
>>>>>>> 684e3ae5687d654aade4b1974ac96fdd75c7e719
- **Settings Dashboard Initialization & AttributeError**:
  - Fixed `AttributeError: 'SettingsWindow' object has no attribute 'hotkey_entries'` aborting `__init__` before `_load_values()`.
  - Pre-initialized `hotkey_entries` and `model_chips` in `SettingsWindow.__init__`.
- **Application Config Retention & Persistence**:
  - Eliminated settings being replaced with empty defaults on save.
  - Entry content now cleared before inserting values in `_load_values()`.
  - Hotkey dictionary merging in `_save_and_close()` so blank fields don't wipe keybinds.
  - Multi-tier config path resolution preventing packaged executables from reading/writing into `_internal`.
- **AI Model Autofill & Quick Presets**:
  - Fixed empty model dropdown by pre-populating models based on active AI provider.
  - Added **"✨ Autofill"** button for 1-click top recommended model fill.
  - Added **Quick Preset Chips** for instant model switching.
  - `preserve_model` support keeps user-configured models intact on load.
  - `_save_and_close()` falls back to recommended defaults if the model field is blank.
- **Packaging & Deployment**:
  - Bundled `config.default.json` in PyInstaller spec `datas`.
  - Rebuilt standalone executable distribution.

---

<<<<<<< HEAD
## [0.1.0.a] - 2026-09-05
=======
## [0.2.0.a] - 2026-09-05
>>>>>>> 684e3ae5687d654aade4b1974ac96fdd75c7e719

### Added
- **Initial Release — Core AVA School Assistant 2**:
  - Foundational vision-based automation framework connecting to Gemini, OpenAI, Anthropic, and custom AI providers.
  - HUD overlay for real-time status, answer display, and engine state feedback.
  - Hotkey system (F9 solve, F10 advance, configurable keybinds).
  - Standalone executable built via PyInstaller at `dist/AVA_School_Assistant_2/AVA_School_Assistant_2.exe`.
