"""The NiceGUI app: the lesson screen with its chat. Every UI string is in Portuguese."""

import asyncio
import logging
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nicegui import app, ui

from manimflow import activity, conversation, plan_turn
from manimflow.agent import (
    Agent,
    AgentError,
    AssistantText,
    Checklist,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    ImageViewed,
    Working,
)
from manimflow.code_tab import FILES as CODE_FILES
from manimflow.code_tab import CodeTab
from manimflow.conversation import ChatTurn, Conversation
from manimflow.dialogs import turma_url
from manimflow.equations import EquationsPanel
from manimflow.export_tab import ExportDialog
from manimflow.lessons import PLACEHOLDER_SCENE, Status, Turma, status
from manimflow.pins import Pin, Pins
from manimflow.plan import PLAN_FILE, Plan, load_plan
from manimflow.plan_cards import PlanCards
from manimflow.preview import PreviewPanel, latest_render, serve_outputs
from manimflow.settings import SettingsDialog, model_switch
from manimflow.sidebar import Sidebar, drawer
from manimflow.sign_in import SignIn
from manimflow.theme import apply_theme, status_pill, turma_badge
from manimflow.versioning import History, Version

logger = logging.getLogger(__name__)

_FILE_CHANGES = {"added": "Arquivo criado", "modified": "Arquivo alterado", "deleted": "Arquivo apagado"}

# Commands that leave new renders for the preview.
_RENDERS = re.compile(r"\bmanimflow\s+(preview|render)\b")

# The steps of the agent's self-check, named for the teacher above the raw command.
_STEPS = [
    (re.compile(r"\bmanimflow\s+plan\s+validate\b"), "Validando o plano"),
    (re.compile(r"\bmanimflow\s+preview\b"), "Renderizando a prévia"),
    (re.compile(r"\bmanimflow\s+render\b"), "Renderizando a versão final"),
    (re.compile(r"\bmanimflow\s+frames\b"), "Extraindo os quadros"),
    (re.compile(r"\bmanimflow\s+check-continuity\b"), "Conferindo a continuidade"),
    (re.compile(r"\bpytest\b.*\btest_fisica\.py\b"), "Rodando os testes de física"),
]

# The lesson's files as the teacher calls them, for "Lendo o plano" or "Escrevendo as cenas".
_FILES = {
    "perfil.md": "o perfil do professor",
    "turma.md": "as instruções da turma",
    "CONTEXTO.md": "o contexto da aula",
    "plano.yaml": "o plano",
    "cenas.py": "as cenas",
    "fisica.py": "a física",
    "test_fisica.py": "os testes de física",
    "SKILL.md": "as instruções do ManimFlow",
}


def serve(agent: Agent, root: Callable[..., Awaitable[None]]) -> None:
    """Serves the app's `root` page on localhost only and opens it in the default browser."""
    app.on_shutdown(agent.close)
    ui.run(
        root,
        host="127.0.0.1",
        port=_free_port(),
        show=True,
        title="ManimFlow",
        language="pt-BR",
        reload=False,
    )


def _free_port() -> int:
    # The teacher may already run Jupyter or another local server on the usual ports.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@dataclass(frozen=True)
class Opening:
    """How the lesson screen opens: on a workspace tab, with the export dialog open."""

    tab: str | None = None
    export: bool = False


# The first message of a lesson started from a message box, sent once the lesson opens.
_first_messages: dict[Path, str] = {}


def send_on_open(lesson: Path, text: str) -> None:
    """Sends `text` to the agent as soon as the lesson's chat opens."""
    _first_messages[lesson.absolute()] = text


TABS = ("Prévia", "Plano", "Código", "Equações")


