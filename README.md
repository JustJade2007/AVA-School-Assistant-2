# ⚡ AVA School Assistant 2

**AVA School Assistant 2** is a next-generation autonomous AI desktop assistant designed to solve online schoolwork, quizzes, and assignments on Windows.

It integrates high-resolution screen reading, multimodal vision AI reasoning, humanized mouse and keyboard automation, automatic question navigation, and a hardware-level anti-screen-capture floating HUD overlay.

---

## 🌟 Key Features

1. **Multimodal Screen Reading & Question Identification**:
   - Takes high-DPI screenshots of your active screen or sub-regions.
   - Accurately parses math equations, multiple-choice questions, text entries, and diagrams.
2. **Multi-Part & Nested Box Question Decomposition**:
   - Discovers all questions, parts, and sub-prompts on screen in a single unified pass (e.g. Part A, Part B, nested small boxes).
   - Generates coordinated action sequences across all sub-components.
3. **Platform Evaluation Status & Answer Rethinking**:
   - Explicitly categorizes question visual status into `correct`, `incorrect`, or `unsubmitted` before considering any problem answered.
   - **Mandatory Rethinking on Incorrect Answers**: If a question is graded `incorrect` by the platform (red error marks, "X", "Try again"), AVA is strictly prohibited from considering it answered or advancing. Instead, AVA rethinks:
     1. *Academic problem reasoning*: Analyzes platform hints, error messages, and alternative solution formulas.
     2. *Entry formatting*: Adjusts simplified fraction vs decimal, coordinate syntax, unit placement, and rounding precision.
     3. *Clear first*: Emits `clear_first: true` to purge stale input text before retyping.
   - **Post-Submission Feedback Interception**: Captures the screen following "Check Answer" / "Submit" clicks; halts auto-advance immediately if the platform rejects the submitted answer and automatically triggers the rethink cycle.
   - Visual status badges on the HUD overlay: `✓ PLATFORM: CORRECT`, `❌ PLATFORM: INCORRECT -> RETHINKING`, `● PLATFORM: UNCHECKED / DRAFT`.
4. **Quick Snip Box & Solve (`F4`)**:
   - Drag-select any tricky, small, or nested question box on screen with pixel precision via global hotkey **`F4`** or the **`✂️`** HUD header button.
   - Solves the snipped region directly at 100% native resolution with hardware cloaking.
5. **Precision AI Problem Solving**:
   - Supports **Google Gemini** (`gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`), **OpenAI** (`gpt-4o`), **Anthropic Claude** (`claude-3-7-sonnet`), and custom OpenAI-compatible / OpenRouter endpoints.
   - Determines the exact pixel coordinates required to click radio buttons, checkboxes, inputs, or dropdowns.
6. **Autonomous & Review Modes**:
   - **Autonomous Mode**: Solves questions and answers them immediately without human intervention.
   - **Review Before Action (Default)**: Displays question breakdown, reasoning, and on-screen target markers on the HUD, awaiting your confirmation before executing.
7. **Two-Stage Advance & Scrolling Quiz Detection**:
   - Built specifically for school and quiz platforms (Edgenuity, IXL, Khan Academy, DeltaMath, Pearson, Canvas, Google Forms, Microsoft Forms, etc.).
   - **Continuous Scrolling Quiz Detection**: When questions are stacked vertically down a single continuous page without a "Next" button between questions (e.g. Google Forms, Canvas worksheets), AVA visually detects this and advances by scrolling down to reveal subsequent questions with zero-token visual verification.
   - **Multi-Stage Button Assessments**: Automatically clicks "Check Answer" first, pauses for server-side validation / "Next" button reveal, and then advances seamlessly.
   - Dynamic HUD button updates (`✓ Check`, `✓ Check & Next`, or `⏭ Next`).
   - Auto-advance safety check: requires all parts on screen to be solved or verified before advancing.
