"""The app's pages: the home ("Minhas aulas") and the lesson screens it opens.

Every UI string is in Portuguese.
"""

import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request

from manimflow.agent import Agent
from manimflow.app import lesson_page
from manimflow.lessons import EXAMPLE_NAME, LessonNameError, LessonSummary, Library

logger = logging.getLogger(__name__)

_LESSON_ROUTE = "/aula/"
_EXAMPLE_ROUTE = "/exemplo"
_EXAMPLE_FOLDER = r"C:\Users\Ana\Documents\Aulas Manim" if sys.platform == "win32" else "~/Documentos/Aulas Manim"


def app_root(agent: Agent, library: Library) -> Callable[[Request], Awaitable[None]]:
    """The root page, which shows the home or a lesson depending on the address.

    Not ui.sub_pages: the lesson screen has a header, which NiceGUI only allows at
    the top of a page.
    """
    example = library.example()

    async def page(request: Request) -> None:
        path = request.url.path
        if path == _EXAMPLE_ROUTE:
            await lesson_page(agent, example)()
            return
        if path.startswith(_LESSON_ROUTE):
            lesson = library.lesson(path.removeprefix(_LESSON_ROUTE))
            if lesson is not None:
                await lesson_page(agent, lesson)()
            else:
                _not_found("Esta aula não está na pasta das aulas.")
        elif path == "/":
            Home(library)
        else:
            _not_found("Esta página não existe.")

    return page


def lesson_url(name: str) -> str:
    return _LESSON_ROUTE + quote(name)


class Home:
    def __init__(self, library: Library) -> None:
        self.library = library
        ui.page_title("Minhas aulas · ManimFlow")
        new_lesson = NewLessonDialog(library)
        folder_dialog = FolderDialog(library, on_changed=self._show_lessons)
        profile_dialog = ProfileDialog(library)
        with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Minhas aulas").classes("text-3xl")
                with ui.row().classes("items-center gap-2"):
                    ui.button("Perfil do professor", icon="tune", on_click=profile_dialog.open).props("flat")
                    ui.button("+ Nova aula", on_click=new_lesson.open).props("size=lg")
            self.cards = ui.row().classes("w-full gap-4").mark("lessons")
            with ui.row().classes("items-center gap-2 text-grey-7"):
                self.folder = ui.label()
                ui.button("Mudar pasta", on_click=folder_dialog.open).props("flat dense")
            ui.separator()
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Exemplo · {EXAMPLE_NAME}").classes("text-grey-8")
                ui.button("Abrir o exemplo", on_click=lambda: ui.navigate.to(_EXAMPLE_ROUTE)).props("outline")
        self._show_lessons()

    def _show_lessons(self) -> None:
        self.folder.set_text(f"Pasta das aulas: {self.library.folder}")
        self.cards.clear()
        lessons = self.library.lessons()
        with self.cards:
            if not lessons:
                ui.label('Nenhuma aula nesta pasta ainda. Comece por "+ Nova aula".').classes("text-grey-7")
            for lesson in lessons:
                with ui.card().classes("w-64 relative hover:shadow-lg"):
                    # Stretched over the whole card, so clicking anywhere on it opens the lesson.
                    ui.link(lesson.name, lesson_url(lesson.name)).classes(
                        "text-lg font-medium text-inherit no-underline after:absolute after:inset-0"
                    )
                    ui.label(_details(lesson)).classes("text-grey-7 text-sm")


class NewLessonDialog:
    """Asks for the new lesson's name, creates it and opens it."""

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
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Criar", on_click=self._create)

    def open(self) -> None:
        self.name.value = ""
        self.error.set_visibility(False)
        self.dialog.open()

    def _create(self) -> None:
        try:
            lesson = self.library.create(self.name.value or "")
        except LessonNameError as problem:
            self._fail(str(problem))
            return
        except OSError:
            logger.exception("Creating a lesson failed")
            self._fail("Não foi possível criar a aula nesta pasta. Confira se ela existe e se você pode gravar nela.")
            return
        self.dialog.close()
        ui.navigate.to(lesson_url(lesson.name))

    def _fail(self, message: str) -> None:
        self.error.set_text(message)
        self.error.set_visibility(True)


class FolderDialog:
    """Moves the lessons to another folder, such as a synced one, from now on."""

    def __init__(self, library: Library, on_changed: Callable[[], None]) -> None:
        self.library = library
        self.on_changed = on_changed
        with ui.dialog() as self.dialog, ui.card().classes("w-[36rem] items-stretch"):
            ui.label("Pasta das aulas").classes("text-lg")
            ui.label(
                "As aulas que já estão na pasta atual ficam onde estão. Uma pasta que ainda não existe é criada."
            ).classes("text-grey-7")
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
            ).classes("text-grey-7")
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


def _not_found(message: str) -> None:
    ui.page_title("ManimFlow")
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
        ui.label(message).classes("text-lg")
        ui.link("Voltar para Minhas aulas", "/")


def _details(lesson: LessonSummary) -> str:
    details = [_edited(lesson.edited)]
    if lesson.states is not None:
        details.append(f"{lesson.states} estado" + ("" if lesson.states == 1 else "s"))
    return " · ".join(details)


def _edited(when: datetime) -> str:
    days = (datetime.now().date() - when.date()).days
    if days == 0:
        return f"editada hoje às {when:%H:%M}"
    if days == 1:
        return f"editada ontem às {when:%H:%M}"
    return f"editada em {when:%d/%m/%Y}"
