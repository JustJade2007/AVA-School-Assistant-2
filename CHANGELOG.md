# Changelog

All notable changes to AVA School Assistant 2 will be documented in this file.

The version format is `1.2.3.a`:
- **1**: MAJOR changes or completion
- **2**: Major feature/reworks
- **3**: New features or major bug update
- **a**: Basic bug fixes

---

## [0.4.3.a] - 2026-09-06

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
  - Green pixel markers cannot override AI-detected `unsubmitted` status.
  - Multi-part questions gate advance strictly on `has_pending_items = False`.
- **Auto-Advance Recovery After Correcting Answers**:
  - Resolved issue where AVA went `IDLE` after re-entering a corrected answer or retrying a missed action.
  - Engine clears `is_rethinking`, resets `action_missed`, and restores `ready_to_advance = True` after successful corrective verification.
- **Screen Transition Verification with Dynamic Navigation Fallback**:
  - `verify_screen_transition` added when clicking known `next_button` elements.
  - Falls back to dynamic navigation button discovery if the clicked Next button does not transition the screen.
  - When dynamic detection clicks Submit/Check, AVA waits for the platform to reveal Next, performs a secondary scan, and clicks it.

---

## [0.4.0.a] - 2026-09-06

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

## [0.2.0.a] - 2026-09-05

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
  - Fixed answer no longer appearing in HUD overlay card.
  - Added top-level `"question"`, `"answer"`, and `"reasoning"` into vision system prompt schema.
  - Automatic question/answer synthesis for `items`-only AI responses.
  - `_update_result_ui` updated to support all field aliases across display labels and item cards.
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

## [0.1.0.a] - 2026-09-05

### Added
- **Initial Release — Core AVA School Assistant 2**:
  - Foundational vision-based automation framework connecting to Gemini, OpenAI, Anthropic, and custom AI providers.
  - HUD overlay for real-time status, answer display, and engine state feedback.
  - Hotkey system (F9 solve, F10 advance, configurable keybinds).
  - Standalone executable built via PyInstaller at `dist/AVA_School_Assistant_2/AVA_School_Assistant_2.exe`.
