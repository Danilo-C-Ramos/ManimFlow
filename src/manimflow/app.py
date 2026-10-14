"""The NiceGUI app: the lesson screen with its chat. Every UI string is in Portuguese."""

import logging
import shutil
import socket
import tempfile
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path

from nicegui import ui

from manimflow.agent import (
    Agent,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    Session,
)

logger = logging.getLogger(__name__)

EXAMPLES = Path(str(files("manimflow"))) / "exemplos"
EXAMPLE_NAME = "Relatividade - herói e espelho"

_FILE_CHANGES = {"added": "Arquivo criado", "modified": "Arquivo alterado", "deleted": "Arquivo apagado"}


def serve(agent: Agent, lesson: Path) -> None:
    """Serves the lesson screen on localhost only and opens it in the default browser."""
    ui.run(
        lesson_page(agent, lesson),
        host="127.0.0.1",
        port=_free_port(),
        show=True,
        title="ManimFlow",
        language="pt-BR",
        reload=False,
    )


def example_copy() -> Path:
    """Copies the bundled example to a temporary folder, so the original stays pristine."""
    lessons = Path(tempfile.mkdtemp(prefix="manimflow-"))
    shutil.copy(EXAMPLES / "perfil.md", lessons)
    return Path(shutil.copytree(EXAMPLES / "relatividade", lessons / EXAMPLE_NAME))


def _free_port() -> int:
    # The teacher may already run Jupyter or another local server on the usual ports.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def lesson_page(agent: Agent, lesson: Path) -> Callable[[], Awaitable[None]]:
    """Builds the page for one lesson; each browser tab gets its own agent session."""

    async def page() -> None:
        ui.page_title(f"{lesson.name} · ManimFlow")
        with ui.header().classes("items-center"):
            ui.label(lesson.name).classes("text-lg")
        Chat(await agent.start_session(lesson))

    return page


class Chat:
    def __init__(self, session: Session) -> None:
        self.session = session
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

    async def send(self) -> None:
        text = (self.input.value or "").strip()
        if not text or not self.button.enabled:
            return
        self.input.value = ""
        self._set_busy(True)
        with self.conversation, ui.chat_message(name="Você", sent=True):
            ui.label(text)
        try:
            async for event in self.session.send(text):
                with self.conversation:
                    self._show(event)
                self.scroll.scroll_to(percent=1)
        except Exception:
            # The engine's own message is in English and meant for developers.
            logger.exception("Agent turn failed")
            with self.conversation:
                _error_row("O agente parou por um erro inesperado.")
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.input.set_enabled(not busy)
        self.button.set_enabled(not busy)
        self.working.set_visibility(busy)

    def _show(self, event: Event) -> None:
        match event:
            case AssistantText(text):
                with ui.chat_message(name="Agente"):
                    ui.markdown(text)
            case CommandStarted(_, command):
                with _event_row("terminal", "grey-7"):
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
            case AgentError(message):
                _error_row(f"Erro do agente: {message}")


def _event_row(icon: str, color: str) -> ui.row:
    """A compact row for a non-text event, starting with its icon."""
    with ui.row().classes("items-center gap-2 text-sm no-wrap") as row:
        ui.icon(icon, color=color)
    return row


def _error_row(text: str) -> None:
    with _event_row("error", "negative"):
        ui.label(text).classes("text-negative text-base")
