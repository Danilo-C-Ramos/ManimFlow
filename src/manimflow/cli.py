"""The `manimflow` command line: the single path from ManimFlow to Manim."""

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Protocol

from manimflow.plan import validate_plan
from manimflow.render import render_scene


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manimflow", description="Without a command, opens the ManimFlow app in the browser."
    )
    parser.add_argument("--demo", action="store_true", help="answer with the scripted demo agent")
    commands = parser.add_subparsers(dest="command")
    for name, help_text in [
        ("preview", "render a scene at low quality"),
        ("render", "render a scene at final quality"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("lesson", type=Path, help="lesson folder")
        command.add_argument("scene", help="scene class name in cenas.py")
        command.add_argument("--json", action="store_true", help="print a JSON report")

    plan = commands.add_parser("plan", help="work with a lesson's plano.yaml")
    plan_commands = plan.add_subparsers(dest="plan_command", required=True)
    validate = plan_commands.add_parser("validate", help="check a lesson's plano.yaml")
    validate.add_argument("lesson", type=Path, help="lesson folder")
    validate.add_argument("--json", action="store_true", help="print a JSON report")

    args = parser.parse_args(argv)
    # The agent and the UI read this output through pipes; lesson paths are
    # often accented ("Aula 09 - Óptica"), so don't depend on the code page.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    if args.command is None:
        return _serve(args.demo)
    if args.command == "plan":
        return _plan_validate(args.lesson, args.json)
    return _render(args.lesson, args.scene, args.command, args.json)


class _Report(Protocol):
    errors: list[str]

    @property
    def ok(self) -> bool: ...

    def to_dict(self) -> dict: ...


def _render(lesson: Path, scene: str, mode: str, as_json: bool) -> int:
    report = render_scene(lesson, scene, mode)
    details = [report.manim_output] if report.manim_output else []
    return _finish(report, as_json, [str(path) for path in report.files], details)


def _serve(demo: bool) -> int:
    # NiceGUI is slow to import, and the other commands run inside the agent's loop.
    from manimflow.app import example_copy, serve
    from manimflow.fake_agent import DEMO, ScriptedAgent

    if not demo:
        print("O agente Codex ainda não está disponível. Usando o agente de demonstração.")
    serve(ScriptedAgent(DEMO, delay=0.6), example_copy())
    return 0


def _plan_validate(lesson: Path, as_json: bool) -> int:
    report = validate_plan(lesson)
    return _finish(report, as_json, ["Plano válido."] if report.ok else [], [])


def _finish(report: _Report, as_json: bool, lines: list[str], details: list[str]) -> int:
    """Prints the report, as JSON or as text lines with details and errors on stderr."""
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        for line in lines:
            print(line)
        for detail in details:
            print(detail, file=sys.stderr)
        for error in report.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
