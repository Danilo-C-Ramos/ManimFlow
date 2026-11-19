"""The dialogs the sidebar and the pages share: new lesson, new turma, a turma's
instructions and color, the lessons folder and the teacher's profile.

Every UI string is in Portuguese.
"""

import logging
import sys
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from urllib.parse import quote

from nicegui import ui

from manimflow.export_tab import open_in_file_manager
from manimflow.lessons import TURMA_COLORS, LessonNameError, Library

logger = logging.getLogger(__name__)

LESSON_ROUTE = "/aula/"
TURMA_ROUTE = "/turma/"
EXAMPLE_ROUTE = "/exemplo"
_EXAMPLE_FOLDER = r"C:\Users\Ana\Documents\Aulas Manim" if sys.platform == "win32" else "~/Documentos/Aulas Manim"
_NO_TURMA = ""


_Dialog = TypeVar("_Dialog")
# One of each dialog per page, whichever part of the page opens it.
_shared: "weakref.WeakKeyDictionary[object, dict[type, object]]" = weakref.WeakKeyDictionary()


def shared(kind: Callable[[Library], _Dialog], library: Library) -> _Dialog:
    """The page's dialog of this kind, made the first time a part of the page asks for it."""
    dialogs = _shared.setdefault(ui.context.client, {})
    if kind not in dialogs:
        dialogs[kind] = kind(library)  # type: ignore[index]
    return dialogs[kind]  # type: ignore[index, return-value]


def lesson_url(id: str) -> str:
    """The address of the lesson with this id, `Aula` or `Turma/Aula`."""
    return LESSON_ROUTE + quote(id)


def turma_url(name: str) -> str:
    return TURMA_ROUTE + quote(name, safe="")


def open_folder(folder: Path) -> None:
    try:
        open_in_file_manager(folder)
    except Exception:
        logger.exception("Could not open %s", folder)
        ui.notify(f"Não foi possível abrir a pasta. Ela está em {folder}", type="negative")


class NewLessonDialog:
    """Asks for the new lesson's name and turma, creates it and opens it."""

    def __init__(self, library: Library) -> None:
        self.library = library
        with ui.dialog() as self.dialog, ui.card().classes("w-96 items-stretch"):
            ui.label("Nova aula").classes("text-lg")
            self.name = (
                ui.input("Nome da aula", placeholder="Aula 09 - Minkowski")
                .props("outlined dense autofocus")
                .mark("lesson-name-input")
            )
            self.name.on("keydown.enter", self._create)
            self.turma = ui.select({}, label="Turma").props("outlined dense").mark("lesson-turma")
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Criar", on_click=self._create)

    def open(self, turma: str | None = None) -> None:
        turmas = [turma.name for turma in self.library.turmas()]
        self.turma.set_options({_NO_TURMA: "Sem turma", **{name: name for name in turmas}})
        self.turma.value = turma if turma in turmas else _NO_TURMA
        self.turma.set_visibility(bool(turmas))
        self.name.value = ""
        self.error.set_visibility(False)
        self.dialog.open()

    def _create(self) -> None:
        turma = self.turma.value or None
        try:
            lesson = self.library.create(self.name.value or "", turma)
        except LessonNameError as problem:
            self._fail(str(problem))
            return
        except OSError:
            logger.exception("Creating a lesson failed")
            self._fail("Não foi possível criar a aula nesta pasta. Confira se ela existe e se você pode gravar nela.")
            return
        self.dialog.close()
        ui.navigate.to(lesson_url(self.library.lesson_id(lesson) or lesson.name))

    def _fail(self, message: str) -> None:
        self.error.set_text(message)
        self.error.set_visibility(True)


def color_picker(value: str, on_pick: Callable[[str], None]) -> ui.row:
    """The turma palette as a row of swatches; the picked one has a ring."""
    with ui.row().classes("gap-2").mark("turma-colors") as row:
        swatches: dict[str, ui.button] = {}

        def pick(color: str) -> None:
            for other, swatch in swatches.items():
                swatch.style(f"box-shadow:{'0 0 0 2px #fff, 0 0 0 4px ' + other if other == color else 'none'}")
            on_pick(color)

        for name, color in TURMA_COLORS.items():
            swatches[color] = (
                ui.button(on_click=lambda color=color: pick(color))
                .props("round unelevated size=sm")
                .style(f"background:{color} !important")
                .tooltip(name)
                .mark(f"cor-{name}")
            )
        pick(value)
    return row


class NewTurmaDialog:
    """Creates a turma with a name and a color, and opens its page."""

    def __init__(self, library: Library) -> None:
        self.library = library
        self.color = next(iter(TURMA_COLORS.values()))
        with ui.dialog() as self.dialog, ui.card().classes("w-[28rem] items-stretch gap-3"):
            ui.label("Nova turma").classes("text-lg")
            ui.label(
                "Uma turma junta as aulas de um curso e as instruções que valem para todas elas."
            ).classes("mf-muted")
            self.name = (
                ui.input("Nome da turma", placeholder="Relatividade Restrita")
                .props("outlined dense autofocus")
                .mark("turma-name-input")
            )
            self.name.on("keydown.enter", self._create)
            ui.label("Cor").classes("text-sm mf-muted")
            color_picker(self.color, self._pick)
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Criar turma", on_click=self._create)

    def _pick(self, color: str) -> None:
        self.color = color

    def open(self) -> None:
        self.name.value = ""
        self.error.set_visibility(False)
        self.dialog.open()

    def _create(self) -> None:
        try:
            turma = self.library.create_turma(self.name.value or "", self.color)
        except LessonNameError as problem:
            self._fail(str(problem))
            return
        except OSError:
            logger.exception("Creating a turma failed")
            self._fail("Não foi possível criar a turma nesta pasta. Confira se você pode gravar nela.")
            return
        self.dialog.close()
        ui.navigate.to(turma_url(turma.name))

    def _fail(self, message: str) -> None:
        self.error.set_text(message)
        self.error.set_visibility(True)


