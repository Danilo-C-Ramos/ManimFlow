"""The NiceGUI app: the lesson screen with its chat. Every UI string is in Portuguese."""

import logging
import re
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nicegui import app, ui

from manimflow import activity
from manimflow.agent import (
    Agent,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    ImageViewed,
    LoginFailed,
    Session,
)
from manimflow.code_tab import FILES as CODE_FILES
from manimflow.code_tab import CodeTab
from manimflow.dialogs import turma_url
from manimflow.equations import EquationsPanel
from manimflow.export_tab import ExportDialog
from manimflow.lessons import PLACEHOLDER_SCENE, Status, Turma, status
from manimflow.pins import Pin, Pins
from manimflow.plan import PLAN_FILE, Plan, load_plan
from manimflow.plan_cards import PlanCards
from manimflow.preview import PreviewPanel, latest_render, serve_outputs
from manimflow.render import cache_dir
from manimflow.sessions import SessionHistory
from manimflow.settings import SettingsDialog, model_switch
from manimflow.sidebar import Sidebar, drawer
from manimflow.theme import apply_theme, status_pill, turma_badge
from manimflow.versioning import OUTSIDE_EDITS, History

logger = logging.getLogger(__name__)

# The teacher's own edits since the agent's last turn, attached to the next message.
MANUAL_EDITS = "edicoes-manuais.diff"

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
) -> Callable[[], Awaitable[None]]:
    """Builds the page for one lesson; each browser tab gets its own agent session.

    `sidebar` draws the side column, such as the map of turmas and lessons.
    """

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
            session = await agent.start_session(lesson)
            controls.clear()
            body.clear()
            with body:
                pins = Pins(lesson)
                export = ExportDialog(lesson)
                with ui.splitter(value=Workspace.DEFAULT, limits=(22, 80)).classes("mf-split") as splitter:
                    with splitter.before:
                        with ui.column().classes("mf-chatcol") as chat_column:
                            with ui.row().classes("mf-chathead items-center no-wrap gap-1 w-full"):
                                ui.label("Conversa").classes("font-semibold grow")
                                SessionHistory(agent, lesson, current=session)
                                ui.button("Nova", icon="add", on_click=ui.navigate.reload).props(
                                    "flat dense no-caps"
                                ).tooltip("Começar uma conversa nova sobre esta aula")
                            chat = Chat(session, history, pins)
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
            if (first := _first_messages.pop(lesson.absolute(), None)) is not None:
                # Not awaited here: the page must show before the turn ends.
                ui.timer(0, lambda: chat.submit(first), once=True)

        def sign_in() -> None:
            controls.clear()
            body.clear()
            with body:
                SignIn(agent, on_signed_in=open_chat)

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


class SignIn:
    """Signs the teacher in with ChatGPT or an API key before the chat opens."""

    def __init__(self, agent: Agent, on_signed_in: Callable[[], Awaitable[None]]) -> None:
        self.agent = agent
        self.on_signed_in = on_signed_in
        with ui.card().classes("mx-auto mt-16 w-full max-w-md items-stretch gap-4"):
            ui.label("Entre para conversar com o agente").classes("text-lg")
            ui.label("Use a sua conta do ChatGPT Plus ou Pro, ou uma chave de API da OpenAI.").classes(
                "text-grey-7"
            )
            self.chatgpt = ui.button("Entrar com o ChatGPT", on_click=self.with_chatgpt)
            self.waiting = ui.label("Termine o login na aba do navegador que acabou de abrir.").classes(
                "text-grey-7"
            )
            self.waiting.set_visibility(False)
            ui.separator()
            self.key = (
                ui.input("Chave de API", password=True, password_toggle_button=True)
                .props("outlined dense")
                .mark("api-key")
            )
            self.key_button = ui.button("Usar chave de API", on_click=self.with_api_key).props("outline")
            self.error = ui.label().classes("text-negative")
            self.error.set_visibility(False)

    async def with_chatgpt(self) -> None:
        await self._login(None)

    async def with_api_key(self) -> None:
        await self._login(self.key.value or "")

    async def _login(self, api_key: str | None) -> None:
        self._set_busy(True, waiting_for_browser=api_key is None)
        self.error.set_visibility(False)
        try:
            await self.agent.login(api_key)
        except LoginFailed as failure:
            self._fail(str(failure))
            return
        except Exception:
            logger.exception("Login failed")
            self._fail("Não foi possível entrar agora. Tente de novo.")
            return
        await self.on_signed_in()

    def _fail(self, message: str) -> None:
        self._set_busy(False)
        self.error.set_text(message)
        self.error.set_visibility(True)

    def _set_busy(self, busy: bool, waiting_for_browser: bool = False) -> None:
        self.chatgpt.set_enabled(not busy)
        self.key_button.set_enabled(not busy)
        self.waiting.set_visibility(busy and waiting_for_browser)


