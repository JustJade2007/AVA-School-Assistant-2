# Changelog

All notable changes to AVA School Assistant 2 will be documented in this file.

The version format is `1.2.3.a`:
- **1**: MAJOR changes or completion
- **2**: Major feature/reworks
- **3**: New features or major bug update
- **a**: Basic bug fixes

## [2.2.3.a] - 2026-09-21

### Fixed & Improved
- **Eliminated Erroneous Scrolling Before Answer Selection**:
  - Resolved an issue where AVA evaluated the screen, scrolled down, and then attempted to click answer choices whose coordinates were displaced by the scroll.
  - **Choice-to-Action Fallback Synthesis**: In [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) and [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), if the AI identifies candidate multiple-choice points and returns an answer but omits an explicit `actions` array, AVA automatically synthesizes the click action targeting the matching choice.
  - **Hardened Cut-Off Question Inspection Guard**: In [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), strictly disabled autonomous 500px scrolling when valid choices or answers already exist on screen, preventing false cut-off detection on visible questions.
  - **Prompt Scroll Instructions & Few-Shot Correction**: In [core/prompt.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/prompt.py), added strict rules forbidding `scroll_down` or `needs_more_info` when question choices/inputs are visible, and fixed the few-shot JSON example where `"in_scrolled_view": true` was erroneously set on normal question inputs.
  - **Viewport Restoration & Alignment Guards**:
    - In [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), if supplementary scrolling occurs but returned actions target elements in the upper view, the viewport is automatically restored to the top before deliberation and execution.
    - Added pre-execution viewport synchronization in `execute_current_solution` ensuring the viewport matches the action's target view before capturing ROIs or clicking.
  - **Automation Sequence Scroll Guard**: In [core/automation.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/automation.py), suppressed raw `scroll` actions inside answer selection sequences to prevent moving target coordinates from under the cursor.

## [2.2.2.a] - 2026-09-21

### Fixed & Improved
- **Automated 5-Second Missed Action Retry & Click Offset Memory Tracking**:
  - Replaced the static, blocking `"Action Missed: Question Not Answered!"` error state with an autonomous, non-blocking 5-second countdown retry sequence in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py).
  - Implemented persistent click offset memory (`_action_offset_memory`): tracks intended coordinate $(X, Y)$ vs actual clicked coordinate $(X, Y)$ and relative offset $(\Delta X, \Delta Y)$ across execution attempts in [core/automation.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/automation.py) and [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py).
  - During automatic retries, previously failed coordinates are retained in `prior_attempted_coords` and excluded so the recovery probing algorithm shifts and re-targets accurately rather than repeating the exact same miss.
  - Added HUD overlay status representation with dynamic countdown timer and offset telemetry: `⚠️ Retrying in {s}s... (Offset: {dx:+d}px, {dy:+d}px)` in [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py).
- **Website-Agnostic Relative Sibling Multiple-Choice Selection Detection**:
  - Implemented multi-point relative comparative choice verification (`compare_choice_to_siblings` and `_extract_control_features`) in [core/local_verifier.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/local_verifier.py).
  - Rather than relying solely on hardcoded contrast or luminance thresholds, AVA extracts feature descriptors (center luminance, border contrast, saturation, glyph edges, and holistic color profiles) across all candidate sibling choices on screen to compute an unselected baseline.
  - Robustly identifies selections across diverse website design paradigms (filled inner dots, colored radio borders, checkmarks, tinted option rows, SVG fill changes, and dark/light themes) with zero additional AI tokens.
  - Updated vision system prompt [core/prompt.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/prompt.py) and AI client coordinate mapper [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) to capture sibling choice coordinates (`choices`) directly from the visual breakdown.
- **Elimination of Infinite Answer Re-Click Loops**:
  - Fixed an issue where questions already answered and verified on screen were repeatedly clicked until giving up.
  - Added pre-execution selection guards in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py): before dispatching clicks, AVA checks whether the target choice is already selected relative to siblings. If selected, the action is suppressed, `needs_action` is cleared, and AVA advances immediately.
  - Fixed post-verification advance looping: if all questions on screen are answered but the platform navigation transition fails or requires manual submission, AVA transitions cleanly into `WAITING_CONFIRMATION` instead of restarting solving on the exact same questions.

## [2.2.1.a] - 2026-09-21

### Added
- **Automated Worker One-Click GitHub Issue Reporting**:
  - Added a dedicated `🐛 Report on GitHub` action button inside the Automated Worker HUD error card ([ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py)) and the Debug Inspector Error Diagnostics panel ([ui/debug_window.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/debug_window.py)).
  - Implemented `generate_github_issue_url` in [core/error_handler.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/error_handler.py) to automatically pre-fill GitHub bug reports according to `.github/ISSUE_TEMPLATE/bug_report.md` with:
    - Target repository: `https://github.com/JustJade2007/AVA-School-Assistant-2/issues/new`.
    - Automated bug title matching failing component and error summary.
    - Application version (`2.2.1.a`).
    - AI Provider and AI Model (`gemini-3.8-flash`, etc.).
    - Automated troubleshooting recommendations and formatted error traceback.
- **Comprehensive Privacy & Secret Sanitization**:
  - Implemented `sanitize_sensitive_info` in [core/error_handler.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/error_handler.py), strictly masking:
    - All configured API keys (`gemini_api_key`, `openai_api_key`, `anthropic_api_key`, `custom_api_key`, `api_key`).
    - API key token patterns (`AIza...`, `sk-...`, `sk-ant-...`, Bearer auth tokens).
    - Local filesystem usernames in paths (`C:\Users\<username>\...` -> `C:\Users\[USERNAME]\...`).
    - Local machine hostnames and email addresses.
  - Added dual-clipboard integration: clicking "Report on GitHub" simultaneously copies the full sanitized diagnostic report to the user's clipboard while safely capping browser query length below HTTP 414 URL limits.