def lesson_page(
    agent: Agent,
    lesson: Path,
    sidebar: Callable[[], object] | None = None,
    opening: Opening = Opening(),
    turma: Turma | None = None,
    reset_example: Callable[[], object] | None = None,
) -> Callable[[], Awaitable[None]]:
    """Builds the page for one lesson, which shows the lesson's one conversation.

    `sidebar` draws the side column, such as the map of turmas and lessons. With
    `reset_example`, the lesson is the example, and the header offers to bring the
    original back by calling it.
    """
    example = reset_example is not None

    async def page() -> None:
        apply_theme()
        ui.page_title(f"{lesson.name} · ManimFlow")
        history = History.open(lesson)
        with ui.header().classes("mf-header items-center px-4 gap-2 no-wrap"):
            if turma is not None:
                turma_badge(turma)
                ui.link(turma.name, turma_url(turma.name)).classes("mf-crumb mf-muted no-underline whitespace-nowrap")
                ui.label("/").classes("mf-faint")
            ui.label(lesson.name).classes("mf-crumb font-medium ellipsis min-w-0").mark("lesson-title")
            LessonStatus(lesson)
            ui.space()
            controls = ui.row().classes("items-center gap-2 no-wrap")
        side = drawer(sidebar) if sidebar is not None else None
        body = ui.column().classes("w-full")

        async def open_chat() -> None:
            talk = conversation.conversation(agent, lesson, example)
            controls.clear()
            body.clear()
            with body:
                pins = Pins(lesson)
                export = ExportDialog(lesson)
                with ui.splitter(value=Workspace.DEFAULT, limits=(22, 80)).classes("mf-split") as splitter:
                    with splitter.before:
                        with ui.column().classes("mf-chatcol") as chat_column:
                            with ui.row().classes("mf-chathead items-center no-wrap gap-2 w-full"):
                                ui.label("Conversa").classes("font-semibold")
                                ui.space()
                                LessonStage(lesson)
                            chat = Chat(talk, history, pins, example=example)
                    with splitter.after:
                        with ui.column().classes("mf-ws gap-0 w-full"):
                            with ui.row().classes("mf-tabsbar items-center no-wrap w-full"):
                                with ui.tabs().props("dense no-caps align=left").classes("grow").mark(
                                    "workspace-tabs"
                                ) as tabs:
                                    for name in TABS:
                                        ui.tab(name)
                                tabs.set_value(opening.tab if opening.tab in TABS else "Prévia")
                                tools = ui.row().classes("items-center gap-0 no-wrap")
                            with ui.tab_panels(tabs, value=tabs.value).classes("mf-panels w-full"):
                                with ui.tab_panel("Prévia"):
                                    with ui.scroll_area().classes("mf-pane"):
                                        PreviewPanel(lesson, pins)
                                with ui.tab_panel("Plano"):
                                    with ui.scroll_area().classes("mf-pane"):
                                        plan_cards = PlanCards(lesson, chat, history)
                                with ui.tab_panel("Código"):
                                    chat.on_busy(CodeTab(lesson, history).set_agent_working)
                                with ui.tab_panel("Equações"):
                                    with ui.scroll_area().classes("mf-pane"):
                                        EquationsPanel(lesson)
            with controls:
                show = ui.button("Mostrar prévia", icon="vertical_split").props("flat no-caps dense").mark(
                    "show-workspace"
                )
                if reset_example is not None:
                    ExampleReset(agent, lesson, reset_example, chat)
                ui.button("Exportar", icon="file_download", on_click=export.open).props(
                    "unelevated no-caps rounded"
                ).mark("open-export")
            workspace = Workspace(splitter, tabs, chat_column, show)
            with tools:
                ui.button(icon="close_fullscreen", on_click=workspace.smaller).props("flat round dense size=sm").tooltip(
                    "Prévia menor"
                )
                ui.button(icon="open_in_full", on_click=workspace.bigger).props("flat round dense size=sm").tooltip(
                    "Prévia maior"
                )
                ui.button(icon="close", on_click=workspace.close).props("flat round dense size=sm").tooltip(
                    "Fechar a prévia"
                ).mark("close-workspace")
            chat.workspace = workspace
            chat.plan_cards = plan_cards
            with chat.switch_slot:
                switch = await model_switch(agent)
            if isinstance(side, Sidebar):
                # Its gear opens the settings; a model picked there moves this lesson's switch.
                side.settings.switch = switch
            else:
                with controls:
                    SettingsDialog(agent, switch, on_signed_out=sign_in)
            if opening.export:
                export.open()
            # The conversation so far, and the turn that is running, if any.
            await chat.load()
            if (first := _first_messages.pop(lesson.absolute(), None)) is not None:
                # Not awaited here: the page must show before the turn ends.
                ui.timer(0, lambda: chat.ask(first), once=True)

        async def signed_in() -> None:
            # The whole page, so the sidebar shows the account too.
            ui.navigate.reload()

        def sign_in() -> None:
            controls.clear()
            body.clear()
            with body:
                SignIn(agent, on_signed_in=signed_in)

        if (await agent.account()).logged_in:
            await open_chat()
        else:
            sign_in()

    return page


class LessonStatus:
    """The lesson's status pill in the header, kept up to date."""

    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        self.shown: tuple[Status, bool] | None = None
        self.slot = ui.row().classes("items-center").mark("lesson-status")
        self.refresh()
        ui.timer(2.0, self.refresh)

    def refresh(self) -> None:
        try:
            current = (status(self.lesson), activity.working(self.lesson))
        except Exception:
            logger.debug("Reading the lesson's status failed", exc_info=True)
            return
        if current == self.shown:
            return
        self.shown = current
        self.slot.clear()
        with self.slot:
            status_pill(*current)


