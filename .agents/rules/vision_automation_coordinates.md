# Vision Automation Coordinate & Spatial Normalization Rules

1. **Gemini 0-1000 Coordinate Invariant**:
   - Google Gemini vision models natively tokenize spatial coordinates on a normalized [0, 1000] integer grid (0 = 0%, 1000 = 100%).
   - Prompts to vision models must explicitly instruct coordinates in the normalized [0, 1000] space.
   - Descaling to screen coordinates must ALWAYS use:
     `screen_x = int((model_x / 1000.0) * screen_width + offset_x)`
     `screen_y = int((model_y / 1000.0) * screen_height + offset_y)`
   - Never treat vision model outputs as raw pixel coordinates unless explicitly bounded and verified.

2. **High-DPI Awareness on Windows**:
   - Always initialize Win32 DPI awareness (`SetProcessDpiAwareness(2)`) before window subsystem initialization.
   - Account for Windows display scaling (e.g. 125%, 150%, 200%) when translating between physical capture pixels and logical GUI overlays.
   - Provide manual calibration offsets (X/Y px) and scale multipliers to accommodate multi-monitor setups and non-standard DPI boundaries.
