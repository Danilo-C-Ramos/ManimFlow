"""The sidebar on every page: a map of the teacher's work, not a chat history.

"Precisa de você" lists what waits for the teacher (a plan to approve, the agent at
work, an export to open). Below it, the turmas as a tree with a status dot on each
lesson, the lessons without a turma, and the example. Quick actions show on hover.
The sidebar looks at the lessons folder every few seconds, so it follows what the
agent does in any tab. Every UI string is in Portuguese.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui

from manimflow import activity
from manimflow.agent import Agent, QuotaWindow
from manimflow.dialogs import (
    EXAMPLE_ROUTE,
    InstructionsDialog,
    NewLessonDialog,
    NewTurmaDialog,
    ProfileDialog,
    TurmaColorDialog,
    lesson_url,
    open_folder,
    shared,
    turma_url,
)
from manimflow.lessons import LessonSummary, Library, Status, Turma, status
from manimflow.settings import SettingsDialog, renews
from manimflow.theme import status_dot, turma_badge

logger = logging.getLogger(__name__)

# Seconds between looks at the lessons folder.
REFRESH_INTERVAL = 2.0


@dataclass(frozen=True)
class Here:
    """Where the page is, so the sidebar marks it: a lesson, a turma, the example or the home."""

    lesson: Path | None = None
    turma: str | None = None
    example: bool = False


@dataclass(frozen=True)
class _Lesson:
    id: str
    name: str
    path: Path
    turma: str | None
    status: Status
    working: bool
    exported: bool


@dataclass(frozen=True)
class _Map:
    turmas: tuple[tuple[Turma, tuple[_Lesson, ...]], ...]
    loose: tuple[_Lesson, ...]


def drawer(sidebar: Callable[[], object]) -> object:
    """Draws `sidebar` in the page's left drawer, running the whole height beside the header,
    and returns what it returned."""
    with ui.left_drawer(value=True, bordered=True, top_corner=True, bottom_corner=True).props(
        "width=268 behavior=desktop"
    ).classes("mf-side"):
        return sidebar()


class Sidebar:
    def __init__(self, library: Library, agent: Agent, here: Here = Here()) -> None:
        self.library = library
        self.agent = agent
        self.here = here
        self.expanded: set[str] = {here.turma} if here.turma else set()
        self.new_lesson = shared(NewLessonDialog, library)
        self.new_turma = shared(NewTurmaDialog, library)
        self.instructions = shared(InstructionsDialog, library)
        self.colors = TurmaColorDialog(library, on_changed=self.refresh)
        self.profile = ProfileDialog(library)
        self.settings = SettingsDialog(agent, None, on_signed_out=lambda: ui.navigate.reload(), button=False)
        self.map: _Map | None = None
        with ui.row().classes("w-full items-center justify-between no-wrap px-1 pt-1 pb-2").mark("sidebar-top"):
            with ui.link(target="/").classes("flex items-center gap-2 no-underline text-inherit"):
                ui.label("M").classes("mf-logo")
                ui.label("ManimFlow").classes("font-semibold text-[15px]")
            ui.button(icon="settings", on_click=self.settings.open).props("flat round dense size=sm color=grey-7").tooltip(
                "Configurações"
            ).mark("open-settings")
        ui.button("Nova aula", icon="add", on_click=lambda: self.new_lesson.open(here.turma)).props(
            "unelevated no-caps"
        ).classes("w-full rounded-[10px]").mark("new-lesson")
        with ui.scroll_area().classes("grow w-full"):
            self.content = ui.column().classes("w-full gap-0").mark("sidebar")
        self.usage = ui.column().classes("w-full gap-0")
        with ui.row().classes("w-full items-center no-wrap gap-1 px-1"):
            ui.button("Perfil do professor", icon="tune", on_click=self.profile.open).props(
                "flat no-caps dense align=left color=grey-8"
            ).classes("grow text-[13px]")
        self.refresh()
        ui.timer(REFRESH_INTERVAL, self.refresh)
        ui.timer(0, self._show_usage, once=True)

    def refresh(self) -> None:
        """Redraws the map when a turma, a lesson or a status changed."""
        try:
            current = self._read()
        except Exception:
            # A lesson being created or deleted right now; the next look reads it whole.
            logger.debug("Sidebar refresh failed", exc_info=True)
            return
        if current == self.map:
            return
        self.map = current
        self.content.clear()
        with self.content:
            self._draw(current)

    def _read(self) -> _Map:
        turmas = tuple(
            (turma, tuple(self._lesson(lesson) for lesson in self.library.lessons(turma.name)))
            for turma in self.library.turmas()
        )
        loose = tuple(self._lesson(lesson) for lesson in self.library.lessons())
        return _Map(turmas, loose)

    def _lesson(self, lesson: LessonSummary) -> _Lesson:
        return _Lesson(
            lesson.id,
            lesson.name,
            lesson.path,
            lesson.turma,
            status(lesson.path),
            activity.working(lesson.path),
            activity.fresh_export(lesson.path) is not None,
        )

    def _draw(self, map: _Map) -> None:
        lessons = [lesson for _, inside in map.turmas for lesson in inside] + list(map.loose)
        waiting = [lesson for lesson in lessons if lesson.working or lesson.status == Status.PLAN or lesson.exported]
        if waiting:
            with ui.row().classes("mf-section items-center gap-2"):
                ui.label("Precisa de você")
                ui.label(str(len(waiting))).classes("mf-count hot")
            with ui.column().classes("w-full gap-0").mark("inbox"):
                for lesson in sorted(waiting, key=lambda lesson: (not lesson.working, lesson.status != Status.PLAN)):
                    self._inbox_row(lesson)
        with ui.row().classes("mf-section w-full items-center justify-between no-wrap pr-1"):
            ui.label("Turmas")
            ui.button(icon="add", on_click=self.new_turma.open).props("flat round dense size=xs").tooltip(
                "Nova turma"
            ).mark("new-turma")
        with ui.column().classes("w-full gap-0").mark("turmas"):
            if not map.turmas:
                ui.label("Crie uma turma para juntar as aulas de um curso.").classes("text-xs mf-faint px-2")
            for turma, inside in map.turmas:
                self._turma_row(turma, inside)
        if map.loose:
            ui.label("Sem turma").classes("mf-section")
            with ui.column().classes("w-full gap-0").mark("loose-lessons"):
                for lesson in map.loose:
                    self._lesson_row(lesson, indented=False)
        ui.label("Exemplo").classes("mf-section")
        with ui.element("div").classes("mf-row" + (" on" if self.here.example else "")):
            ui.label("★").classes("mf-badge text-amber-7").style("background:#fff4cc;width:22px;height:22px")
            ui.link("Herói e espelho", EXAMPLE_ROUTE).classes("mf-name mf-stretch").mark("example")

    def _inbox_row(self, lesson: _Lesson) -> None:
        if lesson.working:
            title = "O agente está trabalhando"
        elif lesson.status == Status.PLAN:
            title = "Aprovar o plano"
        else:
            title = "Exportação pronta"
        where = f"{lesson.turma} · {lesson.name}" if lesson.turma else lesson.name

        def open_it() -> None:
            fresh = activity.fresh_export(lesson.path)
            if fresh is not None and not lesson.working and lesson.status != Status.PLAN:
                activity.seen_export(lesson.path)
                open_folder(fresh.folder)
                self.refresh()
                return
            ui.navigate.to(lesson_url(lesson.id) + ("?aba=Plano" if lesson.status == Status.PLAN else ""))

        with ui.element("div").classes("mf-inbox").on("click", open_it).mark("inbox-item"):
            with ui.element("div").classes("pt-1"):
                status_dot(lesson.status if not lesson.exported or lesson.working else Status.EXPORTED, lesson.working)
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(title).classes("text-[13.5px]")
                ui.label(where).classes("text-xs mf-faint ellipsis w-full")

    def _turma_row(self, turma: Turma, lessons: tuple[_Lesson, ...]) -> None:
        open_ = turma.name in self.expanded
        current = self.here.turma == turma.name and self.here.lesson is None
        with ui.element("div").classes("mf-row" + (" on" if current else "")).mark(f"turma-{turma.name}"):
            ui.button(icon="chevron_right" if not open_ else "expand_more", on_click=lambda: self._toggle(turma.name)).props(
                "flat round dense size=xs"
            ).classes("mf-faint -ml-1").mark("toggle-turma")
            turma_badge(turma)
            ui.link(turma.name, turma_url(turma.name)).classes("mf-name mf-stretch")
            ui.label(str(len(lessons))).classes("mf-count mf-hide-on-hover")
            with ui.row().classes("mf-qa no-wrap"):
                ui.button(icon="add", on_click=lambda: self.new_lesson.open(turma.name)).props(
                    "flat round dense size=xs"
                ).tooltip("Nova aula nesta turma")
                ui.button(icon="edit", on_click=lambda: self.instructions.open(turma.name)).props(
                    "flat round dense size=xs"
                ).tooltip("Instruções da turma")
                with ui.button(icon="more_horiz").props("flat round dense size=xs"):
                    with ui.menu():
                        ui.menu_item("Mudar a cor", on_click=lambda: self.colors.open(turma.name))
                        ui.menu_item("Abrir a pasta", on_click=lambda: open_folder(turma.path))
        if open_:
            for lesson in lessons:
                self._lesson_row(lesson, indented=True)
            if not lessons:
                ui.label("Nenhuma aula ainda.").classes("text-xs mf-faint pl-[34px] py-1")

    def _lesson_row(self, lesson: _Lesson, indented: bool) -> None:
        current = self.here.lesson is not None and self.here.lesson.absolute() == lesson.path.absolute()
        classes = "mf-row" + (" lesson" if indented else "") + (" on" if current else "")
        with ui.element("div").classes(classes).mark("lesson-row"):
            status_dot(lesson.status, lesson.working)
            ui.link(lesson.name, lesson_url(lesson.id)).classes("mf-name mf-stretch").mark(
                "current-lesson" if current else "lesson-name"
            )
            with ui.row().classes("mf-qa no-wrap"):
                ui.button(
                    icon="play_arrow", on_click=lambda: ui.navigate.to(lesson_url(lesson.id) + "?aba=Prévia")
                ).props("flat round dense size=xs").tooltip("Ver a prévia")
                ui.button(
                    icon="file_download", on_click=lambda: ui.navigate.to(lesson_url(lesson.id) + "?exportar=1")
                ).props("flat round dense size=xs").tooltip("Exportar")
                with ui.button(icon="more_horiz").props("flat round dense size=xs"):
                    with ui.menu():
                        ui.menu_item("Abrir a pasta", on_click=lambda: open_folder(lesson.path))

    def _toggle(self, turma: str) -> None:
        self.expanded ^= {turma}
        self.map = None
        self.refresh()

    async def _show_usage(self) -> None:
        try:
            quota = await self.agent.quota()
        except Exception:
            # Signed out, or the engine is still starting: the card only shows a known usage.
            logger.debug("Reading the plan's usage failed", exc_info=True)
            return
        if not quota or self.usage.is_deleted:
            return
        window = max(quota, key=lambda window: window.used_percent)
        with self.usage:
            with ui.element("div").classes("mf-usage").on("click", self.settings.open).mark("usage"):
                with ui.row().classes("w-full justify-between"):
                    ui.label("Uso do ChatGPT")
                    ui.label(f"{window.used_percent}%").classes("mf-muted")
                ui.linear_progress(window.used_percent / 100, show_value=False, size="6px").props("rounded")
                if renews := _renews(window):
                    ui.label(renews).classes("mf-faint mt-1")


def _renews(window: QuotaWindow) -> str | None:
    return renews(window.resets_at).capitalize() if window.resets_at is not None else None