class Workspace:
    """The preview side of the lesson screen: resizable by dragging the bar, by its buttons
    or back to its size with a double click on the bar, and closable, so the chat takes the
    whole page."""

    # The chat's share of the width, in percent.
    DEFAULT = 42
    _SIZES = (62, 42, 28)

    def __init__(self, splitter: ui.splitter, tabs: ui.tabs, chat: ui.column, show: ui.button) -> None:
        self.splitter = splitter
        self.tabs = tabs
        self.chat = chat
        self.show_button = show
        self.is_open = True
        show.on_click(lambda: self.show())
        show.set_visibility(False)
        # Only a double click on the bar itself.
        splitter.on(
            "dblclick",
            self.reset,
            js_handler="(event) => { if (event.target.closest('.q-splitter__separator')) emit(); }",
        )

    def show(self, tab: str | None = None) -> None:
        """Opens the workspace, on `tab` when given."""
        if tab is not None:
            self.tabs.set_value(tab)
        if self.is_open:
            return
        self.is_open = True
        self.splitter.classes(remove="mf-closed")
        self.chat.classes(remove="mf-full")
        self.splitter.set_value(self.DEFAULT)
        self.show_button.set_visibility(False)

    def close(self) -> None:
        self.is_open = False
        self.splitter.classes(add="mf-closed")
        self.chat.classes(add="mf-full")
        self.show_button.set_visibility(True)

    def reset(self) -> None:
        self.splitter.set_value(self.DEFAULT)

    def bigger(self) -> None:
        current = self.splitter.value or self.DEFAULT
        self.splitter.set_value(max((size for size in self._SIZES if size < current - 1), default=current))

    def smaller(self) -> None:
        current = self.splitter.value or self.DEFAULT
        self.splitter.set_value(min((size for size in self._SIZES if size > current + 1), default=current))


class LessonStage:
    """Where the lesson is in its making, above the chat: plan, the teacher's approval,
    animation, ready. Kept up to date."""

    _STEPS = ("Plano", "Sua aprovação", "Animação", "Pronta")
    _AT = {Status.NEW: 0, Status.PLAN: 1, Status.IN_PROGRESS: 2, Status.READY: 3, Status.EXPORTED: 3}

    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        self.shown: int | None = None
        self.row = ui.row().classes("mf-stages items-center no-wrap gap-1").mark("lesson-stage")
        self.refresh()
        ui.timer(2.0, self.refresh)

    def refresh(self) -> None:
        try:
            at = self._AT[status(self.lesson)]
        except Exception:
            logger.debug("Reading the lesson's status failed", exc_info=True)
            return
        if at == self.shown:
            return
        self.shown = at
        self.row.clear()
        with self.row:
            for index, name in enumerate(self._STEPS):
                if index:
                    ui.icon("chevron_right", size="14px").classes("mf-faint")
                done = index < at or (index == at == len(self._STEPS) - 1)
                state = "done" if done else "now" if index == at else "later"
                if index == at == 1:
                    state = "wait"
                with ui.row().classes(f"mf-step {state} items-center no-wrap gap-1").mark(f"stage-{state}"):
                    if done:
                        ui.icon("check", size="13px")
                    ui.label(name)


class ExampleReset:
    """"Restaurar exemplo" in the example's header: brings the original back, files and
    conversation, after a confirmation."""

    def __init__(self, agent: Agent, lesson: Path, reset: Callable[[], object], chat: "Chat") -> None:
        self.agent = agent
        self.lesson = lesson
        self.reset = reset
        self.chat = chat
        with ui.dialog() as self.dialog, ui.card().classes("w-[28rem] items-stretch gap-3"):
            ui.label("Restaurar o exemplo original?").classes("text-lg")
            ui.label(
                "O exemplo volta a ser como veio no ManimFlow, e a conversa sobre ele recomeça. "
                "As suas mudanças continuam no histórico de versões."
            ).classes("mf-muted")
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Restaurar", on_click=self._restore).mark("confirm-reset-example")
        ui.button("Restaurar exemplo", icon="restart_alt", on_click=self._ask).props("flat no-caps dense").mark(
            "reset-example"
        )

    def _ask(self) -> None:
        if self.chat.busy:
            ui.notify("Espere o agente terminar para restaurar o exemplo.")
            return
        self.dialog.open()

    async def _restore(self) -> None:
        self.dialog.close()
        if self.chat.busy:
            ui.notify("Espere o agente terminar para restaurar o exemplo.")
            return
        try:
            self.reset()
        except Exception:
            logger.exception("Restoring the example failed")
            ui.notify("Não foi possível restaurar o exemplo agora. Tente de novo.", type="negative")
            return
        # No turn starts in the old conversation while its threads are put away.
        conversation.conversation(self.agent, self.lesson).closed = True
        try:
            await self.agent.archive(self.lesson)
        except Exception:
            logger.exception("Archiving the example's conversation failed")
        finally:
            # Every tab on the example, this one too, reloads on a new conversation.
            conversation.forget(self.agent, self.lesson)