8. **Hardware-Level Anti-Screen-Capture HUD Overlay**:
   - Utilizes Windows Win32 `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE = 0x11)`.
   - **100% Invisible** to screen recorders, screenshots (PrintScreen), and screen-sharing software (Zoom, Google Meet, Discord, Microsoft Teams, Honorlock, Proctorio, LockDown Browser), while remaining fully visible to you on your physical monitor.
9. **Human-like Anti-Bot Automation Suite**:
   - **Reading Deliberation Delay**: Calculates realistic human reading times based on question word count (~220 WPM) before answering, keeping the cursor naturally stationary while reading. Pressing **`F9`** skips wait time instantly.
   - **Zero-AI-Token Local Visual Verification & Recovery**: Rapid sub-millisecond local ROI analysis verifies element response (e.g. radio bullet dot, checkbox checkmark, text glyphs) with **0 external AI token cost**. If a click misses or lands on text, automatically scans leftward in the option band and performs an autonomous recovery click.
   - **Engine Idle-Prevention Invariant**: AVA will **never** transition to `IDLE` and will **never** advance if an answer click misses. If unverified after recovery, AVA halts, displays an amber HUD alert, and provides a 1-click retry (**`F9`**).
   - **Dynamic Fill-In-The-Blank Layout Shift Tracking**: When text typed into Blank 1 expands and shifts subsequent blanks, local template matching tracks Blank 2's new position before clicking.
   - **Smart Typo Simulation & Math Protection**: Occasional realistic adjacent-key slips on word tokens with human realization pauses and Backspace correction. Pure numbers, math equations, formulas, and code are 100% protected and typo-free.
   - **Gaussian Click Jitter**: Never clicks the exact mathematical center pixel.
   - **Continuous Multi-Part Completion**: Automatically continues solving multi-part questions across sequential Check/Next steps until all parts are finished.
10. **Emergency Stop / Killswitch**:
   - Instant fail-safe abort key (`F12` or mouse corner drag) that releases buttons and cancels all automation sequences immediately.
11. **Global Hotkeys**:
   - Control the assistant from anywhere on your system, even while other browser or desktop windows are focused.

---

## ⌨️ Default Keybinds

| Keybind | Action | Description |
| :---: | :---: | :--- |
| **`F8`** | **Capture & Solve** | Takes a screenshot of the full question screen and queries the AI model |
| **`F4`** | **Snip Box & Solve** | Drag-select any sub-box or small question area to solve directly |
| **`F9`** | **Confirm & Execute** | Executes the proposed clicks/typing on screen |
| **`F10`** | **Next Question** | Clicks the identified "Next" or "Continue" button |
| **`F7`** | **Pause / Resume** | Toggles pause on the assistant loop |
| **`F12`** | **Emergency Stop** | Instant killswitch that halts all mouse/keyboard actions |
| **`F6`** | **Show / Hide Overlay** | Toggles HUD overlay visibility on/off screen |
| **`Ctrl+Shift+Q`** | **Close Application** | Cleanly exits and shuts down the assistant app |

*All keybinds can be customized in the Configuration Dashboard.*

---

## 🚀 Getting Started

### 1. Installation

Ensure you have Python 3.10+ installed on Windows. Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 2. Launching AVA

Run the main application:

```bash
python main.py
```

Optional launch flags:
- `--settings`: Open configuration dashboard directly upon start
- `--debug`: Enable verbose debug mode with detailed logs and stack traces
- `--logs`: Open the cloaked Debug Console window directly upon start

```bash
# Launch directly in debug mode with live diagnostic console
python main.py --debug --logs
```

You can also run `Launch_AVA.bat` to launch the application directly without opening a terminal window.

### 3. Building Standalone Executable (Distribution)

To compile a single, portable `.exe` that can be moved and run independently on any Windows machine without Python installed:

```bash
# Double-click or run:
build_exe.bat
```

Or run via PyInstaller manually:
```bash
pip install pyinstaller
pyinstaller AVA_School_Assistant_2.spec --workpath "%TEMP%\ava_build" --clean --noconfirm
```

The compiled standalone executable will be saved to:
`dist/AVA_School_Assistant_2.exe`

