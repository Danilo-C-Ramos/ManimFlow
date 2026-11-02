"""The NiceGUI app: the lesson screen with its chat. Every UI string is in Portuguese."""

import logging
import re
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path

from nicegui import app, ui

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
from manimflow.code_tab import CodeTab
from manimflow.equations import EquationsPanel
from manimflow.export_tab import ExportPanel
from manimflow.plan_cards import PlanCards
from manimflow.preview import PreviewPanel
from manimflow.render import cache_dir
from manimflow.sessions import SessionHistory
from manimflow.settings import SettingsDialog, model_switch
from manimflow.versioning import OUTSIDE_EDITS, History

logger = logging.getLogger(__name__)

# The teacher's own edits since the agent's last turn, attached to the next message.
MANUAL_EDITS = "edicoes-manuais.diff"

_FILE_CHANGES = {"added": "Arquivo criado", "modified": "Arquivo alterado", "deleted": "Arquivo apagado"}

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


def lesson_page(agent: Agent, lesson: Path) -> Callable[[], Awaitable[None]]:
    """Builds the page for one lesson; each browser tab gets its own agent session."""

    async def page() -> None:
        ui.page_title(f"{lesson.name} · ManimFlow")
        history = History.open(lesson)
        with ui.header().classes("items-center justify-between"):
            ui.button("Minhas aulas", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props("flat color=white")
            ui.label(lesson.name).classes("text-lg")
            controls = ui.row().classes("ml-auto items-center")
        body = ui.column().classes("w-full")

        async def open_chat() -> None:
            session = await agent.start_session(lesson)
            controls.clear()
            with controls:
                SessionHistory(agent, lesson, current=session)
                SettingsDialog(agent, await model_switch(agent), on_signed_out=sign_in)
            body.clear()
            with body, ui.row().classes("w-full no-wrap items-start gap-6"):
                with ui.column().classes("w-1/2"):
                    chat = Chat(session, history)
                with ui.column().classes("w-1/2 gap-0"):
                    with ui.tabs().props("dense align=left") as tabs:
                        ui.tab("Prévia")
                        ui.tab("Código")
                        ui.tab("Equações")
                        ui.tab("Exportar")
                    with ui.tab_panels(tabs, value="Prévia").classes("w-full"):
                        with ui.tab_panel("Prévia").classes("p-0"):
                            with ui.scroll_area().classes("h-[calc(100vh-9rem)]"):
                                PlanCards(lesson, chat)
                                PreviewPanel(lesson)
                        with ui.tab_panel("Código").classes("p-0"):
                            chat.on_busy = CodeTab(lesson, history).set_agent_working
                        with ui.tab_panel("Equações").classes("p-0"):
                            with ui.scroll_area().classes("h-[calc(100vh-9rem)]"):
                                EquationsPanel(lesson)
                        with ui.tab_panel("Exportar"):
                            ExportPanel(lesson)

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
    def __init__(self, session: Session, history: History) -> None:
        self.session = session
        self.history = history
        # Told when a turn starts and ends, for whatever must wait for the agent.
        self.on_busy: Callable[[bool], None] = lambda busy: None
        with ui.column().classes("w-full max-w-3xl mx-auto h-[calc(100vh-6rem)]"):
            with ui.scroll_area().classes("grow w-full") as self.scroll:
                self.conversation = ui.column().classes("w-full gap-2").mark("conversation")
            with ui.row().classes("items-center gap-2 text-grey-7") as self.working:
                ui.spinner(size="sm")
                ui.label("O agente está trabalhando…")
            self.working.set_visibility(False)
            with ui.row().classes("w-full items-center no-wrap"):
                self.input = (
                    ui.input(placeholder="Escreva para o agente")
                    .props("outlined dense")
                    .classes("grow")
                    .mark("message")
                )
                self.input.on("keydown.enter", self.send)
                self.button = ui.button("Enviar", on_click=self.send)

    @property
    def busy(self) -> bool:
        """Whether the agent is still working on the last message."""
        return not self.button.enabled

    async def send(self) -> None:
        text = (self.input.value or "").strip()
        if not text or self.busy:
            return
        self.input.value = ""
        await self.submit(text)

    async def submit(self, text: str) -> bool:
        """Sends `text` as the teacher's message and shows the agent's turn as it streams.

        False when the turn failed.
        """
        self._set_busy(True)
        with self.conversation, ui.chat_message(name="Você", sent=True):
            ui.label(text).classes("whitespace-pre-wrap")
        # So the agent's commit holds only what the agent changed.
        self._save_version(lambda: self.history.commit_manual_edit(OUTSIDE_EDITS))
        ok = True
        try:
            async for event in self.session.send(text, self._manual_edits()):
                ok = ok and not isinstance(event, AgentError)
                with self.conversation:
                    self._show(event)
                self.scroll.scroll_to(percent=1)
        except Exception:
            # The engine's own message is in English and meant for developers.
            logger.exception("Agent turn failed")
            with self.conversation:
                _error_row("O agente parou por um erro inesperado.")
            ok = False
        finally:
            # Even a failed turn may have changed files, and they must not be lost.
            self._save_version(lambda: self.history.commit_agent_turn(text))
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

    def _save_version(self, commit: Callable[[], object]) -> None:
        """Runs `commit`, telling the teacher when the version couldn't be saved; the
        chat goes on either way."""
        try:
            commit()
        except Exception:
            logger.exception("Commit failed")
            with self.conversation:
                _error_row("Não foi possível salvar uma versão desta mudança.")

    def _set_busy(self, busy: bool) -> None:
        self.input.set_enabled(not busy)
        self.button.set_enabled(not busy)
        self.working.set_visibility(busy)
        self.on_busy(busy)

    def _show(self, event: Event) -> None:
        match event:
            case AssistantText(text):
                with ui.chat_message(name="Agente"):
                    ui.markdown(text)
            case CommandStarted(_, command):
                with _event_row("terminal", "grey-7"):
                    if step := _step(command):
                        ui.label(step)
                    ui.label(command).classes("font-mono")
            case CommandFinished(_, command):
                if event.ok:
                    icon, color, outcome = "check_circle", "positive", "Concluído"
                else:
                    icon, color, outcome = "cancel", "negative", f"Falhou (código {event.exit_code})"
                with _event_row(icon, color):
                    ui.label(f"{outcome}: {command}")
            case FileChanged(path, change):
                with _event_row("edit_document", "primary"):
                    ui.label(f"{_FILE_CHANGES[change]}: {path}")
            case ImageViewed(path):
                with _event_row("visibility", "primary"):
                    ui.label(f"Olhou a imagem {Path(path).name}").tooltip(path)
            case AgentError(message):
                _error_row(f"Erro do agente: {message}")


def _step(command: str) -> str | None:
    return next((step for pattern, step in _STEPS if pattern.search(command)), None)


def _event_row(icon: str, color: str) -> ui.row:
    """A compact row for a non-text event, starting with its icon."""
    with ui.row().classes("items-center gap-2 text-sm no-wrap") as row:
        ui.icon(icon, color=color)
    return row


def _error_row(text: str) -> None:
    with _event_row("error", "negative"):
        ui.label(text).classes("text-negative text-base")