class Progress:
    """The bar above the message box while the agent works: what it is doing now, its own
    list of steps when it keeps one, for how long, and "Parar"."""

    def __init__(self, on_stop: Callable[[], Awaitable[None]]) -> None:
        self.turn: ChatTurn | None = None
        self.now = ""
        with ui.row().classes("mf-progress items-center no-wrap gap-2 w-full").mark("progress") as self.row:
            ui.spinner(size="sm")
            with ui.column().classes("gap-0 grow min-w-0"):
                self.label = ui.label().classes("ellipsis w-full").mark("progress-label")
                self.steps = ui.label().classes("text-xs mf-faint ellipsis w-full").mark("progress-steps")
            self.clock = ui.label().classes("text-xs mf-faint whitespace-nowrap")
            self.stop = (
                ui.button("Parar", icon="stop_circle", on_click=on_stop)
                .props("flat dense no-caps size=sm color=grey-8")
                .mark("stop")
            )
        self.row.set_visibility(False)
        ui.timer(1.0, self._tick)

    def follow(self, turn: ChatTurn) -> None:
        self.turn = turn
        self.now = _START
        for event in turn.events:
            self.now = _doing(event) or self.now
        self.stop.set_enabled(True)
        self.row.set_visibility(True)
        self.show(turn)

    def show(self, turn: ChatTurn, event: Event | None = None) -> None:
        if event is not None and (doing := _doing(event)) is not None:
            # The agent thinks between any two steps; the bar keeps naming the last step,
            # which tells where in the work it is.
            if not (doing == _THINKING and self.now != _START):
                self.now = doing
        self.label.set_text(f"{self.now}…")
        self.steps.set_text(_checklist(turn.checklist))
        self.steps.set_visibility(turn.checklist is not None)
        self._tick()

    def stopping(self) -> None:
        self.stop.set_enabled(False)
        self.label.set_text("Parando…")

    def done(self) -> None:
        self.turn = None
        self.row.set_visibility(False)

    def _tick(self) -> None:
        if self.turn is not None:
            self.clock.set_text(_clock(self.turn.elapsed))