- **Unit Test Coverage**:
  - Added [tests/test_github_issue_reporting.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/tests/test_github_issue_reporting.py) testing key redaction, user path sanitization, issue URL formatting, and diagnostic object helpers.

## [2.2.0.b] - 2026-09-21

### Fixed
- **Scroll-Down Auto-Next Navigation AttributeError**:
  - Resolved `AttributeError: 'ScreenCapture' object has no attribute 'get_primary_monitor'` during single-page scrolling test progression in [_advance_by_scrolling_down](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py).
  - Added `get_primary_monitor()` method to [core/capture.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/capture.py) as an alias for `get_screen_bounds(monitor_idx=1)`.
  - Hardened monitor bounds coordinate calculation in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py) to safely support multi-monitor coordinate offsets (`left`, `top`) and fallback safely if bounds retrieval is unavailable.
  - Added unit test coverage in `tests/test_supplementary_and_navigation.py` and `tests/test_core.py`.

## [2.2.0.a] - 2026-09-21

### Added & Improved
- **Automated Worker (HUD) Cosmetic Rework**:
  - **Seamless Rounded Window Smoothing**:
    - Applied Windows transparent color-keying (`-transparentcolor` `#010203`) to [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py), perfectly eliminating black outer rectangular window corners and allowing the rounded blue card (`corner_radius=14`, `padx=4, pady=4`) to float smoothly on the desktop.
  - **High-DPI Vector Icons System**:
    - Created [ui/hud_icons.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_icons.py) providing high-DPI procedural PIL vector rendering with 4x supersampling, Lanczos downscaling, and caching.
    - Replaced emojis and text characters with crisp vector icons across HUD header buttons (Close, Minimize, Collapse, Settings, Debug, Snip, Playground) and action controls.
  - **Dynamic Status & Text Animations**:
    - Implemented `_start_status_pulse()` and `_stop_status_pulse()` in [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py), giving active working states (Scanning, Thinking, Reading, Executing, Verifying, Inspecting, Navigating) an organic breathing glow transition on the status indicator.
    - Added `_animate_typewriter_text()` with automatic task scheduling and cleanup, smoothly revealing question and answer solutions chunk-by-chunk upon reception.
  - **Modern Unified Floating Control Dock**:
    - Replaced legacy button grid with a modern floating action dock (`dock_frame`):
      - Primary Hero Action Row (`actions_dock_frame`): Pill-styled buttons for **Solve [F8]**, **Execute [F9]**, **Next [F10]**, and **Stop [F12]** with embedded hotkey badges and vector icons.
      - Auxiliary Utilities Row (`aux_dock_frame`): Sleek compact buttons for **Pause [F7]**, **▲ Scroll**, **▼ Scroll**, **Inspect**, and **Cloak Proof**.
      - Maintained full backwards compatibility with hotkey listeners, auto-execution routines, and collapse toggling.

## [2.1.6.a] - 2026-09-21

### Added & Improved
- **AI Visual Double-Check & Self-Correction Before Advancing**:
  - Implemented visual double-checking in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py) (`_double_check_answers_on_screen`), automatically verifying the question and all selected answers on screen after choosing answers and before clicking Next, Check Answer, or Submit.
  - Added dedicated double-check prompt `get_double_check_prompt` in [core/prompt.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/prompt.py) instructing the vision model to inspect the post-execution screen and verify that visible selections (filled radio buttons, checked boxes, typed text) accurately and completely match the correct answer.
  - Added mistake detection and classification: distinguishes `wrong_option` (clicked wrong radio/checkbox), `unclicked_option` (missed click / unselected option), `missing_selection` (missed multi-select item), and `wrong_text` (mistyped or unfilled input).
  - Added autonomous self-correction loop: if a mistake is detected, the AI generates and executes exact corrective actions (e.g. clicking the correct option, unchecking wrong options, or re-typing) and re-verifies up to `max_double_check_retries` before permitting progression.
  - Added `double_check_solution` in [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) with automatic screen coordinate translation for corrective actions.
  - Added configuration options `double_check_enabled: bool = True` and `max_double_check_retries: int = 2` in [config.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/config.py).

## [2.1.5.b] - 2026-09-21

### Fixed & Improved
- **Elimination of Unnecessary Down-Scroll Before Clicking Next Button**:
  - Resolved an issue in [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) where navigation buttons (`next_button`, `check_button`, `submit_button`) were unconditionally tagged with `in_scrolled_view = True` due to their vertical coordinate (`by >= 350`), causing the automated worker to scroll down 500px prior to clicking Next on normal single-view screens.
  - Added multi-view awareness (`has_multi_view`) to `_map_coordinates`: in single-view captures (`has_multi_view = False`), all buttons and actions strictly preserve `in_scrolled_view = False`.
  - Added viewport alignment safeguards in `trigger_next_button()`, `trigger_check_button()`, and `trigger_submit_button()` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py) ensuring that unless the viewport is already scrolled or extra supplementary images were actively used during the solve pipeline, `is_scrolled` is forced to `False`, preventing unwanted down-scroll displacement before button interaction.
  - Preserved natural continuous scrolling quiz progression (`advance_action: "scroll_down"`) and scrolled multi-view question interaction without viewport jitter.

## [2.1.5.a] - 2026-09-21

