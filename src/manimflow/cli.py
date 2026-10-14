"""The `manimflow` command line: the single path from ManimFlow to Manim."""

import argparse
import io
import json
import sys
from pathlib import Path

from manimflow.render import render_scene


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manimflow")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("preview", "render a scene at low quality"),
        ("render", "render a scene at final quality"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("lesson", type=Path, help="lesson folder")
        command.add_argument("scene", help="scene class name in cenas.py")
        command.add_argument("--json", action="store_true", help="print a JSON report")

    args = parser.parse_args(argv)
    # The agent and the UI read this output through pipes; lesson paths are
    # often accented ("Aula 09 - Óptica"), so don't depend on the code page.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    report = render_scene(args.lesson, args.scene, args.command)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for path in report.files:
            print(path)
        if report.manim_output:
            print(report.manim_output, file=sys.stderr)
        for error in report.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