class TurmaColorDialog:
    """Changes a turma's color."""

    def __init__(self, library: Library, on_changed: Callable[[], None]) -> None:
        self.library = library
        self.on_changed = on_changed
        self.turma = ""
        with ui.dialog() as self.dialog, ui.card().classes("w-96 items-stretch gap-3"):
            self.title = ui.label().classes("text-lg")
            self.picker = ui.column()
            with ui.row().classes("justify-end"):
                ui.button("Fechar", on_click=self.dialog.close).props("flat")

    def open(self, turma: str) -> None:
        current = self.library.turma(turma)
        if current is None:
            return
        self.turma = turma
        self.title.set_text(f"Cor da turma {turma}")
        self.picker.clear()
        with self.picker:
            color_picker(current.color, self._pick)
        self.dialog.open()

    def _pick(self, color: str) -> None:
        current = self.library.turma(self.turma)
        if current is None or current.color == color:
            return
        try:
            self.library.set_turma_color(self.turma, color)
        except OSError:
            logger.exception("Changing a turma's color failed")
            ui.notify("Não foi possível mudar a cor.", type="negative")
            return
        self.on_changed()


class InstructionsDialog:
    """Shows and edits a turma's instructions, which the agent reads before every request."""

    def __init__(self, library: Library) -> None:
        self.library = library
        self.turma = ""
        with ui.dialog().props("full-width") as self.dialog, ui.card().classes("items-stretch"):
            self.title = ui.label().classes("text-lg")
            ui.label(
                "O que vale para todas as aulas desta turma: nível dos alunos, notação, livro-texto. "
                "O agente lê estas instruções depois do perfil do professor."
            ).classes("mf-muted")
            self.text = ui.textarea().props("outlined autogrow").classes("font-mono").mark("instructions-input")
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Salvar instruções", on_click=self._save)

    def open(self, turma: str) -> None:
        self.turma = turma
        self.title.set_text(f"Instruções da turma {turma}")
        self.error.set_visibility(False)
        try:
            self.text.value = self.library.turma_instructions(turma)
        except (OSError, UnicodeDecodeError):
            logger.exception("Reading a turma's instructions failed")
            ui.notify("Não foi possível abrir as instruções da turma.", type="negative")
            return
        self.dialog.open()

    def _save(self) -> None:
        try:
            self.library.save_turma_instructions(self.turma, self.text.value or "")
        except OSError:
            logger.exception("Saving a turma's instructions failed")
            self.error.set_text("Não foi possível salvar. Confira se você pode gravar na pasta da turma.")
            self.error.set_visibility(True)
            return
        self.dialog.close()
        ui.notify("Instruções salvas.", type="positive")


class FolderDialog:
    """Moves the lessons to another folder, such as a synced one, from now on."""

    def __init__(self, library: Library, on_changed: Callable[[], None]) -> None:
        self.library = library
        self.on_changed = on_changed
        with ui.dialog() as self.dialog, ui.card().classes("w-[36rem] items-stretch"):
            ui.label("Pasta das aulas").classes("text-lg")
            ui.label(
                "As aulas que já estão na pasta atual ficam onde estão. Uma pasta que ainda não existe é criada."
            ).classes("mf-muted")
            self.path = ui.input("Caminho da pasta").props("outlined dense").mark("folder-input")
            self.path.on("keydown.enter", self._save)
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Salvar pasta", on_click=self._save)

    def open(self) -> None:
        self.path.value = str(self.library.folder)
        self.error.set_visibility(False)
        self.dialog.open()

    def _save(self) -> None:
        folder = Path(self.path.value or "").expanduser()
        if not folder.is_absolute():
            self._fail(f"Use o caminho completo da pasta, como {_EXAMPLE_FOLDER}.")
            return
        try:
            self.library.set_folder(folder)
        except OSError:
            logger.exception("Changing the lessons folder failed")
            self._fail("Não foi possível usar essa pasta. Confira o caminho e se você pode gravar nela.")
            return
        self.dialog.close()
        self.on_changed()

    def _fail(self, message: str) -> None:
        self.error.set_text(message)
        self.error.set_visibility(True)


class ProfileDialog:
    """Shows and edits the teacher's profile, which every lesson in the folder follows."""

    def __init__(self, library: Library) -> None:
        self.library = library
        with ui.dialog().props("full-width") as self.dialog, ui.card().classes("items-stretch"):
            ui.label("Perfil do professor").classes("text-lg")
            ui.label(
                "Preferências que valem para todas as aulas: cores, fontes, vírgula decimal, fundo dos slides. "
                "O agente lê este perfil antes de cada pedido."
            ).classes("mf-muted")
            self.text = ui.textarea().props("outlined autogrow").classes("font-mono").mark("profile-input")
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Salvar perfil", on_click=self._save)

    def open(self) -> None:
        self.error.set_visibility(False)
        try:
            self.text.value = self.library.profile()
        except (OSError, UnicodeDecodeError):
            logger.exception("Reading the profile failed")
            ui.notify("Não foi possível abrir o perfil.", type="negative")
            return
        self.dialog.open()

    def _save(self) -> None:
        try:
            self.library.save_profile(self.text.value or "")
        except OSError:
            logger.exception("Saving the profile failed")
            self.error.set_text("Não foi possível salvar o perfil. Confira se você pode gravar na pasta das aulas.")
            self.error.set_visibility(True)
            return
        self.dialog.close()
        ui.notify("Perfil salvo.", type="positive")
