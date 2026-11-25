"""The app's pages: the home, a turma's page and the lesson screens they open, each with
the sidebar.

Every UI string is in Portuguese.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from nicegui import ui
from starlette.requests import Request

from manimflow import activity
from manimflow.agent import Agent
from manimflow.app import Opening, lesson_page, send_on_open
from manimflow.dialogs import (
    EXAMPLE_ROUTE,
    LESSON_ROUTE,
    TURMA_ROUTE,
    FolderDialog,
    InstructionsDialog,
    NewLessonDialog,
    NewTurmaDialog,
    lesson_url,
    shared,
    turma_url,
)
from manimflow.lessons import EXAMPLE_NAME, LessonNameError, LessonSummary, Library, Status, Turma, status
from manimflow.plan import load_plan
from manimflow.preview import latest_render, serve_outputs
from manimflow.settings import model_switch
from manimflow.sidebar import Here, Sidebar, drawer
from manimflow.theme import apply_theme, status_pill, turma_badge

logger = logging.getLogger(__name__)

_NO_TURMA = ""


def app_root(agent: Agent, library: Library) -> Callable[[Request], Awaitable[None]]:
    """The root page, which shows the home, a turma or a lesson depending on the address.

    Not ui.sub_pages: the lesson screen has a header, which NiceGUI only allows at
    the top of a page.
    """
    example = library.example()

    async def page(request: Request) -> None:
        apply_theme()
        path = request.url.path
        opening = Opening(tab=request.query_params.get("aba"), export="exportar" in request.query_params)
        if path == EXAMPLE_ROUTE:
            await lesson_page(agent, example, _sidebar(library, agent, Here(example=True)), opening)()
        elif path.startswith(LESSON_ROUTE):
            lesson = library.lesson(path.removeprefix(LESSON_ROUTE))
            if lesson is None:
                _not_found(library, agent, "Esta aula não está na pasta das aulas.")
                return
            turma = library.turma_of(lesson)
            here = Here(lesson=lesson, turma=turma.name if turma else None)
            await lesson_page(agent, lesson, _sidebar(library, agent, here), opening, turma)()
        elif path.startswith(TURMA_ROUTE):
            turma = library.turma(path.removeprefix(TURMA_ROUTE))
            if turma is None:
                _not_found(library, agent, "Esta turma não está na pasta das aulas.")
                return
            _drawer(library, agent, Here(turma=turma.name))
            await TurmaPage.build(library, agent, turma)
        elif path == "/":
            _drawer(library, agent, Here())
            await Home.build(library, agent)
        else:
            _not_found(library, agent, "Esta página não existe.")

    return page


def _sidebar(library: Library, agent: Agent, here: Here) -> Callable[[], object]:
    return lambda: Sidebar(library, agent, here)


def _drawer(library: Library, agent: Agent, here: Here) -> None:
    drawer(lambda: Sidebar(library, agent, here))


class StartComposer:
    """The message box that starts a lesson: the teacher describes the animation, picks the
    turma, and the new lesson opens with the message on its way to the agent."""

    def __init__(self, library: Library, turma: str | None, placeholder: str, pick_turma: bool) -> None:
        self.library = library
        with ui.column().classes("mf-composer").mark("start-composer"):
            self.text = (
                ui.textarea(placeholder=placeholder)
                .props("borderless autogrow dense")
                .classes("w-full")
                .mark("start-message")
            )
            self.text.on("keydown.enter.exact.prevent", self.start)
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                turmas = {turma.name: turma.name for turma in library.turmas()}
                self.turma = ui.select(
                    {_NO_TURMA: "Sem turma", **turmas}, value=turma if turma in turmas else _NO_TURMA
                ).props("dense borderless options-dense").classes("text-[13px]").mark("start-turma")
                self.turma.set_visibility(pick_turma and bool(turmas))
                self.switch_slot = ui.row().classes("items-center")
                ui.space()
                ui.button(icon="arrow_upward", on_click=self.start).props("round unelevated dense").classes(
                    "w-[34px] h-[34px]"
                ).tooltip("Começar a aula").mark("start")

    async def add_switch(self, agent: Agent) -> None:
        with self.switch_slot:
            try:
                await model_switch(agent)
            except Exception:
                # Codex didn't answer: the lesson page draws its own switch.
                logger.debug("Reading the model settings failed", exc_info=True)

    def start(self) -> None:
        text = (self.text.value or "").strip()
        if not text:
            return
        turma = self.turma.value or None
        try:
            lesson = self.library.create(self.library.free_name(text, turma), turma)
        except (LessonNameError, OSError):
            logger.exception("Creating a lesson from a message failed")
            ui.notify("Não foi possível criar a aula na pasta das aulas.", type="negative")
            return
        send_on_open(lesson, text)
        ui.navigate.to(lesson_url(self.library.lesson_id(lesson) or lesson.name))


class Home:
    """"O que vamos animar hoje?": a message box that starts a lesson, then the turmas,
    the lessons without a turma and the example."""

    def __init__(self, library: Library) -> None:
        self.library = library
        ui.page_title("ManimFlow")
        new_turma = shared(NewTurmaDialog, library)
        folder_dialog = FolderDialog(library, on_changed=lambda: ui.navigate.reload())
        with ui.column().classes("mf-page"):
            with ui.column().classes("w-full max-w-2xl mx-auto items-center gap-2 mt-10"):
                ui.label("O que vamos animar hoje?").classes("text-3xl font-medium")
                ui.label("Descreva a animação e escolha a turma. O agente monta o plano antes de escrever código.").classes(
                    "mf-muted text-center"
                )
                self.composer = StartComposer(
                    library, None, "Ex.: uma onda estacionária numa corda com 3 harmônicos…", pick_turma=True
                )
            turmas = library.turmas()
            with ui.row().classes("w-full items-center justify-between mt-6"):
                ui.label("Turmas").classes("text-base font-semibold")
                ui.button("Nova turma", icon="add", on_click=new_turma.open).props("flat no-caps dense")
            with ui.element("div").classes("mf-grid").mark("turma-cards"):
                for turma in turmas:
                    _turma_card(turma, library.lessons(turma.name))
                with ui.element("div").classes("mf-newcard").style("min-height:110px").on("click", new_turma.open):
                    ui.label("＋ Nova turma")
            loose = library.lessons()
            ui.label("Aulas sem turma" if turmas else "Minhas aulas").classes("text-base font-semibold mt-4")
            with ui.element("div").classes("mf-grid").mark("lessons"):
                if not loose:
                    ui.label("Nenhuma aula fora das turmas. Comece pela caixa de mensagem acima.").classes(
                        "mf-muted"
                    ).mark("no-lessons")
                for lesson in loose:
                    lesson_card(lesson, None)
            with ui.row().classes("w-full items-center gap-2 mf-muted text-[13px]"):
                ui.label(f"Pasta das aulas: {library.folder}")
                ui.button("Mudar pasta", on_click=folder_dialog.open).props("flat dense no-caps")
            ui.separator()
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Exemplo · {EXAMPLE_NAME}").classes("mf-muted")
                ui.button("Abrir o exemplo", on_click=lambda: ui.navigate.to(EXAMPLE_ROUTE)).props(
                    "outline no-caps"
                )

    @classmethod
    async def build(cls, library: Library, agent: Agent) -> "Home":
        home = cls(library)
        await home.composer.add_switch(agent)
        return home


class TurmaPage:
    """A turma: its color band with the counts and a message box for a new lesson, the
    lesson cards with a "Nova aula" card, and the turma's instructions on the side."""

    def __init__(self, library: Library, turma: Turma) -> None:
        self.library = library
        self.turma = turma
        ui.page_title(f"{turma.name} · ManimFlow")
        new_lesson = shared(NewLessonDialog, library)
        instructions = shared(InstructionsDialog, library)
        lessons = library.lessons(turma.name)
        statuses = [status(lesson.path) for lesson in lessons]
        with ui.column().classes("mf-page"):
            with ui.column().classes("mf-band").style(f"background:{turma.color}14"):
                with ui.row().classes("w-full items-start justify-between no-wrap"):
                    with ui.row().classes("items-center gap-3 no-wrap"):
                        turma_badge(turma, size=40)
                        ui.label(turma.name).classes("text-2xl font-semibold")
                    with ui.row().classes("gap-2").mark("turma-counts"):
                        _stat(len(lessons), "aula" if len(lessons) == 1 else "aulas")
                        ready = sum(state in (Status.READY, Status.EXPORTED) for state in statuses)
                        _stat(ready, "pronta" if ready == 1 else "prontas")
                        _stat(statuses.count(Status.PLAN), "para aprovar")
                self.composer = StartComposer(
                    library, turma.name, f"Nova aula em {turma.name}…", pick_turma=False
                )
            with ui.row().classes("w-full items-start no-wrap gap-6"):
                with ui.column().classes("grow min-w-0 gap-3"):
                    ui.label("Aulas").classes("text-base font-semibold")
                    with ui.element("div").classes("mf-grid").mark("lessons"):
                        for lesson in lessons:
                            lesson_card(lesson, turma)
                        with ui.element("div").classes("mf-newcard").on(
                            "click", lambda: new_lesson.open(turma.name)
                        ).mark("new-lesson-card"):
                            ui.label("＋ Nova aula")
                with ui.column().classes("w-72 flex-none gap-2 mf-card p-4 mt-9").mark("turma-instructions"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Instruções da turma").classes("font-semibold")
                        ui.button("Editar", on_click=lambda: instructions.open(turma.name)).props(
                            "flat dense no-caps"
                        )
                    try:
                        text = library.turma_instructions(turma.name)
                    except (OSError, UnicodeDecodeError):
                        text = ""
                    ui.markdown(text or "Sem instruções ainda.").classes("mf-instr text-[13px] mf-muted")
                    ui.label("O agente lê estas instruções em toda aula da turma.").classes("text-xs mf-faint")

    @classmethod
    async def build(cls, library: Library, agent: Agent, turma: Turma) -> "TurmaPage":
        page = cls(library, turma)
        await page.composer.add_switch(agent)
        return page


def _stat(number: int, label: str) -> None:
    with ui.element("div").classes("mf-stat"):
        ui.html(f"<b>{number}</b>{label}")


def _turma_card(turma: Turma, lessons: list[LessonSummary]) -> None:
    with ui.card().classes("mf-card p-4 gap-2").mark("turma-card"):
        with ui.row().classes("items-center gap-3 no-wrap w-full"):
            turma_badge(turma, size=32)
            ui.link(turma.name, turma_url(turma.name)).classes("font-medium mf-stretch text-inherit no-underline")
        count = len(lessons)
        ui.label(f"{count} aula" + ("" if count == 1 else "s")).classes("text-[13px] mf-muted")
        ui.element("div").classes("h-1 w-12 rounded").style(f"background:{turma.color}")


def lesson_card(lesson: LessonSummary, turma: Turma | None) -> None:
    """A lesson as a card: its newest state image, name, status and last edit."""
    current = status(lesson.path)
    working = activity.working(lesson.path)
    url = lesson_url(lesson.id)
    with ui.card().classes("mf-card mf-lessoncard").mark("lesson-card"):
        with ui.element("div").classes("mf-thumb"):
            if thumbnail := _thumbnail(lesson.path):
                ui.image(thumbnail)
            else:
                ui.label("sem prévia ainda")
        with ui.row().classes("mf-hover"):
            ui.button("▶ Prévia", on_click=lambda: ui.navigate.to(url + "?aba=Prévia")).props(
                "dense no-caps unelevated color=white text-color=black size=sm"
            )
            ui.button("⇩ Exportar", on_click=lambda: ui.navigate.to(url + "?exportar=1")).props(
                "dense no-caps unelevated color=white text-color=black size=sm"
            )
        with ui.column().classes("mf-body"):
            ui.link(lesson.name, url).classes("font-medium mf-stretch text-inherit no-underline ellipsis w-full")
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                status_pill(current, working)
                ui.label(_edited(lesson.edited)).classes("text-xs mf-faint whitespace-nowrap")
            details = [turma.name] if turma else []
            if lesson.states is not None:
                details.append(f"{lesson.states} estado" + ("" if lesson.states == 1 else "s"))
            if details:
                ui.label(" · ".join(details)).classes("text-xs mf-faint")


def _thumbnail(lesson: Path) -> str | None:
    """The newest image of the lesson's last rendered state, or None before any render."""
    try:
        plan, _ = load_plan(lesson)
    except Exception:
        return None
    if plan is None:
        return None
    served_at = serve_outputs(lesson)
    for state in reversed(plan.states):
        if url := latest_render(lesson, served_at, state.scene, "png"):
            return url
    return None


def _not_found(library: Library, agent: Agent, message: str) -> None:
    ui.page_title("ManimFlow")
    _drawer(library, agent, Here())
    with ui.column().classes("mf-page"):
        ui.label(message).classes("text-lg")
        ui.link("Voltar para o início", "/")


def _edited(when: datetime) -> str:
    days = (datetime.now().date() - when.date()).days
    if days == 0:
        return f"hoje às {when:%H:%M}"
    if days == 1:
        return f"ontem às {when:%H:%M}"
    return f"em {when:%d/%m/%Y}"