class Chat:
    """The lesson's conversation on this page: what it said so far, the turn that is
    running, and the message box. The conversation itself lives on the server."""

    def __init__(self, talk: Conversation, history: History, pins: Pins | None = None, example: bool = False) -> None:
        self.talk = talk
        self.history = history
        self.lesson = talk.lesson
        self.pins = pins
        # Set once the workspace exists: the result cards open its tabs, the bar approves the plan.
        self.workspace: Workspace | None = None
        self.plan_cards: PlanCards | None = None
        # Told when a turn starts and ends, for whatever must wait for the agent, and
        # before a turn starts, for whatever must be committed first.
        self._busy_listeners: list[Callable[[bool], None]] = []
        self._before_turn: list[Callable[[], None]] = []
        self._busy = False
        # Until the conversation so far shows, a message could start a turn the page misses.
        self._ready = False
        self._views: dict[int, _TurnView] = {}
        # The pins this page sent with the running turn, which turn green once it ran.
        self._sent: list[Pin] = []
        self._session: str | None = None
        # The approve buttons inside the chat's plan cards; only the newest shows.
        self._approve_in_chat: ui.row | None = None
        with ui.scroll_area().classes("mf-thread w-full") as self.scroll:
            if example:
                self._welcome()
            self.conversation = ui.column().classes("mf-conversation").mark("conversation")
        with ui.column().classes("mf-composer-wrap"):
            self.progress = Progress(self.stop)
            with ui.column().classes("mf-composer"):
                with ui.row().classes("mf-approvebar items-center no-wrap gap-2").mark("approve-bar") as self.approve_bar:
                    ui.icon("hourglass_top", size="18px")
                    ui.label("O plano está esperando a sua aprovação.").classes("grow")
                    ui.button("Ver plano", on_click=lambda: self.open_tab("Plano")).props(
                        "outline dense no-caps rounded size=sm color=brown-8"
                    ).classes("px-2")
                    ui.button("Aprovar plano", on_click=self._approve).props(
                        "unelevated dense no-caps rounded size=sm"
                    ).classes("px-2").mark("approve-bar-button")
                self.approve_bar.set_visibility(False)
                self.attachments = ui.row().classes("gap-1 flex-wrap").mark("attachments")
                self.attachments.set_visibility(False)
                self.input = (
                    ui.textarea(placeholder="Peça uma mudança…")
                    .props("borderless autogrow dense")
                    .classes("w-full")
                    .mark("message")
                )
                self.input.on("keydown.enter.exact.prevent", self.send)
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    self.switch_slot = ui.row().classes("items-center")
                    ui.space()
                    self.button = (
                        ui.button(icon="arrow_upward", on_click=self.send)
                        .props("round unelevated dense")
                        .classes("w-[34px] h-[34px]")
                        .tooltip("Enviar (Enter)")
                        .mark("send")
                    )
        if pins is not None:
            pins.on_change(self._show_attachments)
        self.input.set_enabled(False)
        self.button.set_enabled(False)
        ui.timer(1.0, self._show_approve_bar)

    async def load(self) -> None:
        """Shows the conversation so far, joins the turn that is running and follows the
        ones to come."""
        await self.talk.load()
        if self.talk.closed:
            # The conversation started over while the page opened, as when the example is
            # restored in another tab: the page shows the new one once it is there. The
            # page's timers already have NiceGUI send it before its response timeout; this
            # keeps it so without them.
            await ui.context.client.connected()
            await self.talk.replaced.wait()
            ui.navigate.reload()
            return
        # From here on without awaiting, so no turn starts or ends unseen.
        self._ready = True
        with self.conversation:
            if not self.talk.loaded:
                # The chat still works; the next page tries to read them again.
                _error_row("Não foi possível mostrar as mensagens anteriores agora.")
            for turn in self.talk.ended:
                self._draw(turn)
        if self.talk.running is not None:
            # Joined, not started: what the teacher left uncommitted is the agent's now.
            self._show_turn(self.talk.running)
        else:
            self.input.set_enabled(True)
            self.button.set_enabled(True)
        self.talk.listen(self)
        ui.context.client.on_delete(lambda: self.talk.forget(self))
        self.scroll.scroll_to(percent=1)

    def on_busy(self, listener: Callable[[bool], None]) -> None:
        """Calls `listener` with True while the agent works on the lesson, and with False
        when it stops."""
        self._busy_listeners.append(listener)

    def before_turn(self, listener: Callable[[], None]) -> None:
        """Calls `listener` when a turn starts, before anything is committed."""
        self._before_turn.append(listener)

    @property
    def busy(self) -> bool:
        """Whether the agent is working on the lesson, or the page isn't ready for it yet."""
        return self.talk.busy or not self._ready

    def open_tab(self, tab: str) -> None:
        if self.workspace is not None:
            self.workspace.show(tab)

    async def send(self) -> None:
        text = (self.input.value or "").strip()
        if not text or self.busy:
            return
        self.input.value = ""
        await self.ask(text)

    async def ask(self, text: str) -> None:
        """Sends the teacher's own message. Until the teacher first approves the plan, it
        asks for the plan (see plan_turn)."""
        try:
            planning = plan_turn.pending(self.lesson)
        except Exception:
            logger.exception("Reading whether the lesson waits for its plan failed")
            planning = False
        turn = await self._start(text, plan=planning)
        if turn is None or turn.plan is None or not turn.ok:
            return
        if turn.plan_written:
            self.open_tab("Plano")
        elif turn.plan.approved and self.plan_cards is not None:
            # The teacher approved it in their own words, after seeing it in the chat, as
            # the button does; the cards may not have looked at the file since.
            self.plan_cards.refresh()
            if self.plan_cards.can_approve:
                await self.plan_cards.approve()

    async def submit(
        self,
        text: str,
        summary: str | None = None,
        after: Callable[[ChatTurn | None], None] | None = None,
        attachments: Sequence[Path] = (),
    ) -> bool:
        """Sends `text` as the teacher's message, as it is, with `attachments`; False when
        the turn failed.

        The turn's version is named after `summary` when given, else after `text`.
        `after` runs on the server once the turn's version is saved.
        """
        turn = await self._start(text, summary=summary, after=after, attachments=attachments)
        if turn is None and after is not None:
            # It never started: what the caller did ahead of it is undone as for a failure.
            after(None)
        return turn is not None and turn.ok

    async def _start(
        self,
        text: str,
        summary: str | None = None,
        plan: bool = False,
        after: Callable[[ChatTurn], None] | None = None,
        attachments: Sequence[Path] = (),
    ) -> ChatTurn | None:
        if self.talk.closed:
            # The example was restored in another tab.
            ui.navigate.reload()
            return None
        if self.busy:
            ui.notify("Espere o agente terminar.")
            return None
        pins = self.pins.pending() if self.pins is not None else []
        attachments = [*attachments, *self._pins_attachment(pins)]
        self._sent = pins
        task = self.talk.start(
            text,
            summary=summary,
            notes=[f"📍 {pin.number} · {pin.state}: {pin.text}" for pin in pins],
            attachments=attachments,
            plan=plan,
            after=after,
        )
        # The turn goes on if the page goes away.
        return await asyncio.shield(task)

    async def stop(self) -> None:
        self.progress.stopping()
        await self.talk.stop()

    # The conversation tells every page that shows it.

    def turn_started(self, turn: ChatTurn) -> None:
        for listener in self._before_turn:
            listener()
        self._show_turn(turn)

    def _show_turn(self, turn: ChatTurn) -> None:
        self._set_busy(True)
        with self.conversation:
            view = self._bubble(turn)
            for event in turn.events:
                view.show(event)
        self.progress.follow(turn)
        self.scroll.scroll_to(percent=1)

    def turn_event(self, turn: ChatTurn, event: Event) -> None:
        view = self._views.get(id(turn))
        if view is None:
            return
        if not isinstance(event, (Working, Checklist)):
            with self.conversation:
                view.show(event)
            self.scroll.scroll_to(percent=1)
        self.progress.show(turn, event)

    def turn_ended(self, turn: ChatTurn) -> None:
        view = self._views.get(id(turn))
        if view is not None:
            with self.conversation:
                self._close(turn, view, live=True)
        if self._sent and turn.delivered and self.pins is not None:
            self.pins.resolved(self._sent)
        self._sent = []
        self.progress.done()
        self.scroll.scroll_to(percent=1)
        self._set_busy(False)

    def conversation_closed(self) -> None:
        with self.conversation:
            ui.navigate.reload()

    def _draw(self, turn: ChatTurn) -> None:
        """A turn that already ended."""
        view = self._bubble(turn)
        for event in turn.events:
            view.show(event)
        self._close(turn, view, live=False)

    def _bubble(self, turn: ChatTurn) -> "_TurnView":
        if turn.session is not None and self._session is not None and turn.session != self._session:
            when = f" de {_when(turn.started_at)}" if turn.started_at is not None else ""
            ui.label(f"Conversa{when}").classes("mf-divider w-full").mark("session-divider")
        self._session = turn.session or self._session
        with ui.column().classes("mf-user gap-1"):
            ui.label(turn.request).classes("whitespace-pre-wrap")
            for note in turn.notes:
                ui.label(note).classes("text-xs mf-muted")
        view = _TurnView(turn)
        self._views[id(turn)] = view
        return view

    def _close(self, turn: ChatTurn, view: "_TurnView", live: bool) -> None:
        view.finish(turn.ok, turn.seconds)
        for problem in turn.problems:
            _error_row(problem)
        self._results(turn, view, live)
        if turn.version is not None:
            self._checkpoint(turn.version)

    def _pins_attachment(self, pins: list[Pin]) -> list[Path]:
        if not pins or self.pins is None:
            return []
        try:
            return [self.pins.attachment(pins)]
        except Exception:
            logger.exception("Writing the pinned comments failed")
            ui.notify("Não foi possível mandar ao agente os comentários na imagem.", type="negative")
            return []

    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        self.input.set_enabled(not busy)
        self.button.set_enabled(not busy)
        self._show_approve_bar()
        for listener in self._busy_listeners:
            listener(busy)

    def _show_approve_bar(self) -> None:
        cards = self.plan_cards
        try:
            waiting = cards is not None and cards.can_approve and status(self.lesson) == Status.PLAN
        except Exception:
            logger.debug("Reading the lesson's status failed", exc_info=True)
            return
        shown = waiting and not self.busy
        self.approve_bar.set_visibility(shown)
        if self._approve_in_chat is not None and not self._approve_in_chat.is_deleted:
            self._approve_in_chat.set_visibility(shown)

    async def _approve(self) -> None:
        if self.plan_cards is not None:
            await self.plan_cards.approve()

    def _show_attachments(self) -> None:
        assert self.pins is not None
        pending = self.pins.pending()
        self.attachments.clear()
        self.attachments.set_visibility(bool(pending))
        with self.attachments:
            for pin in pending:
                with ui.row().classes("mf-attach items-center no-wrap gap-1"):
                    ui.label(f"📍 {pin.number} · {pin.state}: {pin.text}").classes("ellipsis max-w-[16rem]").mark(
                        "pin-chip"
                    )
                    ui.button(icon="close", on_click=lambda pin=pin: self._remove_pin(pin)).props(
                        "flat round dense size=xs"
                    ).tooltip("Tirar este comentário")

    def _remove_pin(self, pin: Pin) -> None:
        if self.pins is not None:
            self.pins.remove(pin)

    def _welcome(self) -> None:
        """The example's own introduction, from the app: it spends no quota."""
        with ui.column().classes("mf-welcome gap-2").mark("example-welcome"):
            ui.label("Esta é a aula de exemplo").classes("font-semibold text-[14.5px]")
            ui.label(
                "Um herói voa a 0,6c em direção a um espelho na Terra e acompanha um raio de luz que vai, "
                "reflete e volta até ele. As animações já estão prontas na prévia ao lado."
            )
            ui.label(
                "Pergunte o que quiser sobre a aula ou peça mudanças: esta cópia é sua, "
                "e “Restaurar exemplo”, lá em cima, traz o original de volta."
            ).classes("mf-muted")
            with ui.row().classes("gap-2 flex-wrap"):
                for suggestion in SUGGESTIONS:
                    ui.button(suggestion, on_click=lambda text=suggestion: self._suggest(text)).props(
                        "outline no-caps rounded dense size=sm"
                    ).classes("px-2").mark("suggestion")

    def _suggest(self, text: str) -> None:
        self.input.value = text
        self.input.run_method("focus")

    def _results(self, turn: ChatTurn, view: "_TurnView", live: bool) -> None:
        """Cards for what the turn produced, each opening the tab that shows it. A turn drawn
        again, when the page opens, gets a small card: the plan and the images may have
        changed since it ran."""
        if PLAN_FILE in view.files or turn.plan_written:
            plan, _ = load_plan(self.lesson)
            if plan is not None and not all(state.scene == PLACEHOLDER_SCENE for state in plan.states):
                if live:
                    self._plan_card(plan)
                else:
                    _small_card("view_carousel", "Plano atualizado", "Ver plano →", lambda: self.open_tab("Plano"), "result-plan")
        if view.rendered:
            if live:
                self._preview_card()
            else:
                _small_card("movie", "Prévia atualizada", "Abrir →", lambda: self.open_tab("Prévia"), "result-preview")
        elif changed := sorted(view.files & set(CODE_FILES)):
            _small_card("code", "Código alterado: " + ", ".join(changed), "Ver código →", lambda: self.open_tab("Código"), "result-code")

    def _plan_card(self, plan: Plan) -> None:
        transitions = {transition.source: transition for transition in plan.transitions}
        with ui.column().classes("mf-plan").on("click", lambda: self.open_tab("Plano")).mark("result-plan"):
            states = len(plan.states)
            count = len(plan.transitions)
            ui.label(
                f"Plano · {states} estado{'' if states == 1 else 's'}, {count} transiç{'ão' if count == 1 else 'ões'}"
            ).classes("font-semibold text-[13.5px] pb-1")
            for state in plan.states:
                with ui.row().classes("w-full items-start no-wrap gap-2 py-1 border-t border-gray-200"):
                    ui.label(state.id).classes("mf-tag w-10")
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(state.title).classes("font-medium")
                        if state.visible:
                            ui.label(state.visible).classes("text-xs mf-muted")
                if (transition := transitions.get(state.id)) and transition.duration is not None:
                    ui.label(f"↓ {_seconds(transition.duration)} s").classes("text-xs mf-muted pl-12")
        # Outside the card's labels: the buttons only show while the plan waits for the teacher.
        with ui.row().classes("mf-plan-actions items-center no-wrap gap-2 w-full").mark("approve-in-chat") as actions:
            ui.button("Aprovar e animar", icon="check", on_click=self._approve).props(
                "unelevated no-caps rounded dense"
            ).classes("px-3").mark("approve-in-chat-button")
            ui.button("Ver e editar os cartões", on_click=lambda: self.open_tab("Plano")).props(
                "outline no-caps rounded dense"
            ).classes("px-3")
        if self._approve_in_chat is not None and not self._approve_in_chat.is_deleted:
            self._approve_in_chat.set_visibility(False)
        self._approve_in_chat = actions
        actions.set_visibility(False)
        if self.plan_cards is not None:
            # So the approval shows with the card, not on the cards' next look at the file.
            self.plan_cards.refresh()
        self._show_approve_bar()

    def _preview_card(self) -> None:
        plan, _ = load_plan(self.lesson)
        if plan is None:
            return
        served_at = serve_outputs(self.lesson)
        images = [url for state in plan.states if (url := latest_render(self.lesson, served_at, state.scene, "png"))]
        with ui.column().classes("mf-result").on("click", lambda: self.open_tab("Prévia")).mark("result-preview"):
            if images:
                with ui.row().classes("mf-strip no-wrap"):
                    for url in images[:6]:
                        ui.image(url).props("ratio=1.7778").classes("w-24 flex-none rounded border")
            with ui.row().classes("mf-foot items-center no-wrap gap-2"):
                ui.icon("movie", color="primary")
                ui.label("Prévia atualizada").classes("grow")
                ui.label("Abrir →").classes("text-xs mf-faint")

    def _checkpoint(self, version: Version) -> None:
        when = version.when.astimezone()
        with ui.row().classes("mf-checkpoint items-center no-wrap gap-2").mark("checkpoint"):
            ui.label(f"Versão salva {_at(when)}")
            ui.button("Restaurar", icon="restore", on_click=lambda: self._confirm_restore(version.id, when)).props(
                "flat dense no-caps size=sm color=grey-7"
            ).mark("restore")

    def _confirm_restore(self, version: str, when: datetime) -> None:
        if self.busy:
            ui.notify("Espere o agente terminar para voltar a uma versão.")
            return
        with ui.dialog() as dialog, ui.card().classes("w-[28rem] items-stretch gap-3"):
            ui.label(f"Voltar a aula para a versão {_at(when)}?").classes("text-lg")
            ui.label(
                "Os arquivos da aula ficam como estavam logo depois deste pedido. "
                "O que veio depois continua no histórico, e o agente fica sabendo da volta na próxima mensagem."
            ).classes("mf-muted")
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Restaurar", on_click=lambda: self._restore(dialog, version, when)).mark("confirm-restore")
        dialog.open()

    def _restore(self, dialog: ui.dialog, version: str, when: datetime) -> None:
        dialog.close()
        try:
            self.history.restore(version)
        except Exception:
            logger.exception("Restoring a version failed")
            ui.notify("Não foi possível voltar a esta versão.", type="negative")
            return
        with self.conversation:
            with ui.row().classes("mf-checkpoint items-center no-wrap gap-2"):
                ui.label(f"A aula voltou para a versão {_at(when)}")
        ui.notify(f"A aula voltou para a versão {_at(when)}.", type="positive")


