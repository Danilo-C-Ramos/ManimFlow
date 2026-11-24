"""The lesson's export dialog: pick a preset, adjust its settings and run `manimflow export`,
with the lesson's previous exports listed to open or redo."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nicegui import ui
from PIL import ImageColor

from manimflow import activity
from manimflow.cli import MAX_FPS, MAX_RESOLUTION
from manimflow.export import PRESETS
from manimflow.render import OUTPUT_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Name:
    title: str
    description: str


# The presets of docs/export.md, as the teacher sees them.
_NAMES = {
    "powerpoint": _Name("PowerPoint", "Uma imagem PNG por estado e um vídeo MP4 por transição."),
    "web": _Name("PowerPoint web / Google Slides", "Um GIF por transição e um GIF parado por estado."),
    "beamer": _Name("Beamer / PDF", "Uma imagem PNG por estado."),
    "video": _Name("Vídeo da aula inteira", "Todas as transições em um único vídeo MP4."),
}
ASPECT_RATIOS = ["16:9", "16:10", "4:3", "1:1"]


class ExportDialog:
    """The export panel in a dialog, with the lesson's previous exports above it."""

    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        with ui.dialog() as self.dialog, ui.card().classes("w-[52rem] max-w-full items-stretch gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Exportar a aula").classes("text-lg font-semibold")
                ui.button(icon="close", on_click=self.dialog.close).props("flat round dense")
            self.previous = ui.column().classes("w-full gap-1").mark("previous-exports")
            self.panel = ExportPanel(lesson, on_done=self._show_previous)
        self._show_previous()

    def open(self, preset: str | None = None) -> None:
        if preset is not None:
            self.panel.preset.value = preset
        self._show_previous()
        self.dialog.open()

    def _show_previous(self) -> None:
        self.previous.clear()
        exports = previous_exports(self.lesson)
        if not exports:
            return
        with self.previous:
            ui.label("Exportações anteriores").classes("text-sm font-medium")
            for preset, folder, count, when in exports:
                with ui.row().classes("w-full items-center no-wrap gap-3 mf-card px-3 py-2").mark("previous-export"):
                    ui.label(_NAMES[preset].title).classes("font-medium")
                    ui.label(f"{count} arquivo" + ("" if count == 1 else "s") + f" · {when:%d/%m às %H:%M}").classes(
                        "text-[13px] mf-muted grow"
                    )
                    ui.button("Abrir pasta", on_click=lambda folder=folder: _open(self.lesson, folder)).props(
                        "flat dense no-caps"
                    )
                    ui.button("Exportar de novo", on_click=lambda preset=preset: self._again(preset)).props(
                        "flat dense no-caps"
                    )

    async def _again(self, preset: str) -> None:
        self.panel.preset.value = preset
        await self.panel.run()


def previous_exports(lesson: Path) -> list[tuple[str, Path, int, datetime]]:
    """Each preset the lesson was exported with: its folder, number of files and last export."""
    found = []
    for preset in PRESETS:
        folder = lesson / OUTPUT_DIR / preset
        try:
            files = [path for path in folder.iterdir() if path.is_file()]
        except OSError:
            continue
        if files:
            when = datetime.fromtimestamp(max(path.stat().st_mtime for path in files))
            found.append((preset, folder, len(files), when))
    return sorted(found, key=lambda export: export[3], reverse=True)


def _open(lesson: Path, folder: Path) -> None:
    activity.seen_export(lesson)
    try:
        open_in_file_manager(folder)
    except Exception:
        logger.exception("Could not open %s", folder)
        ui.notify(f"Não foi possível abrir a pasta. Os arquivos estão em {folder}", type="negative")


