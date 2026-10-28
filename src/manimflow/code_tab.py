"""The lesson's code tab: the physics and scenes files in an editor the teacher can change.

"Renderizar" saves the teacher's edits, commits them as a manual edit and
previews every scene of the plan through the `manimflow` CLI. The preview panel
picks the new renders up on its own.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

from nicegui import run, ui
from nicegui.events import ValueChangeEventArguments

from manimflow.plan import load_plan
from manimflow.render import SCENES_FILE
from manimflow.versioning import History

logger = logging.getLogger(__name__)

PHYSICS_FILE = "fisica.py"
FILES = (PHYSICS_FILE, SCENES_FILE)
# Seconds between looks at the lesson's files, for changes the agent or another editor made.
REFRESH_INTERVAL = 0.5


class CodeTab:
    def __init__(self, lesson: Path, history: History) -> None:
        self.lesson = lesson
        self.history = history
        # Each file as it was last read from or written to the lesson, and as the teacher has it now.
        self.saved = {name: _read(lesson / name) for name in FILES}
        self.drafts = dict(self.saved)
        self.current = PHYSICS_FILE
        # Files changed outside the editor while the teacher had unsaved edits in them,
        # with their new content, until the teacher picks a version.
        self.conflicts: dict[str, str] = {}
        self.rendering = False
        self.agent_working = False
        # Shown above the render's progress until the next "Renderizar".
        self.notice: str | None = None
        with ui.column().classes("w-full gap-2"):
            self.warnings = ui.column().classes("w-full gap-2")
            # File names keep their case.
            with ui.tabs().props("dense align=left no-caps") as files:
                for name in FILES:
                    ui.tab(name)
            self.editor = (
                ui.codemirror(self.drafts[self.current], language="Python")
                .classes("w-full h-[calc(100vh-17rem)]")
                .mark("code")
            )
            files.value = self.current
            files.on_value_change(self._switch)
            with ui.row().classes("items-center gap-2"):
                self.button = ui.button("Renderizar", on_click=self.render)
                self.spinner = ui.spinner(size="sm")
                self.spinner.set_visibility(False)
            self.status = ui.column().classes("w-full gap-1").mark("render-status")
        ui.timer(REFRESH_INTERVAL, self._reload)

    def _switch(self, event: ValueChangeEventArguments) -> None:
        self.drafts[self.current] = self.editor.value
        # The tab's name.
        self.current = str(event.value)
        self.editor.value = self.drafts[self.current]

    def _reload(self) -> None:
        """Loads the files someone else changed, unless the teacher has unsaved edits in them."""
        self.drafts[self.current] = self.editor.value
        for name in FILES:
            on_disk = _read(self.lesson / name)
            if on_disk == self.saved[name]:
                continue
            if self.drafts[name] == self.saved[name]:
                self._load(name, on_disk)
            elif self.conflicts.get(name) != on_disk:
                self.conflicts[name] = on_disk
                self._draw_conflicts()

    def _load(self, name: str, content: str) -> None:
        self.saved[name] = self.drafts[name] = content
        if name == self.current:
            self.editor.value = content

    def _resolve(self, name: str, keep_mine: bool) -> None:
        on_disk = self.conflicts.pop(name)
        if keep_mine:
            # So "Renderizar" writes the teacher's version over the new one.
            self.saved[name] = on_disk
        else:
            self._load(name, on_disk)
        self._draw_conflicts()

    def _draw_conflicts(self) -> None:
        self.warnings.clear()
        with self.warnings:
            for name in self.conflicts:
                with ui.card().classes("w-full bg-amber-1"):
                    ui.label(f"{name} foi alterado fora do editor enquanto você o editava.")
                    with ui.row():
                        ui.button("Manter as minhas edições", on_click=lambda name=name: self._resolve(name, True))
                        ui.button(
                            "Carregar a versão nova", on_click=lambda name=name: self._resolve(name, False)
                        ).props("outline")
        self._update_button()

    def set_agent_working(self, working: bool) -> None:
        self.agent_working = working
        self._update_button()

    def _update_button(self) -> None:
        # During a turn, the commit would take the agent's half-done changes for the
        # teacher's, and the teacher's edit would miss the next diff. With a conflict,
        # saving would overwrite one of the versions before the teacher picked it.
        self.button.set_enabled(not (self.rendering or self.agent_working or self.conflicts))

    async def render(self) -> None:
        # A change the editor hasn't looked at yet would be saved over without a warning.
        self._reload()
        if not self.button.enabled:
            return
        self.rendering = True
        self._update_button()
        self.spinner.set_visibility(True)
        self.notice = None
        try:
            if self._save():
                await self._preview()
        except Exception:
            logger.exception("Preview from the code tab failed")
            self._show("Não foi possível renderizar a prévia agora. Tente de novo.")
        finally:
            self.rendering = False
            self._update_button()
            self.spinner.set_visibility(False)

    def _save(self) -> bool:
        """Writes and commits the teacher's edits, returning whether the files were written."""
        edited = [name for name in FILES if self.drafts[name] != self.saved[name]]
        for name in edited:
            try:
                (self.lesson / name).write_text(self.drafts[name], encoding="utf-8")
            except OSError as error:
                logger.exception("Saving %s failed", name)
                self._show(f"Não foi possível salvar {name}:", [str(error)])
                return False
            self.saved[name] = self.drafts[name]
        if edited:
            try:
                self.history.commit_manual_edit(f"Edição manual em {' e '.join(edited)}")
            except Exception:
                # The files are saved; the next commit picks them up.
                logger.exception("Commit failed")
                self.notice = "Não foi possível salvar uma versão desta mudança."
        return True

    async def _preview(self) -> None:
        plan, errors = load_plan(self.lesson)
        if plan is None:
            self._show("O plano tem problemas, então não dá para saber o que renderizar:", errors)
            return
        in_order = [state.scene for state in plan.states] + [step.scene for step in plan.transitions]
        scenes = list(dict.fromkeys(in_order))
        for number, scene in enumerate(scenes, start=1):
            self._show(f"Renderizando a cena {scene} ({number} de {len(scenes)})…")
            if problem := await run.io_bound(_preview_scene, self.lesson, scene):
                self._show(f"A cena {scene} não renderizou:", [problem])
                return
        self._show("Prévia atualizada.")

    def _show(self, text: str, details: list[str] | tuple[str, ...] = ()) -> None:
        self.status.clear()
        with self.status:
            if self.notice:
                ui.label(self.notice).classes("text-negative")
            ui.label(text).classes("text-negative" if details else "text-grey-7")
            for detail in details:
                ui.label(detail).classes("text-negative text-sm font-mono whitespace-pre-wrap")


def _preview_scene(lesson: Path, scene: str) -> str | None:
    """Previews `scene` through the `manimflow` CLI, returning what went wrong, or None."""
    done = subprocess.run(
        [sys.executable, "-m", "manimflow.cli", "preview", str(lesson), scene, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        report = json.loads(done.stdout)
    except json.JSONDecodeError:
        logger.error("manimflow preview printed no report: %s", done.stderr)
        return done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "erro desconhecido"
    if report["ok"]:
        return None
    # The last line of Manim's output is the Python error, such as "NameError: name 'g' is not defined".
    output = report["manim_output"].strip().splitlines()
    return output[-1] if output else "; ".join(report["errors"])


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