# What the example's welcome suggests asking.
SUGGESTIONS = (
    "Explique o que acontece entre S1 e S2",
    "Mude a cor da luz para amarelo",
    "Deixe a transição S2 → S2b mais lenta",
)


class _TurnView:
    """One agent turn in the chat: its texts in order, with the steps between them grouped in
    a collapsible block, and what it changed, for the result cards."""

    def __init__(self, turn: ChatTurn) -> None:
        self.turn = turn
        self.block: ui.expansion | None = None
        self.blocks: list[tuple[ui.expansion, list[bool]]] = []
        self.files: set[str] = set()
        self.rendered = False

    def show(self, event: Event) -> None:
        match event:
            case AssistantText(text):
                self.block = None
                ui.markdown(text).classes("mf-agent w-full")
            case CommandStarted(_, command):
                with self._step(_doing(event) or "Rodando um comando"):
                    with _event_row("terminal", "grey-7"):
                        with ui.column().classes("gap-0 min-w-0"):
                            if step := _step(command) or _reading(event.reads):
                                ui.label(step)
                            ui.label(command).classes("font-mono mf-cmd")
            case CommandFinished(_, command):
                if event.ok:
                    icon, color, outcome = "check_circle", "positive", "Concluído"
                    self.rendered = self.rendered or bool(_RENDERS.search(command))
                else:
                    icon, color, outcome = "cancel", "negative", f"Falhou (código {event.exit_code})"
                with self._step(None, failed=not event.ok):
                    with _event_row(icon, color):
                        ui.label(f"{outcome}: {command}").classes("min-w-0 break-all")
            case FileChanged(path, change):
                self.files.add(path)
                with self._step(f"{_FILE_CHANGES[change]}: {path}"):
                    with _event_row("edit_document", "primary"):
                        ui.label(f"{_FILE_CHANGES[change]}: {path}")
            case ImageViewed(path):
                with self._step(f"Olhando a imagem {Path(path).name}"):
                    with _event_row("visibility", "primary"):
                        ui.label(f"Olhou a imagem {Path(path).name}").tooltip(path)
            case AgentError(message):
                self.block = None
                _error_row(f"Erro do agente: {message}")

    def _step(self, now: str | None, failed: bool = False) -> ui.expansion:
        """The current block of steps, started when a text came last, with its header on `now`."""
        if self.block is None:
            self.block = ui.expansion(icon="pending").classes("mf-activity").props("dense")
            self.blocks.append((self.block, []))
        steps = self.blocks[-1][1]
        steps.append(failed)
        if now is not None:
            _set_header(self.block, f"{now}…")
        return self.block

    def finish(self, ok: bool, seconds: float | None) -> None:
        """Labels each block with its number of steps and the turn's duration."""
        for block, steps in self.blocks:
            failed = any(steps)
            count = len(steps)
            header = f"{count} passo{'' if count == 1 else 's'}"
            if seconds is not None:
                header += f" · {_duration(round(seconds))}"
            _set_header(block, header)
            block.props(f"icon={'error_outline' if failed or not ok else 'check_circle_outline'}")
        self.block = None


