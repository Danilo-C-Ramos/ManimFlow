"""The lesson's export tab: pick a preset, adjust its settings and run `manimflow export`."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui
from PIL import ImageColor

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


class ExportPanel:
    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        with ui.column().classes("w-full gap-3").mark("export"):
            ui.label("Exportar").classes("text-lg")
            self.preset = ui.radio(
                {name: _NAMES[name].title for name in PRESETS}, value="powerpoint", on_change=self._use_defaults
            ).mark("preset")
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
            self.result = ui.column().classes("w-full gap-1")
        self._use_defaults()

    async def run(self) -> None:
        if not self.button.enabled:
            return
        # The settings are locked while the export runs.
        folder = self.lesson / OUTPUT_DIR / self.preset.value
        self._set_busy(True)
        self.result.clear()
        started = time.monotonic()
        ticker = ui.timer(1, lambda: self._show_progress(time.monotonic() - started))
        self._show_progress(0)
        try:
            report = await self._export()
        finally:
            ticker.cancel()
            self._set_busy(False)
        with self.result:
            if report.get("ok"):
                _show_files(report["files"], folder)
            else:
                _show_failure(report)

    async def _export(self) -> dict:
        """Runs the CLI and returns its JSON report, or a report of why there is none."""
        try:
            # In a thread: NiceGUI's event loop may not run subprocesses on Windows.
            finished = await asyncio.to_thread(
                subprocess.run,
                self._command(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as error:
            logger.exception("Could not start the export")
            return {"ok": False, "errors": [str(error)]}
        try:
            return json.loads(finished.stdout)
        except ValueError:
            # The CLI stopped before writing its report, so its own words are on stderr.
            logger.error("Export ended without a report: %s", finished.stderr)
            return {"ok": False, "errors": finished.stderr.strip().splitlines()[-1:]}

    def _command(self) -> list[str]:
        command = [sys.executable, "-m", "manimflow.cli", "export", str(self.lesson), self.preset.value]
        command += ["--resolution", str(int(self.resolution.value)), "--fps", str(int(self.fps.value))]
        command += ["--aspect-ratio", self.aspect_ratio.value]
        if self.background.value:
            command += ["--background", self.background.value]
        return [*command, "--json"]

    def _show_progress(self, elapsed: float) -> None:
        self.progress.set_text(f"Exportando… {int(elapsed)} s. Pode levar alguns minutos.")

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


def _show_files(files: list[str], folder: Path) -> None:
    ui.label("Arquivos exportados").classes("text-positive")
    with ui.column().classes("gap-0").mark("exported-files"):
        for file in files:
            ui.label(Path(file).name).classes("font-mono")

    def open_folder() -> None:
        try:
            open_in_file_manager(folder)
        except Exception:
            logger.exception("Could not open %s", folder)
            ui.notify(f"Não foi possível abrir a pasta. Os arquivos estão em {folder}", type="negative")

    ui.button("Abrir pasta", icon="folder_open", on_click=open_folder).props("outline")


def open_in_file_manager(folder: Path) -> None:
    """Shows the folder in the system's file manager, ready to drag files into the slides."""
    if sys.platform == "win32":
        os.startfile(folder)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def _show_failure(report: dict) -> None:
    """What went wrong: the CLI's own messages are in Portuguese for the plan, and in
    English, meant for the agent, for everything else."""
    ui.label("A exportação falhou, e nenhum arquivo foi alterado.").classes("text-negative")
    if report.get("manim_output"):
        ui.label("Uma cena deu erro ao renderizar. Peça ao agente para corrigir.")
    for error in report.get("errors", []):
        ui.label(error).classes("text-negative text-sm")
    if report.get("manim_output"):
        with ui.expansion("Saída do Manim").classes("w-full"):
            ui.label(report["manim_output"]).classes("font-mono text-xs whitespace-pre-wrap")