class ExportPanel:
    def __init__(self, lesson: Path, on_done: Callable[[], None] = lambda: None) -> None:
        self.lesson = lesson
        self.on_done = on_done
        with ui.column().classes("w-full gap-3").mark("export"):
            self.preset = ui.radio(
                {name: _NAMES[name].title for name in PRESETS}, value="powerpoint", on_change=self._use_defaults
            ).mark("export-preset")
            self.description = ui.label().classes("text-grey-7")
            with ui.row().classes("w-full gap-4"):
                self.resolution = ui.number(
                    "Resolução (altura em pixels)", precision=0, on_change=self._check
                ).mark("resolution")
                self.fps = ui.number("Quadros por segundo", precision=0, on_change=self._check).mark("fps")
                self.aspect_ratio = ui.select(ASPECT_RATIOS, label="Proporção").mark("aspect-ratio")
                self.background = ui.color_input(
                    "Cor de fundo", value="", placeholder="O fundo da própria aula", on_change=self._check
                ).mark("background")
            self.problems = ui.column().classes("gap-0")
            self.button = ui.button("Exportar", icon="file_download", on_click=self.run).mark("run-export")
            with ui.row().classes("items-center gap-2 text-grey-7") as self.working:
                ui.spinner(size="sm")
                self.progress = ui.label()
            self.working.set_visibility(False)
            self.result = ui.column().classes("w-full gap-1").mark("export-result")
        # The CLI's last word on its progress, from the thread that reads it.
        self.step: dict | None = None
        self._use_defaults()

    async def run(self) -> None:
        if not self.button.enabled:
            return
        # The settings are locked while the export runs.
        folder = self.lesson / OUTPUT_DIR / self.preset.value
        self._set_busy(True)
        self.result.clear()
        self.step = None
        started = time.monotonic()
        ticker = ui.timer(1, lambda: self._show_progress(time.monotonic() - started))
        self._show_progress(0)
        activity.start(self.lesson)
        try:
            report = await self._export()
        finally:
            activity.stop(self.lesson)
            ticker.cancel()
            self._set_busy(False)
        with self.result:
            if report.get("ok"):
                activity.exported(self.lesson, self.preset.value, folder)
                _show_files(report["files"], self.lesson, folder)
            else:
                _show_failure(report)
        self.on_done()

    async def _export(self) -> dict:
        """Runs the CLI and returns its JSON report, or a report of why there is none."""
        try:
            # In a thread: NiceGUI's event loop may not run subprocesses on Windows.
            return await asyncio.to_thread(self._run_cli)
        except Exception as error:
            logger.exception("Could not start the export")
            return {"ok": False, "errors": [str(error)]}

    def _run_cli(self) -> dict:
        """Runs the CLI, keeping its progress lines in `step` as they come."""
        with subprocess.Popen(
            self._command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as process:
            assert process.stdout is not None and process.stderr is not None
            stdout = process.stdout
            report: list[str] = []
            # Read apart, so a long report never blocks the CLI while stderr is read.
            reader = threading.Thread(target=lambda: report.append(stdout.read()))
            reader.start()
            other = []
            for line in process.stderr:
                try:
                    self.step = json.loads(line)["progress"]
                except (ValueError, KeyError, TypeError):
                    other.append(line)
            reader.join()
        try:
            return json.loads(report[0])
        except ValueError:
            # The CLI stopped before writing its report, so its own words are on stderr.
            logger.error("Export ended without a report: %s", "".join(other))
            return {"ok": False, "errors": "".join(other).strip().splitlines()[-1:]}

    def _command(self) -> list[str]:
        command = [sys.executable, "-m", "manimflow.cli", "export", str(self.lesson), self.preset.value]
        command += ["--resolution", str(int(self.resolution.value)), "--fps", str(int(self.fps.value))]
        command += ["--aspect-ratio", self.aspect_ratio.value]
        if self.background.value:
            command += ["--background", self.background.value]
        return [*command, "--json"]

    def _show_progress(self, elapsed: float) -> None:
        step = self.step
        if step is None:
            doing = "Exportando…"
        elif step["scene"] is None:
            doing = "Gravando os arquivos…"
        else:
            doing = f"Renderizando a cena {step['scene']} ({step['number']} de {step['of']})…"
        self.progress.set_text(f"{doing} {int(elapsed)} s. Pode levar alguns minutos.")

    def _set_busy(self, busy: bool) -> None:
        for control in (self.preset, self.resolution, self.fps, self.aspect_ratio, self.background):
            control.set_enabled(not busy)
        self.working.set_visibility(busy)
        self._check()

    def _check(self) -> None:
        """Explains the settings the CLI would refuse, and only lets a valid export run."""
        problems = _problems(
            PRESETS[self.preset.value].max_fps, self.resolution.value, self.fps.value, self.background.value
        )
        self.problems.clear()
        with self.problems:
            for problem in problems:
                ui.label(problem).classes("text-negative text-sm")
        self.button.set_enabled(not problems and not self.working.visible)

    def _use_defaults(self) -> None:
        preset = PRESETS[self.preset.value]
        self.description.set_text(_NAMES[preset.name].description)
        self.resolution.value = preset.resolution
        self.fps.value = preset.fps
        self.aspect_ratio.value = "{}:{}".format(*preset.aspect_ratio)
        self.background.value = ""
        self._check()


def _problems(max_fps: int | None, resolution: float | None, fps: float | None, background: str | None) -> list[str]:
    problems = []
    if resolution is None or not (16 <= resolution <= MAX_RESOLUTION and resolution % 2 == 0):
        problems.append(f"A resolução precisa ser um número par de 16 a {MAX_RESOLUTION}.")
    if fps is None or not 1 <= fps <= MAX_FPS:
        problems.append(f"Os quadros por segundo precisam ir de 1 a {MAX_FPS}.")
    elif max_fps and fps > max_fps:
        problems.append(f"Os GIFs tocam no máximo {max_fps} quadros por segundo.")
    if background:
        try:
            ImageColor.getrgb(background)
        except ValueError:
            problems.append("Use uma cor como #ffffff ou white, ou deixe vazio.")
    return problems


def _show_files(files: list[str], lesson: Path, folder: Path) -> None:
    ui.label("Arquivos exportados").classes("text-positive")
    with ui.column().classes("gap-0").mark("exported-files"):
        for file in files:
            ui.label(Path(file).name).classes("font-mono")
    ui.button("Abrir pasta", icon="folder_open", on_click=lambda: _open(lesson, folder)).props("outline").mark(
        "open-exported-folder"
    )


def open_in_file_manager(folder: Path) -> None:
    """Shows the folder in the system's file manager, ready to drag files into the slides."""
    if sys.platform == "win32":
        os.startfile(folder)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def _show_failure(report: dict) -> None:
    """What went wrong: the CLI's own messages are in Portuguese for problems in the plan
    and the scenes. For a scene that fails to render they are in English, meant for the
    agent, so they wait in the details."""
    ui.label("A exportação falhou, e nenhum arquivo foi alterado.").classes("text-negative")
    failed = report.get("failed_scenes") or []
    for scene in failed:
        ui.label(f"A cena {scene} deu erro ao renderizar.").classes("text-negative text-sm")
    if failed:
        ui.label("Peça ao agente para corrigir.")
        with ui.expansion("Detalhes para o agente").classes("w-full"):
            for error in report.get("errors", []):
                ui.label(error).classes("font-mono text-xs")
            ui.label(report.get("manim_output", "")).classes("font-mono text-xs whitespace-pre-wrap")
        return
    for error in report.get("errors", []):
        ui.label(error).classes("text-negative text-sm")