### Added & Improved
- **Single-Instance Application Enforcement & Automatic Foreground Activation**:
  - Implemented [core/single_instance.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/single_instance.py) utilizing a named Win32 kernel Mutex (`Local\AVASchoolAssistant2_SingleInstance_Mutex`) and loopback IPC socket (`127.0.0.1:49285`).
  - Added duplicate instance prevention in [main.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/main.py): launching `AVA_School_Assistant_2.exe` while another copy is already running detects the existing process, transmits an activation signal, restores any minimized application windows, brings the running application to the foreground via `AttachThreadInput` / `SetForegroundWindow`, and terminates the duplicate process cleanly.
  - Added thread-safe `bring_to_foreground()` in [ui/app.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/app.py) to automatically restore and focus whichever workspace module is currently active (Playground Studio, HUD Overlay, or Command Hub Home).
- **Taskbar & Alt-Tab Minimization Fix**:
  - Created [ui/window_utils.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/window_utils.py) providing `ensure_taskbar_presence()`, enforcing `WS_EX_APPWINDOW` and stripping `WS_EX_TOOLWINDOW` extended styles across all top-level application windows.
  - Removed `overrideredirect(True)` from the root Tk window in [ui/app.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/app.py), eliminating root-level tool window style inheritance that previously caused child windows to disappear from the taskbar and Alt+Tab when minimized.
  - Implemented dynamic display affinity state management via `attach_minimize_restore_handlers()`: temporarily lifts `WDA_EXCLUDEFROMCAPTURE` when windows enter the iconic state to avoid DWM shell enumeration and thumbnail dropout, seamlessly re-enabling anti-capture cloaking upon window restoration.
  - Refactored HUD overlay minimize action (`self.minimize_overlay()`) in [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py) so clicking `—` minimizes normally to the taskbar instead of disappearing via withdraw.
  - Integrated native Win32 `WM_SETICON` loading for 16x16 and 32x32 icons in [ui/asset_loader.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/asset_loader.py) and [ui/window_utils.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/window_utils.py) to ensure custom branding persists on the Windows taskbar and Alt-Tab switcher across all modes.
- **Automated Worker Reopen Title Bar Elimination**:
  - Eliminated `overrideredirect(False)` toggling during HUD overlay minimization in [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py), preserving `overrideredirect(True)` throughout the entire window lifecycle and preventing the default Windows title bar (`WS_CAPTION`) from ever displaying upon restore.
  - Implemented asynchronous Win32 `SC_MINIMIZE` dispatch via `PostMessageW`, enabling standard taskbar minimization without native frame generation.
  - Added `_on_overlay_restored` callback in [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py) to strictly re-apply borderless styling, topmost layer, stealth cloaking, and strip `WS_CAPTION` / `WS_THICKFRAME` extended styles whenever the worker is reopened from the taskbar, Alt-Tab, or duplicate launcher activation.

## [2.1.4.f] - 2026-09-20

### Fixed & Improved
- **Accurate Next vs Submit Classification**:
  - Defined explicit schema separation between single-item verification (`check_button`), progression/navigation (`next_button`), and assessment-level submission (`submit_button`) in [core/prompt.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/prompt.py).
  - Updated AI coordinate mapping in [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) to preserve `submit_button` coordinates and prevent assessment-level submits from being conflated with problem checks or next buttons.
  - Enhanced `detect_navigation_button` to classify buttons into `"submit"`, `"next"`, or `"check"`, preventing misidentification during fallback discovery.
- **Unfinished Work Submission Failsafe**:
  - Implemented `_is_final_submission_button(btn)` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py) to detect final submission buttons (e.g., "Submit Quiz", "Submit Assignment", "Finish Quiz", "Turn In", "Hand In", "Submit All").
  - Implemented `_has_unfinished_work()` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py) to evaluate whether questions remain unresolved, unattempted, incorrectly answered, or actively in rethinking mode.
  - Blocked automated execution and auto-advance from clicking final submission buttons whenever unfinished or incorrect work remains on screen.
  - Added safe `trigger_submit_button()` handler with confirmation verification, ensuring assessment submission requires explicit user validation when work is incomplete.
  - Guarded `is_already_filled` autonomous advance to ensure it only activates for legitimate next buttons and never for assessment submission buttons.
- **Visualizer & HUD Overlay Distinction**:
  - Added distinct visual rendering for `submit_button` in [ui/visualizer.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/visualizer.py) with a dedicated crimson red highlight (`#ef4444`) and `[SUBMIT (FINAL)]` tag.
  - Updated [ui/hud_overlay.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/ui/hud_overlay.py) to dynamically label the button as `🚀 Submit (F10)` when a submit button is detected, providing clear visual status to the user.

## [2.1.4.e] - 2026-09-20

### Fixed & Improved
- **Double Next Button Click Elimination (Mis-input Fix)**:
  - Eliminated the 150ms micro-ROI verification click retries from `trigger_next_button` and `_discover_and_click_next_button` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py). Web page navigation does not alter button pixel values within 150ms; previously, the verifier interpreted this static state as a failed click and executed a firm retry, causing an unintentional double-click.
  - Raised the default navigation debounce interval to 2.5s in `_can_click_next()` to strictly suppress rapid duplicate clicks across all triggers.
  - Ensured all discovered and scrolled Next button clicks call `_record_next_click()` to guarantee debounce enforcement across all navigation pathways.
- **Screen Transition Verification & AttributeError Fix**:
  - Introduced `TransitionResult` in [core/local_verifier.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/local_verifier.py), a `tuple` subclass that supports both legacy tuple-unpacking `(is_transitioned, diff)` and dictionary-style `.get('transitioned')` and `.details`.
  - Fixed an unhandled `AttributeError` in `execute_current_solution` where `trans.get()` crashed on tuple returns, causing the engine to abort transition polling after 0.35s and immediately fall back to dynamic button discovery to click Next again.
  - Expanded screen transition polling from 4 attempts (1.4s) to 12 attempts (~4.2s) in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), providing sufficient time for school platforms to initiate and complete page transitions.
