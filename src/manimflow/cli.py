"""The `manimflow` command line: the single path from ManimFlow to Manim."""

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Protocol

from PIL import ImageColor

from manimflow.continuity import (
    CHANNEL_DIFF,
    MAX_FRACTION,
    Pair,
    check_continuity,
    extract_frames,
)
from manimflow.export import PRESETS, export_lesson
from manimflow.plan import validate_plan
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

    frames = commands.add_parser(
        "frames", help="save the first, middle and last frame of transitions, and state images"
    )
    _add_frame_arguments(frames)

    continuity = commands.add_parser(
        "check-continuity", help="check that transitions start and end on their states' images"
    )
    _add_frame_arguments(continuity)
    continuity.add_argument(
        "--channel-diff",
        type=_channel_diff,
        default=CHANNEL_DIFF,
        help=f"a pixel differs when any channel differs by more than this (default: {CHANNEL_DIFF})",
    )
    continuity.add_argument(
        "--max-fraction",
        type=_fraction,
        default=MAX_FRACTION,
        help=f"images match when under this fraction of pixels differ (default: {MAX_FRACTION})",
    )

    export = commands.add_parser(
        "export",
        help="render the lesson at final quality into slide-ready files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="presets:\n"
        + "\n".join(
            f"  {p.name:<12} {p.help} ({p.resolution}p, {p.fps} fps)" for p in PRESETS.values()
        ),
    )
    export.add_argument("lesson", type=Path, help="lesson folder")
    export.add_argument("preset", choices=PRESETS, help="what the files are for")
    export.add_argument(
        "--resolution", type=_resolution, help="height in pixels, such as 720 or 1080"
    )
    export.add_argument("--fps", type=_fps, help="frames per second")
    export.add_argument(
        "--aspect-ratio", type=_aspect_ratio, help="width:height, such as 16:9 or 4:3"
    )
    export.add_argument(
        "--background",
        type=_color,
        help="background color, such as #ffffff or white (default: the lesson's own)",
    )
    export.add_argument("--json", action="store_true", help="print a JSON report")

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
    if args.command == "plan":
        return _plan_validate(args.lesson, args.json)
    if args.command == "export":
        return _export(
            args.lesson, args.preset, args.resolution, args.fps, args.aspect_ratio, args.background, args.json
        )
    if args.command == "frames":
        return _frames(args.lesson, args.transitions, args.final, args.json)
    if args.command == "check-continuity":
        return _check_continuity(
            args.lesson, args.transitions, args.final, args.channel_diff, args.max_fraction, args.json
        )
    return _render(args.lesson, args.scene, args.command, args.json)


def _add_frame_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("lesson", type=Path, help="lesson folder")
    command.add_argument(
        "transitions", nargs="*", metavar="transition", help="transitions such as S0-S1 (default: all)"
    )
    command.add_argument(
        "--final", action="store_true", help="read the final render instead of the preview"
    )
    command.add_argument("--json", action="store_true", help="print a JSON report")


def _channel_diff(text: str) -> int:
    value = int(text)
    if not 0 <= value < 255:
        raise argparse.ArgumentTypeError("must be from 0 to 254")
    return value


def _fraction(text: str) -> float:
    value = float(text)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError("must be above 0 and at most 1")
    return value


def _resolution(text: str) -> int:
    value = int(text)
    if not (16 <= value <= 2160 and value % 2 == 0):
        raise argparse.ArgumentTypeError("must be an even number of pixels from 16 to 2160")
    return value


def _fps(text: str) -> int:
    value = int(text)
    if not 1 <= value <= 120:
        raise argparse.ArgumentTypeError("must be from 1 to 120")
    return value


def _aspect_ratio(text: str) -> tuple[int, int]:
    across, _, down = text.partition(":")
    valid = across.isdigit() and down.isdigit() and int(down) > 0
    if not (valid and 1 / 4 <= int(across) / int(down) <= 4):
        raise argparse.ArgumentTypeError("must be width:height, such as 16:9, from 1:4 to 4:1")
    return int(across), int(down)


def _color(text: str) -> str:
    try:
        red, green, blue = ImageColor.getrgb(text)[:3]
    except ValueError:
        raise argparse.ArgumentTypeError("must be a color such as #ffffff or white") from None
    return f"#{red:02x}{green:02x}{blue:02x}"


class _Report(Protocol):
    errors: list[str]

    @property
    def ok(self) -> bool: ...

    def to_dict(self) -> dict: ...


def _render(lesson: Path, scene: str, mode: str, as_json: bool) -> int:
    report = render_scene(lesson, scene, mode)
    details = [report.manim_output] if report.manim_output else []
    return _finish(report, as_json, [str(path) for path in report.files], details)


def _export(
    lesson: Path,
    preset: str,
    resolution: int | None,
    fps: int | None,
    aspect_ratio: tuple[int, int] | None,
    background: str | None,
    as_json: bool,
) -> int:
    report = export_lesson(lesson, preset, resolution, fps, aspect_ratio, background)
    details = [report.manim_output] if report.manim_output else []
    return _finish(report, as_json, [str(path) for path in report.files], details)


def _frames(lesson: Path, transitions: list[str], final: bool, as_json: bool) -> int:
    report = extract_frames(lesson, transitions, final)
    return _finish(report, as_json, [str(path) for path in report.files], [])


def _check_continuity(
    lesson: Path,
    transitions: list[str],
    final: bool,
    channel_diff: int,
    max_fraction: float,
    as_json: bool,
) -> int:
    report = check_continuity(lesson, transitions, final, channel_diff, max_fraction)
    return _finish(report, as_json, [_pair_line(pair) for pair in report.pairs], [])


def _pair_line(pair: Pair) -> str:
    sign = "=" if pair.ok else "≠"
    return (
        f"{'ok' if pair.ok else 'FAIL'}  {pair.transition} {pair.position} {sign} {pair.state} "
        f"({pair.fraction:.3%})"
    )


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