### 4. Setting Up Your AI Model & API Key

1. Click the **⚙ (Settings)** button on the top-right of the floating HUD, or launch with `--settings`.
2. Select your AI Provider (e.g. **Google Gemini**).
3. Choose your desired model (e.g. `gemini-3.6-flash` or `gemini-3.5-flash-lite`).
4. Paste your API Key into the field.
5. Click **🔗 Test API Connection** to verify that your key is valid and connected.
6. Configure your execution preferences (Autonomous vs Review Mode, Auto-Next toggle, Mouse Pace).
7. Configure display capture resolution and fine-tuning offsets in the **🖥️ Display & Calibration** tab.
8. Configure logging preferences in the **🐞 Debug & Logging** tab.
9. Click **💾 Save & Apply Settings**.

---

## 🐞 Debug & Error Diagnostic System

AVA School Assistant 2 includes an integrated logging and error diagnostic framework designed for debug users and developers:

- **Untruncated Error Transparency**: Error messages are never clipped. Full API response codes and payloads are parsed and presented clearly.
- **Automated Troubleshooting Hints**: Identifies common failures (authentication, rate limits, screen session lock, JSON schema deviations) and provides actionable guidance.
- **1-Click Copy Diagnostic**: Instant clipboard copying of structured error reports, including complete Python stack traces, component context, and timestamps for effortless bug reporting.
- **Anti-Capture Cloaked Debug Console**: Live streaming logs with level filtering (DEBUG, INFO, WARNING, ERROR), regex/keyword search, and disk export—fully protected by hardware-level anti-capture cloaking.
- **Persistent File Logging**: Continuous rotating log output saved to `logs/ava_assistant.log`.

---

## 🛡️ Verifying Anti-Capture Invisibility

To verify that the HUD is completely invisible to screen recording apps:
1. Click the **👁 Verify Cloak** button on the floating HUD overlay.
2. A verification dialog will pop up showing the screenshot taken of the desktop right where the HUD is positioned.
3. You will see that the screen capture engine cannot see the HUD at all.

---

## 📁 Project Architecture

```
AVA-School-Assistant-2/
├── config.py                     # Configuration manager and JSON persistence
├── main.py                       # Desktop application launcher (--debug, --logs, --settings)
├── requirements.txt              # Python dependencies
├── logs/                         # Rotating log storage directory
│   └── ava_assistant.log         # Persistent disk log file
├── core/
│   ├── ai_client.py              # Unified REST API client with structured error parser
│   ├── assistant_engine.py       # State machine orchestrator with ErrorDiagnostic capture
│   ├── automation.py             # Humanized Bézier curves, smart typos, click jitter & failsafes
│   ├── capture.py                # High-DPI screen capture & coordinate scaling
│   ├── cloaking.py               # Win32 SetWindowDisplayAffinity wrapper
│   ├── error_handler.py          # Rich error diagnostics, classification & advice generator
│   ├── hotkeys.py                # Global keybind listener (pynput)
│   ├── local_verifier.py         # Zero-AI-token local ROI verification & layout shift tracking
│   ├── logger.py                 # Core logger with memory buffer & rotating file handler
│   └── prompt.py                 # Multimodal vision system prompt & schemas
├── ui/
│   ├── app.py                    # Main application lifecycle
│   ├── debug_window.py           # Cloaked live log console & error diagnostic inspector
│   ├── hud_overlay.py            # Anti-capture floating HUD window with error actions
│   ├── settings_view.py          # Configuration dashboard with Debug & Logging tab
│   ├── snipping_tool.py          # Interactive cloaked full-screen snip box selector
│   └── visualizer.py             # Cloaked on-screen target highlight canvas
└── tests/
    ├── test_core.py              # Core unit & integration test suite
    └── test_logging_and_errors.py # Dedicated logging & error diagnostic test suite
```

---

## ⚠️ Safety Notice

AVA School Assistant 2 includes PyAutoGUI failsafes. In an emergency, pressing **`F12`** or slamming your mouse cursor into any corner of the screen will immediately abort all automation.