- **Page Loading Patience & Dynamic Settle Stabilization**:
  - Implemented `_wait_for_page_to_settle` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), monitoring for blank loading frames (low standard deviation across pixels) and frame-to-frame visual stabilization (ensuring animations, LaTeX/MathJax rendering, and layout shifts cease) before triggering question solving.
  - Integrated `_wait_for_page_to_settle` across automated solution execution, autonomous already-answered advances, and manual advances (F10) to prevent solving or re-clicking before the new question is completely loaded.

## [2.1.4.d] - 2026-09-20

### Fixed & Improved
- **Viewport Scroll Stabilization & Rapid Jitter Elimination**:
  - Eliminated the rapid "scroll down and scroll up" viewport jump during question inspection and cut-off detection in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py).
  - Retained the scrolled viewport position after capturing the lower area (`_viewport_is_scrolled = True`), ensuring the screen remains aligned with the lower view for immediate, jitter-free action execution without scroll inertia drift.
- **Answer Button Localization & Click Accuracy**:
  - Resolved missed answer clicks by maintaining the scrolled view and auto-tagging all actions and multi-part items discovered during lower view inspection with `in_scrolled_view: True`.
  - Added center tracking (`_last_scroll_center`) in [core/automation.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/automation.py) so `scroll` and `ensure_scrolled_view` always target the validated content area rather than arbitrary cursor positions.
  - Added a 0.45s smooth scroll deceleration settling buffer to allow browser inertial scrolling animations to come to a full stop before input clicks are executed.
- **Next / Check Button Alignment Safeguard**:
  - Fixed the issue where AVA would answer a question in the scrolled view and then scroll back up to the top to click where the Next button was when scrolled down.
  - Implemented a viewport alignment safeguard in `trigger_check_button` and `trigger_next_button` in [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py): if the viewport is currently scrolled down and the button is situated in the lower viewport (`y >= 250`), AVA retains the scrolled position and clicks the button directly on screen instead of scrolling away.
  - Automatically propagated `in_scrolled_view: True` to navigation buttons in [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) when question actions target the lower view.
  - Updated prompt guidelines in [core/prompt.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/prompt.py) for clear attribution of `check_button` and `next_button` in Image 2.

## [2.1.4.c] - 2026-09-20

### Fixed
- **AI Vision `extra_images` UnboundLocalError Fix**:
  - Fixed `UnboundLocalError: cannot access local variable 'extra_images' where it is not associated with a value` in `_run_solve_pipeline` ([core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py)).
  - Initialized `extra_images = []` in all execution branches prior to the supplementary inspection phase, ensuring the variable is always defined when evaluating question cut-off heuristics.