def _small_card(icon: str, title: str, action: str, on_click: Callable[[], None], marker: str) -> None:
    with ui.row().classes("mf-result items-center no-wrap gap-2 px-3 py-2").on("click", on_click).mark(marker):
        ui.icon(icon, color="primary")
        ui.label(title).classes("grow")
        ui.label(action).classes("text-xs mf-faint")


def _doing(event: Event) -> str | None:
    """What the agent is doing, as the progress bar says it, after this event."""
    match event:
        case CommandStarted(_, command):
            return _step(command) or _reading(event.reads) or "Rodando um comando"
        case FileChanged(path, change):
            if change == "deleted":
                return f"Apagando {Path(path).name}"
            return f"Escrevendo {_FILES.get(Path(path).name, Path(path).name)}"
        case ImageViewed(path):
            return f"Olhando a imagem {Path(path).name}"
        case Working(label):
            return label
    return None


_START = "Enviando o pedido"
_THINKING = "Pensando"


def _reading(files: tuple[str, ...]) -> str | None:
    """"Lendo o plano e as cenas" for a command that only reads those files."""
    if not files:
        return None
    if files == (".",):
        return "Procurando arquivos da aula"
    names = list(dict.fromkeys(_FILES.get(Path(path).name, Path(path).name) for path in files))
    return "Lendo " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1])


