"""Command Line Interface (CLI) for Jade's AI Humanizer."""

from __future__ import annotations

import argparse
import sys
from typing import Optional


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="humanizer",
        description="Jade's AI Humanizer - Local zero-backend AI text humanization engine.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'serve' subcommand
    serve_parser = subparsers.add_parser("serve", help="Start the local REST and SSE API daemon")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")

    # 'humanize' subcommand
    humanize_parser = subparsers.add_parser("humanize", help="Humanize a text string or file directly from the CLI")
    humanize_parser.add_argument("text", nargs="?", default="", help="Text to humanize (or pass via stdin)")
    humanize_parser.add_argument("--file", "-f", help="Path to text/markdown file to humanize")
    humanize_parser.add_argument("--mode", "-m", choices=["budget", "deep"], default="budget", help="Humanization mode")
    humanize_parser.add_argument(
        "--tone", "-t", choices=["neutral", "casual", "academic", "professional"], default="neutral", help="Tone preset"
    )
    humanize_parser.add_argument(
        "--level", "-l", choices=["general", "middle_school", "high_school", "college"], default="general", help="Reading level"
    )
    humanize_parser.add_argument("--no-markdown", action="store_true", help="Disable markdown structure preservation")

    return parser


def main(args: Optional[list[str]] = None) -> int:
    """Main CLI entry point."""
    import multiprocessing
    multiprocessing.freeze_support()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        # Default to local server daemon on empty args for one-click launch
        print("No command specified. Defaulting to 'serve' on http://127.0.0.1:8000 ...")
        print("Interactive API Docs: http://127.0.0.1:8000/docs")
        print("Run 'humanizer --help' for CLI options.\n")
        parsed_args.command = "serve"
        parsed_args.host = "127.0.0.1"
        parsed_args.port = 8000
        parsed_args.reload = False

    if parsed_args.command == "serve":
        import uvicorn
        from core.humanizer.daemon.app import create_app

        print(f"Starting Jade's AI Humanizer daemon on http://{parsed_args.host}:{parsed_args.port}")
        print(f"Interactive API Docs available at http://{parsed_args.host}:{parsed_args.port}/docs")
        app = create_app()
        uvicorn.run(
            app,
            host=parsed_args.host,
            port=parsed_args.port,
            reload=parsed_args.reload,
        )
        return 0

    if parsed_args.command == "humanize":
        from core.humanizer.client import Humanizer

        input_text = parsed_args.text
        if parsed_args.file:
            with open(parsed_args.file, "r", encoding="utf-8-sig") as f:
                input_text = f.read()
        elif not input_text and not sys.stdin.isatty():
            input_text = sys.stdin.read()

        if not input_text:
            print("Error: No text provided. Supply text as an argument, file via -f, or through stdin.", file=sys.stderr)
            return 1

        client = Humanizer()
        result = client.humanize(
            text=input_text,
            mode=parsed_args.mode,
            tone=parsed_args.tone,
            reading_level=parsed_args.level,
            preserve_markdown=not parsed_args.no_markdown,
        )
        print(result.text)
        return 0

    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
