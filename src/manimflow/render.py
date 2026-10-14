"""Renders one lesson scene into the lesson's output folder."""

import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

SCENES_FILE = "cenas.py"
OUTPUT_DIR = "saida"
CACHE_DIR = ".manimflow"

QUALITIES = {
    "preview": ("low_quality", Path(OUTPUT_DIR) / "previa"),
    "render": ("high_quality", Path(OUTPUT_DIR)),
}


# Scene names end up in file paths and in the worker's command line, so only
# plain ASCII identifiers get through.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{device}{n}" for device in ("com", "lpt") for n in range(1, 10)
}


def scene_name_error(name: str) -> str | None:
    """Explains why `name` can't be used as a scene name, or None if it can."""
    if not _IDENTIFIER.fullmatch(name) or keyword.iskeyword(name):
        return f"Invalid scene name {name!r}: use a plain Python identifier such as S0 or T01"
    if name.lower() in _WINDOWS_RESERVED:
        return f"Invalid scene name {name!r}: it is a reserved file name on Windows"
    return None


@dataclass
class RenderReport:
    command: str
    scene: str
    files: list[Path] = field(default_factory=list)
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    manim_output: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": self.command,
            "scene": self.scene,
            "files": [str(path) for path in self.files],
            "duration_s": round(self.duration_s, 3),
            "errors": self.errors,
            "manim_output": self.manim_output,
        }


def render_scene(lesson: Path, scene: str, mode: str) -> RenderReport:
    """Renders `scene` from the lesson's scenes file; `mode` is "preview" or "render"."""
    started = time.perf_counter()
    report = RenderReport(command=mode, scene=scene)
    _render_into(report, lesson.absolute(), scene, mode)
    report.duration_s = time.perf_counter() - started
    return report


def _render_into(report: RenderReport, lesson: Path, scene: str, mode: str) -> None:
    if error := scene_name_error(scene):
        report.errors.append(error)
        return
    if not (lesson / SCENES_FILE).is_file():
        report.errors.append(f"No {SCENES_FILE} found in lesson folder {lesson}")
        return

    quality, output_dir = QUALITIES[mode]
    cache_dir = lesson / CACHE_DIR
    cache_dir.mkdir(exist_ok=True)

    # Everything is written inside the lesson folder, the only place the
    # agent's sandbox lets it write.
    with tempfile.TemporaryDirectory(dir=cache_dir) as staging:
        worker = subprocess.run(
            [
                sys.executable,
                "-m",
                "manimflow._worker",
                str(lesson / SCENES_FILE),
                scene,
                quality,
                str(cache_dir / "media"),
                staging,
            ],
            cwd=lesson,
            # Manim logs its errors (LaTeX failures among them) to stdout and
            # Python writes the traceback to stderr; the report needs both.
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                # Keep __pycache__ out of the teacher's lesson folder.
                "PYTHONDONTWRITEBYTECODE": "1",
                # Windows would otherwise write tracebacks in the ANSI code page.
                "PYTHONUTF8": "1",
            },
        )
        if worker.returncode != 0:
            report.manim_output = worker.stdout
            last_line = worker.stdout.strip().splitlines()[-1:] or ["no error output"]
            report.errors.append(f"Scene {scene} failed: {last_line[0]}")
            return

        for kind in ("png", "mp4"):
            produced = Path(staging) / f"{scene}.{kind}"
            target = lesson / output_dir / kind / produced.name
            if produced.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(produced, target)
                report.files.append(target)
            else:
                # A scene that no longer animates must not keep an old video.
                target.unlink(missing_ok=True)