- **Answered Question Evaluation Status & False "Incorrect" / "Unanswered" Prevention**:
  - Prevented answered questions from being falsely categorized as "incorrect" or "unanswered" during automated answering.
  - Raised the visual platform evaluation marker threshold (`min_cluster_pixels`) from 250 to 1200 in [core/local_verifier.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/local_verifier.py) and [core/assistant_engine.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/assistant_engine.py), preventing minor red UI elements (logos, banners, buttons) from triggering false rethink cycles.
  - Prevented local visual markers from overriding AI evaluation when the AI model explicitly confirms `eval_status == 'correct'` or `needs_action is False`.
  - Updated `check_question_evaluation_status` and `execute_current_solution` to recognize when an answer is already filled out and correct on screen (`needs_action is False`, 0 actions required), marking `is_answered = True` and allowing auto-advancing via `next_button` rather than halting or redoing.
  - Updated `AIClient._map_coordinates` in [core/ai_client.py](file:///c:/Users/jacob/OneDrive/Desktop/Coding/AVA-School-Assistant-2/core/ai_client.py) to preserve `ready_to_advance = True` when `needs_action is False`.

## [2.1.4.b] - 2026-09-20

### Fixed
- **Playground Source Materials Remove Button Visibility**:
  - Fixed an issue where source materials with long names or URLs displaced or clipped the `✕` remove button out of view in the Playground Stage 1 sources list.
  - Reordered pack geometry to pack the `✕` remove button against `side="right"` first, ensuring it remains anchored, visible, and clickable regardless of material title length or window dimensions.
  - Implemented smart filename truncation for source items exceeding 45 characters, preserving file extensions while keeping the `(~N words)` count badge clearly readable.
  - Added a lightweight, non-intrusive hover tooltip (`WidgetToolTip`) displaying the complete un-truncated name, material type, word count, and file path.
  - Safeguarded preset removal buttons in the preset manager modal and action buttons in rubric criteria rows by packing right-aligned action buttons before expanding content.

## [2.1.4.a] - 2026-09-20

### Added
- **Independent Academic Metadata Presets (Author, Course, Professor)**:
  - Added independent save, load, and delete management for **Author Name**, **Course Title**, and **Professor / Instructor Name** in Playground Studio.
  - Implemented `AcademicMetadataManager` in `core/playground/metadata_manager.py` to persist presets across application sessions via `AppConfig` and local JSON fallback storage.
  - Updated Stage 1 metadata UI in `ui/playground/workspace.py` with individual `📂 Load ▾` dropdown menus, `💾 Save` preset buttons, and `🗑️` delete buttons for each field.
  - Added an interactive preset management modal for reviewing and deleting saved entries individually per category without affecting other metadata.
  - Added `saved_authors`, `saved_courses`, and `saved_professors` schema fields to `AppConfig` (`config.py`) and `config.default.json`.

## [2.1.3.c] - 2026-09-20

### Fixed
- **Teacher AI Grading `SourceItem` Attribute Fix**:
  - Fixed `AttributeError: 'SourceItem' object has no attribute 'title'` during Teacher AI evaluation on papers with attached sources.
  - Added a `.title` property alias (getter and setter) as well as deserialization title-to-name fallback to `SourceItem` in `core/playground/project_model.py`.
  - Updated source list summarization in `TeacherEvaluator.grade_document` (`core/playground/teacher_evaluator.py`) to safely reference `s.name` with fallback to `s.title`.

## [2.1.3.b] - 2026-09-20

### Fixed
- **Rubric & Outline 'Words Per Point' Prompt & Target Count Disambiguation**:
  - **Rubric Parser Prompt Clarification**: Updated `PlaygroundEngine.parse_rubric` system prompt with explicit instructions that statements like *"__ words per point"*, *"__ words per bullet"*, or *"__ words each"* specify requirements for individual criteria, not the total assignment length.
  - **Outline Formulation Target Calculation**: Updated `PlaygroundEngine.generate_outline` to calculate total document word count as `(words per point) × (number of points/criteria)` and instruct the AI architect to assign each section its corresponding per-point word count rather than collapsing the entire paper to a single point's count.
  - **Multi-Point Constraint Extraction**: Updated `WrittenSolver.extract_detailed_word_constraints` in `core/written_solver.py` with expanded keywords (`point`, `points`, `bullet`, `bullets`, `criterion`, `criteria`, `section`, `topic`) and an optional `item_count` parameter. Prevented setting `total_min_words` to a single point's limit when item count is not yet established.
  - **Playground Auto-Detection & Live Recalculation**: Updated `_auto_detect_word_requirements` in `ui/playground/workspace.py` to auto-calculate `num_points × per_item_words = total_words`, bound real-time detection to `rubric_raw_textbox`, and re-triggered calculation upon criteria parse completion.

## [2.1.3.a] - 2026-09-20

### Added
- **Command Hub Formatted Changelog Viewer**:
  - Added interactive `📜 Changelog` buttons to both the top navigation header and bottom footer of the Command Hub (`HomeDashboard` in `ui/home_view.py`).
  - Implemented `ChangelogViewer` modal dialog (`ui/changelog_viewer.py`) that automatically parses `CHANGELOG.md` and renders formatted release cards with version badges, release dates, version scope pills (`MAJOR REWORK`, `FEATURE UPDATE`, `PATCH / BUG FIX`), categorized headers (`Added`, `Fixed`, `Changed`), and bullet points.
  - Added real-time search and filter bar for instant querying across all version numbers, features, and release notes.
  - Added a toggleable `[ 📝 Raw Markdown ]` view mode for raw text inspection.
  - Bundled `CHANGELOG.md` directly into PyInstaller `datas` in `AVA_School_Assistant_2.spec` for standalone frozen executable support.

## [2.1.2.a] - 2026-09-20

### Added
- **Outline Structure & Formatting Clarification Pop-up**:
  - Clicking `⚡ AI Auto-Generate Outline` now opens a dedicated clarification modal (`_show_outline_clarification_dialog`) before generating section drafts.
  - Allows students to configure and personalize:
    - **Structure Preset**: Standard Academic, Multi-Question/Multi-Part, Scientific (IMRAD), Comparative Analysis, Argumentative/Persuasive, or Auto-Detect.
    - **Target Section Count**: 3 through 8 sections or Auto-Detect.
    - **Heading & Title Naming Style**: Descriptive Academic, Numbered, Question-Based, or Roman Numerals.
    - **Total Word Count Target**: Inline verification and modification before outline formulation.
    - **Student Focus & Personalization Notes**: Text field for specific instructions, themes, mandatory arguments, or required sections.
  - Custom guidelines are passed to `PlaygroundEngine.generate_outline`, producing personalized outlines while maintaining rubric word count normalization.

## [2.1.1.b] - 2026-09-20

### Fixed
- **Web & YouTube Citation Generator Parameter Mismatch**:
  - Added `format_style` parameter and `**kwargs` support to `CitationGenerator.generate()` and `CitationGenerator.generate_citation()` to resolve `TypeError: got an unexpected keyword argument 'format_style'` during web article and YouTube source ingestion.
  - Added defensive error boundaries around citation generation in `ui/playground/workspace.py` for both manual link ingestion and embedded YouTube auto-import.

## [2.1.1.a] - 2026-09-20

### Added
- **Unbiased Teacher AI Grading System (`TeacherEvaluator`)**:
  - Implemented an independent, objective academic instructor persona (`core/playground/teacher_evaluator.py`) to grade documents strictly against assignment rubrics, word count targets, and formatting guidelines.
  - Produces complete grading profiles: letter grade (A+, A, B, etc.), numerical score (0–100), percentage, executive summary, overall commentary, key strengths, and actionable areas for improvement.
  - Automatically reconciles and updates `project.rubric_criteria` checklist status (`fulfilled` and `notes`) in real-time based on the teacher's evaluations.
- **Stage 4 Academic Review UI & Breakdown Inspector**:
  - Integrated Teacher AI Grading card into Stage 4 of Playground Studio with real-time grade badges, score percentages, and critique previews.
  - Added background-threaded grading execution via `🎓 Grade Document with Teacher AI`.
  - Added detailed modal breakdown dialog (`_show_teacher_breakdown_dialog`) displaying comprehensive strengths, improvement areas, and criterion-by-criterion marks and feedback.
- **Rubric Grade Report .docx Export**:
  - Extended `DocumentExporter.export_to_docx` with `teacher_grade_report` support to append a formal "Instructor Evaluation & Rubric Grade Report" section and rubric table to exported Word documents.
  - Added `Include Teacher Evaluation in .docx` checkbox in Stage 4.
- **Project Model Persistence**:
  - Added `teacher_grade_report` to `PlaygroundProject` dataclass and JSON serialization.

## [2.1.0.a] - 2026-09-20

### Added & Reworked
- **Application Command Hub (Home Page)**:
  - Redesigned app startup to launch a dedicated Command Hub (`HomeDashboard` in `ui/home_view.py`) featuring an active AI backend status pill, anti-capture cloaking toggle, and a modular grid of assistant cards:
    - **Automated Worker**: Floating stealth HUD overlay with screen solve, answer injection, and global hotkeys.
    - **Playground Studio**: 4-stage document studio for essays, research papers, and reports.
    - **Settings & Preferences**: Configuration of API keys, model backends, hotkeys, humanizer tones, reading levels, and cloaking.
    - **Extensible Hub Slot**: Pre-wired for future modular expansion (flashcards, quiz generator, AI agents).
  - Floating HUD overlay and global solving hotkeys are deferred until the Automated Worker is explicitly launched.
  - Added seamless `return_to_home()` routing to safely restore the Command Hub and suspend background solving from all modules.
  - Added CLI flags `--worker` (`-w`) and `--playground` (`-p`) in `main.py` for direct launch options.

- **Playground Interactive Rubric Management**:
  - Added `CriterionEditModal` dialog in `ui/playground/rubric_viewer.py` allowing manual addition, editing, and deletion of individual rubric criteria.
  - Added `+ Add Criterion` header action, inline `✏️` edit buttons, and `✕` delete buttons per card with real-time sync to `project.rubric_criteria` and the Stage 2 checklist.

- **Web & YouTube Ingestion & Automatic Academic Citations**:
  - Implemented `WebSourceIngestor` in `core/playground/web_source.py` utilizing public YouTube oEmbed metadata extraction and webpage scraping with high-density academic AI summarization.
  - Implemented `CitationGenerator` formatting formal bibliography entries in **MLA 9th Edition**, **APA 7th Edition**, and **Chicago / Standard Report** formats.
  - Added `🌐 + Web Link` ingestion dialog in Stage 1 and integrated citations into `project.bibliography_entries` and `.docx` Works Cited export.
  - Added automatic scanning and auto-import of embedded YouTube links from imported PDF/DOCX/TXT files, notes, and assignment prompts.

- **Start Over & Recent Projects Quick-Selector**:
  - Added `🔄 Start Over` button in Playground workspace with confirmation dialog to cleanly reset project state and return to Stage 1.
  - Replaced single open dialog with a dynamic `📂 Open Recent ▾` dropdown listing recent `.avaproj` files from `projects/` for 1-click loading, alongside a browse disk fallback.

- **Rubric-Aware Outline Word Count & Goal Counter Fix**:
  - Deep rubric scanning in `PlaygroundEngine.generate_outline` enforcing rubric word counts across all sections and clamping `sec.target_word_count` to prevent AI over-generation (e.g., 50w prompt yields 50w target sections instead of 250w/500w).
  - Enhanced multi-part question count detection in `WrittenSolver.extract_detailed_word_constraints` across compound prompt structures.
  - Stage 3 goal counter accurately reflects the clamped section targets and believable margin status.

### Fixed
- **WebSourceIngestor Fetch Attribute & YouTube Canonicalization**:
  - Added `WebSourceIngestor.fetch` classmethod alias for `fetch_source`.
  - Added automatic URL canonicalization for short links (`youtu.be`) and embed links to `https://www.youtube.com/watch?v=...` before querying oEmbed.
  - Added robust fallback handling for deleted, private, or unavailable videos preventing unhandled HTTP 404 errors.

---

## [2.0.3.d] - 2026-09-20

### Fixed & Improved
- **Believable Word Count Enforcement & Prevention of Massive LLM Over-Generation**:
  - **Multi-Question & Complex Word Requirement Parsing**:
    - Added `extract_detailed_word_constraints` in `core/written_solver.py` detecting multi-part patterns (e.g. *"50 words each for the 5 questions"*, *"50 words each"*, *"50 words per question"*, ranges, and approximate limits) across vision OCR prompts, assignment rubrics, and playground topics.
    - Added automatic total and per-item word scaling (`total_min_words`, `per_item_words`, `num_items`, `max_allowed`).
  - **Authentic Student Believability (10%–20% Error Margin)**:
    - Replaced unconstrained generation with a strict believability principle: target length is set to ~10% above the requirement and strictly capped at 20% above the minimum (e.g. 50 words targets ~55 words and hard caps at 60 words; prevents massive 1,000-word dumps).
    - Rewrote `apply_word_limits` as a classmethod with multi-question paragraph decomposition (`re.split(r"\n+(?=\s*\d+[\.\)]\s+)")`) and sentence-boundary trimming ensuring every sub-question stays strictly within 10%–20% of its individual target.
    - Integrated post-generation, post-humanization, and post-spellcheck trimming across both HUD Written Question solver and Playground Mode.
  - **Playground Mode Dynamic Scaling & Live Believability Indicator**:
    - `PlaygroundEngine.generate_outline` dynamically detects per-question constraints, adjusting total project words (e.g. 5 questions × 50 words = 250 words total instead of default 1,000 words) and assigning 50 words per section.
    - Added real-time prompt/rubric auto-detection in Stage 1 updating `words_entry` and displaying a detected requirement badge.
    - Added live believable word count status (`Words: X / Y • Believable +Z%`) and a manual **✂️ Believable Trim (10-20%)** action in Stage 3 section review.
  - **Vision OCR Prompt Guidance**:
    - Updated `core/prompt.py` with explicit believability and 10%–20% margin rules for vision-detected written responses.

---

## [2.0.3.c] - 2026-09-20

### Fixed
- **Playground Mode Window Launch Crash & Process Orphaning**:
  - Added `@property def ai_client(self) -> AIClient` to `AssistantEngine`, resolving `AttributeError: 'AssistantEngine' object has no attribute 'ai_client'` when launching Playground Mode.
  - Fixed Tkinter `TclError: bad option "-width"` in `ui/playground/workspace.py` by properly configuring frame widths on `CTkFrame` rather than inside `.pack(..., width=...)`.
  - Added automatic `.lift()` and `.focus_force()` to `PlaygroundWorkspace` to ensure it always raises above background applications immediately.
  - Wrapped `_do_open_playground` in `ui/app.py` in a robust try-except error handler that immediately restores the HUD overlay and global hotkeys and displays an error dialog if launch ever fails, preventing the application from hanging as an invisible orphaned background process.

---

## [2.0.3.b] - 2026-09-20

### Improved
- **HUD Overlay Header Bar Redesign & Dynamic Icon Resizing**:
  - Redesigned all header action buttons with sleek circular / pill shapes (`corner_radius = size // 2`) and compact spacing (`padx=1`) to eliminate horizontal crowding.
  - Compacted left branding to `⚡ AVA` and `🛡️ CLOAK` badge, freeing up over 80px of horizontal room on the header.
  - Made the cutout / snip button (`✂️`) distinctly smaller and highlighted with an accent theme.
  - Implemented dynamic icon resizing (`set_header_icon_size`), scalable from 8px to 18px in real time via `<Control-MouseWheel>` over the header bar or the new **Header Icon Size** slider in the Configuration Dashboard.
  - Expanded default overlay width from 460px to 490px with configurable `overlay_width` and `header_icon_size` persistence.

---

## [2.0.3.a] - 2026-09-20

### Added
- **Playground Mode (Semi-Automated Long-Form Document Studio)**:
  - Built a dedicated, cloaked workspace window designed for long-running schoolwork projects, essays, and research papers.
  - **4-Stage Project Pipeline**:
    1. *Rubrics & Sources Ingestion*: Supports screen-snipping rubrics with automatic OCR, importing files (`.pdf`, `.docx`, `.doc`, `.txt`), free-text notes, and AI parsing into structured checklist criteria.
    2. *Outline & Criteria Checklist Mapping*: Formulates ordered section outlines mapped directly to rubric criteria with custom target word counts.
    3. *Section-by-Section Drafting & Humanizing with Mandatory User Review*: Generates drafts with AI, auto-humanizes via **Jade's AI Humanizer**, presents side-by-side comparison, supports direct inline editing, interactive refinement prompts, and per-section review approval.
    4. *Full Document Compilation & Academic Export*: Exports formatted Microsoft Word documents (`.docx`) according to **MLA 9th**, **APA 7th**, or **Standard Report** presets with Works Cited / Bibliography support.
  - **Complete Background Function Isolation**: When Playground Mode is launched, default solving hotkeys (`F8`, `F4`, etc.) and autonomous solving routines are suspended to prevent typing conflicts in Word/browsers, and the HUD overlay is safely hidden until returning.
  - **Project Auto-Save & Recovery**: Saves and loads project state (`.avaproj` / JSON) preserving all rubrics, sources, outlines, and approved drafts across sessions.
  - **Pip & Spec Integration**: Integrated `jades-ai-humanizer`, `python-docx`, and `pypdf`, and added `F3` global hotkey.

---

## [2.0.2.b] - 2026-09-14

### Fixed
- **Resolved API Key `Unexpected token 'I', "Internal S"... is not valid JSON` Crash**:
  - Upgraded Jade's AI Humanizer default model to **Gemini 3.5 Flash Lite** (`gemini-3.5-flash-lite`) and fallback to **Gemini 3.1 Flash Lite** (`gemini-3.1-flash-lite`), resolving Google API `404 NOT_FOUND` deprecation errors for retired `gemini-2.5-flash-lite` and `gemini-2.0-flash-lite` endpoints.
  - Hardened candidate model fallbacks across both synchronous and asynchronous execution paths (`gemini-3.5-flash-lite` -> `gemini-3.1-flash-lite` -> `gemini-3.6-flash` -> `gemini-3.8-flash` -> `gemini-2.5-flash` -> rule-based offline transform).
  - Protected fallback streaming in `generate_stream_sync` and `generate_stream_async` with nested try/except blocks to prevent unhandled streaming exceptions from escaping into the route handler.
  - Added robust exception handling to `/v1/humanize` in `core/humanizer/daemon/routes.py`, returning proper JSON `HTTPException` objects rather than unhandled plain-text 500 `Internal Server Error` responses.
  - Hardened JavaScript `handleHumanize()` in `core/humanizer/daemon/ui.py` to safely inspect error responses without throwing `SyntaxError` on non-JSON payloads.
  - Ensured logger portability across both standalone humanizer execution and bundled AVA Assistant engine.

---

## [2.0.2.a] - 2026-09-11

### Fixed
- **Jade's AI Humanizer Live REST Execution Pipeline**:
  - Fixed a critical bug in `core/humanizer/engine/generator.py` where `_client is None` (due to missing `google-genai` pip package) caused synchronous and asynchronous humanization to unconditionally abort network calls and default to un-transformed offline text.
  - Implemented direct REST API execution via standard `requests` with multi-model fallback (`self.model` -> `self.fallback_model` -> `gemini-3.8-flash` -> `gemini-2.5-flash` -> `gemini-2.0-flash` -> `gemini-1.5-flash`), restoring 100% active live Gemini humanization for all users with configured API keys.
- **Implemented `generate_text_response` in `AIClient`**:
  - Added native text-only response generation to `core/ai_client.py` across Gemini, OpenAI, Anthropic, and Custom providers, resolving an `AttributeError` that previously caused written question drafting to fall back to hardcoded robotic placeholder text.
- **Upgraded Offline Paraphraser Heuristics**:
  - Expanded `STIFF_TRANSITIONS` and pattern sanitizers in `core/humanizer/engine/deep.py` to strip robotic AI hedging (*"Based on the provided information..."*, *"It is important to remember that..."*, *"fundamental principles underlying..."*, *"interact directly to support..."*), normalize sentence starters, and capitalize clauses cleanly.
- **Humanizer Model Alignment & Transformation Tracking**:
  - In `core/written_solver.py`, dynamically passed the user's selected Gemini model to `Humanizer`.
  - Added transformation diff tracking and logging (`is_offline`, `text_changed`, `buzzwords_replaced`, readability scores) to ensure complete visibility into text changes.

---

## [2.0.1.a] - 2026-09-11

### Added
- **Question Viewport Scrolling & Dual-View Scrolled Action Execution**:
  - Implemented automatic and on-demand scrolling down to reveal the entire question when question stems, reading passages, answer choices, or input fields extend below the visible viewport fold.
  - Multi-view solving pipeline: captures Image 1 (top of question) and Image 2 (scrolled lower view), passing both to Gemini with spatial context.
  - Added `ensure_scrolled_view` in `core/automation.py` to dynamically scroll and align the viewport before executing clicks or typing targeting lower-view elements (`in_scrolled_view: True`).
  - Added manual viewport scroll helper buttons to the HUD (`📜 Scroll Down`, `📜 Scroll Up`, `🔍 Inspect Whole Q`).
- **Harden Answer Filled-Out Detection & Placeholder Filtering**:
  - Fixed false-positive detection where blank input boxes or placeholder text (*"Type your answer here..."*, *"Enter response"*, *"Write an essay..."*, *"e.g. 10"*, *"Click to add text"*) were misread as already filled out.
  - Upgraded contrast-aware glyph detection in `is_text_input_filled` (`core/local_verifier.py`) to correctly distinguish typed ink from blank white/dark backgrounds and faint watermark text.
  - Hardened evaluation status invariants in `core/assistant_engine.py`: unsubmitted questions showing "Check Answer" or "Submit" buttons cannot be erroneously promoted to `correct` or skipped.

---

## [2.0.0.a] - 2026-09-11

### Added
- **Written Questions & Essays Engine (AVA 2.0 Major Upgrade)**:
  - Added full end-to-end support for answering written open-ended questions, short answers, paragraphs, and essays using **Gemini 3.8 Flash** (`gemini-3.8-flash`).
  - Implemented multi-tier quality presets:
    - `Realistic Student (B-Grade)`: Authentic student cadence, colloquial flow, realistic punctuation, and non-robotic phrasing.
    - `Solid (A-Grade)`: Clear structured thesis, strong topic sentences, and focused academic argumentation.
    - `Honors / AP`: Advanced analytical depth, elevated vocabulary, and nuanced synthesis.
  - Implemented automatic extraction and enforcement of word count constraints:
    - Parses min/max word limits (e.g. "at least 50 words", "100-150 words", "minimum of 25 words").
    - Configurable word buffer percentage (+10%–20%) and maximum overage cap (+15–25 words) preventing overly verbose AI answers that trigger suspicion.
    - Trims intelligently at natural sentence boundaries without leaving dangling thoughts.
- **Embedded Jade's AI Humanizer Engine**:
  - Bundled [Jade's AI Humanizer](https://github.com/JustJade2007/Jade-s-AI-Humanizer) directly into `core/humanizer/` as an offline client-side library requiring zero external daemons or user installs.
  - Automated buzzword sanitization stripping stereotypical AI clichés (*delve into*, *tapestry of*, *testament to*, *beacon of*, *multifaceted*).
  - Configurable humanizer modes (`budget` vs `deep`), tones (`academic`, `casual`, `neutral`, `professional`), and reading levels (`middle_school`, `high_school`, `college`, `general`).
  - Added REST API fallback supporting student Google API keys without requiring `google-genai` pip dependencies.
- **Local Offline Dictionary Spellchecker & Text Sanitizer**:
  - Created zero-latency O(1) typo corrector in `core/spellcheck.py` covering frequent student slips, contraction repairs, accidental double-word deduplication, and punctuation spacing normalization.
- **Mandatory User Confirmation Safeguard for Written Responses (10+ Words)**:
  - Enforced a hard safety barrier: any written response of 10 or more words automatically pauses at `Waiting for Confirmation` so the student can inspect the draft before typing.
  - Added `Auto-Confirm Written Responses` toggle in Settings for users who deliberately prefer autonomous typing.
- **Live HUD Written Preview & Interactive Text Editor**:
  - Added an expandable written question card in `ui/hud_overlay.py` with an interactive multi-line text editor (`CTkTextbox`).
  - Allows the user to inspect, revise, tweak, or completely rewrite the drafted response before typing.
  - Added live word count badge with color coding (green when meeting word minimum, amber if below minimum).
  - Added `✨ Re-Humanize` button to re-run humanization and buzzword stripping on edited text with a single click.
- **Post-Typing Area Verification**:
  - Integrated `verify_written_input_area` in `core/local_verifier.py` to confirm text ink stroke density and visual change within the bounding box post-typing.
- **Dedicated Settings Tab for Written Questions**:
  - Added `✍️ Written & Humanizer` tab in `ui/settings_view.py` for full configuration of models, quality presets, word buffers, humanizer parameters, spellcheck, and confirmation safeguards.

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