def _checklist(checklist: Checklist | None) -> str:
    if checklist is None or not checklist.steps:
        return ""
    steps = checklist.steps
    done = sum(step.status == "completed" for step in steps)
    current = next((step.text for step in steps if step.status == "inProgress"), None)
    at = min(done + 1, len(steps))
    return f"Etapa {at} de {len(steps)}" + (f": {current}" if current else "")


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _at(when: datetime) -> str:
    """"às 14:32" today, "em 25/11 às 14:32" on another day."""
    if when.date() == datetime.now().astimezone().date():
        return f"às {when:%H:%M}"
    return f"em {when:%d/%m} às {when:%H:%M}"


def _when(moment: datetime) -> str:
    """The moment in the teacher's own time zone."""
    return moment.astimezone().strftime("%d/%m/%Y %H:%M")


def _set_header(block: ui.expansion, text: str) -> None:
    # Set directly, not through props(): a command or a path may hold quotes.
    block._props["label"] = text
    block.update()


def _duration(seconds: int) -> str:
    return f"{seconds} s" if seconds < 60 else f"{seconds // 60} min {seconds % 60:02d} s"


def _seconds(duration: float) -> str:
    """`4,7` for 4.7: the teacher reads a decimal comma."""
    return f"{duration:g}".replace(".", ",")


def _step(command: str) -> str | None:
    return next((step for pattern, step in _STEPS if pattern.search(command)), None)


def _event_row(icon: str, color: str) -> ui.row:
    """A compact row for a non-text event, starting with its icon."""
    with ui.row().classes("mf-event items-start gap-2 no-wrap w-full") as row:
        ui.icon(icon, color=color, size="16px").classes("mt-[2px]")
    return row


def _error_row(text: str) -> None:
    with _event_row("error", "negative"):
        ui.label(text).classes("text-negative text-base")
