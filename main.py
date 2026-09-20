"""
AVA School Assistant 2 - Main Entry Point.
Autonomous Schoolwork Solver with Multimodal Vision, GUI Automation,
and Anti-Screen Capture Cloaking.
"""

import sys
import argparse
from ui.app import AVASchoolAssistantApp


def main():
    parser = argparse.ArgumentParser(description="AVA School Assistant 2")
    parser.add_argument(
        "--version",
        action="version",
        version="AVA School Assistant 2 v2.1.0.a"
    )
    parser.add_argument(
        "--worker",
        "-w",
        action="store_true",
        help="Launch Automated Worker (HUD Mode) directly upon start"
    )
    parser.add_argument(
        "--playground",
        "-p",
        action="store_true",
        help="Launch Playground Studio directly upon start"
    )
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Open configuration dashboard directly upon start"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug mode with detailed logs and stack traces"
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Open the cloaked Debug Console window directly upon start"
    )
    args = parser.parse_args()

    start_mode = "home"
    if args.worker:
        start_mode = "worker"
    elif args.playground:
        start_mode = "playground"

    app = AVASchoolAssistantApp(start_mode=start_mode)
    if args.debug:
        from core.logger import set_debug_mode
        set_debug_mode(True)
        app.config_manager.update(debug_mode=True)

    if args.settings:
        app.open_settings()
    if args.logs and app.hud_window:
        app.hud_window.open_debug_window()

    app.run()


if __name__ == "__main__":
    main()