class Chat:
    def __init__(self, session: Session, history: History, pins: Pins | None = None) -> None:
        self.session = session
        self.history = history
        self.lesson = session.lesson
        self.pins = pins
        # Set once the workspace exists: the result cards open its tabs, the bar approves the plan.
        self.workspace: Workspace | None = None
        self.plan_cards: PlanCards | None = None
        # Told when a turn starts and ends, for whatever must wait for the agent.
        self._busy_listeners: list[Callable[[bool], None]] = []
        self._busy = False
        with ui.scroll_area().classes("mf-thread w-full") as self.scroll:
            self.conversation = ui.column().classes("mf-conversation").mark("conversation")
        with ui.column().classes("mf-composer-wrap"):
            with ui.row().classes("items-center gap-2 mf-muted text-[13px] px-2") as self.working:
                ui.spinner(size="sm")
                ui.label("O agente está trabalhando…")
            self.working.set_visibility(False)
            with ui.column().classes("mf-composer"):
                with ui.row().classes("mf-approvebar items-center no-wrap gap-2").mark("approve-bar") as self.approve_bar:
                    ui.icon("hourglass_top", size="18px")
                    ui.label("O plano está esperando você.").classes("grow")
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
        ui.timer(1.0, self._show_approve_bar)

    def on_busy(self, listener: Callable[[bool], None]) -> None:
        """Calls `listener` with True when a turn starts, before anything is committed,
        and with False when it ends."""
        self._busy_listeners.append(listener)

    @property
    def busy(self) -> bool:
        """Whether the agent is still working on the last message."""
        return self._busy

    def open_tab(self, tab: str) -> None:
        if self.workspace is not None:
            self.workspace.show(tab)

    async def send(self) -> None:
        text = (self.input.value or "").strip()
        if not text or self.busy:
            return
        self.input.value = ""
        await self.submit(text)

    async def submit(self, text: str, summary: str | None = None) -> bool:
        """Sends `text` as the teacher's message and shows the agent's turn as it streams.

        The turn's version is named after `summary` when given, else after `text`.
        False when the turn failed.
        """
        self._set_busy(True)
        pins = self.pins.pending() if self.pins is not None else []
        with self.conversation:
            with ui.column().classes("mf-user gap-1"):
                ui.label(text).classes("whitespace-pre-wrap")
                for pin in pins:
                    ui.label(f"📍 {pin.number} · {pin.state}: {pin.text}").classes("text-xs mf-muted")
        # So the agent's commit holds only what the agent changed.
        self._save_version(lambda: self.history.commit_manual_edit(OUTSIDE_EDITS))
        attachments = self._manual_edits() + self._pins_attachment(pins)
        turn = _Turn(self.conversation)
        ok = delivered = True
        try:
            async for event in self.session.send(text, attachments):
                ok = ok and not isinstance(event, AgentError)
                delivered = delivered and not (isinstance(event, AgentError) and not event.delivered)
                with self.conversation:
                    turn.show(event)
                self.scroll.scroll_to(percent=1)
        except Exception:
            # The engine's own message is in English and meant for developers.
            logger.exception("Agent turn failed")
            with self.conversation:
                _error_row("O agente parou por um erro inesperado.")
            ok = False
        finally:
            turn.finish(ok)
            # Even a failed turn may have changed files, and they must not be lost. A message
            # the agent never got leaves the manual edits and the pins for the next one.
            version = None
            if delivered:
                version = self._save_version(lambda: self.history.commit_agent_turn(summary or text))
                if self.pins is not None and pins:
                    self.pins.resolved(pins)
            with self.conversation:
                self._results(turn)
                if version is not None:
                    self._checkpoint(version)
            self.scroll.scroll_to(percent=1)
            self._set_busy(False)
        return ok

    def _manual_edits(self) -> list[Path]:
        """The diff of the teacher's edits since the agent's last turn, as an attachment
        file, so the agent builds on them; none when there are no such edits."""
        try:
            diff = self.history.manual_changes()
            if not diff:
                return []
            attachment = cache_dir(self.session.lesson) / MANUAL_EDITS
            # As is: the diff holds each file's own line endings.
            attachment.write_text(diff, encoding="utf-8", newline="")
        except Exception:
            # The message still goes: the teacher can tell the agent what they changed.
            logger.exception("Manual changes failed")
            with self.conversation:
                _error_row("Não foi possível mandar ao agente as suas edições no código.")
            return []
        return [attachment]

    def _pins_attachment(self, pins: list[Pin]) -> list[Path]:
        if not pins or self.pins is None:
            return []
        try:
            return [self.pins.attachment(pins)]
        except Exception:
            logger.exception("Writing the pinned comments failed")
            with self.conversation:
                _error_row("Não foi possível mandar ao agente os comentários na imagem.")
            return []

    def _save_version(self, commit: Callable[[], str | None]) -> str | None:
        """Runs `commit` and returns the new version's id, telling the teacher when the
        version couldn't be saved; the chat goes on either way."""
        try:
            return commit()
        except Exception:
            logger.exception("Commit failed")
            with self.conversation:
                _error_row("Não foi possível salvar uma versão desta mudança.")
            return None

    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            activity.start(self.lesson)
        else:
            activity.stop(self.lesson)
        self.input.set_enabled(not busy)
        self.button.set_enabled(not busy)
        self.working.set_visibility(busy)
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
        self.approve_bar.set_visibility(waiting and not self.busy)

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

    def _results(self, turn: "_Turn") -> None:
        """Cards for what the turn produced, each opening the tab that shows it."""
        if PLAN_FILE in turn.files:
            plan, _ = load_plan(self.lesson)
            if plan is not None and not all(state.scene == PLACEHOLDER_SCENE for state in plan.states):
                self._plan_card(plan)
        if turn.rendered:
            self._preview_card()
        elif changed := sorted(turn.files & set(CODE_FILES)):
            with ui.row().classes("mf-result items-center no-wrap gap-2 px-3 py-2").on(
                "click", lambda: self.open_tab("Código")
            ).mark("result-code"):
                ui.icon("code", color="primary")
                ui.label("Código alterado: " + ", ".join(changed)).classes("grow")
                ui.label("Ver código →").classes("text-xs mf-faint")

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

    def _checkpoint(self, version: str) -> None:
        when = datetime.now()
        with ui.row().classes("mf-checkpoint items-center no-wrap gap-2").mark("checkpoint"):
            ui.label(f"Versão salva às {when:%H:%M}")
            ui.button("Restaurar", icon="restore", on_click=lambda: self._confirm_restore(version, when)).props(
                "flat dense no-caps size=sm color=grey-7"
            ).mark("restore")

    def _confirm_restore(self, version: str, when: datetime) -> None:
        if self.busy:
            ui.notify("Espere o agente terminar para voltar a uma versão.")
            return
        with ui.dialog() as dialog, ui.card().classes("w-[28rem] items-stretch gap-3"):
            ui.label(f"Voltar a aula para a versão das {when:%H:%M}?").classes("text-lg")
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
                ui.label(f"A aula voltou para a versão das {when:%H:%M}")
        ui.notify(f"A aula voltou para a versão das {when:%H:%M}.", type="positive")


class _Turn:
    """One agent turn in the chat: its texts in order, with the steps between them grouped in
    a collapsible block, and what it changed, for the result cards."""

    def __init__(self, conversation: ui.column) -> None:
        self.conversation = conversation
        self.started = time.monotonic()
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
                with self._step(_step(command) or "Rodando um comando"):
                    with _event_row("terminal", "grey-7"):
                        with ui.column().classes("gap-0 min-w-0"):
                            if step := _step(command):
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

    def finish(self, ok: bool) -> None:
        """Labels each block with its number of steps and the turn's duration."""
        seconds = round(time.monotonic() - self.started)
        for block, steps in self.blocks:
            failed = any(steps)
            count = len(steps)
            _set_header(block, f"{count} passo{'' if count == 1 else 's'} · {_duration(seconds)}")
            block.props(f"icon={'error_outline' if failed or not ok else 'check_circle_outline'}")
        self.block = None


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
