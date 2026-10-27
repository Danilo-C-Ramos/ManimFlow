"""The lesson's past sessions, read-only, so the teacher can recall why something was done.

Every opening of a lesson starts a new session; `CONTEXTO.md` carries the
memory between them, and the old conversations are only there to be read.
"""

import logging
from datetime import datetime
from pathlib import Path

from nicegui import ui

from manimflow.agent import Agent, PastSession, Session

logger = logging.getLogger(__name__)


class SessionHistory:
    """A header button that opens the lesson's earlier sessions, apart from the current one."""

    def __init__(self, agent: Agent, lesson: Path, current: Session) -> None:
        self.agent = agent
        self.lesson = lesson
        self.current = current
        with ui.dialog() as self.dialog, ui.card().classes("w-full max-w-2xl"):
            self.content = ui.column().classes("w-full gap-2")
        ui.button("Conversas anteriores", icon="history", on_click=self.show_list).props("flat color=white")

    async def show_list(self) -> None:
        self.dialog.open()
        try:
            sessions = [past for past in await self.agent.past_sessions(self.lesson) if past.id != self.current.id]
        except Exception:
            logger.exception("Listing past sessions failed")
            self._show_problem()
            return
        self.content.clear()
        with self.content:
            ui.label("Conversas anteriores").classes("text-lg")
            with ui.column().classes("w-full gap-1").mark("past-sessions"):
                if not sessions:
                    ui.label("Esta aula ainda não tem conversas anteriores.").classes("text-grey-7")
                for past in sessions:
                    self._entry(past)

    def _entry(self, past: PastSession) -> None:
        async def open_session() -> None:
            await self.show_session(past)

        with ui.item(on_click=open_session).classes("w-full rounded-borders").mark("past-session"):
            with ui.column().classes("gap-0"):
                ui.label(_when(past.started_at)).classes("text-sm text-grey-7")
                ui.label(past.first_request).classes("line-clamp-2")

    async def show_session(self, past: PastSession) -> None:
        try:
            messages = await self.agent.session_messages(past.id)
        except Exception:
            logger.exception("Reading a past session failed")
            self._show_problem()
            return
        self.content.clear()
        with self.content:
            with ui.row().classes("items-center gap-2"):
                ui.button("Voltar", icon="arrow_back", on_click=self.show_list).props("flat")
                ui.label(f"Conversa de {_when(past.started_at)}").classes("text-lg")
            with ui.scroll_area().classes("w-full h-[60vh]"):
                with ui.column().classes("w-full gap-2").mark("past-messages"):
                    for message in messages:
                        if message.author == "teacher":
                            with ui.chat_message(name="Você", sent=True):
                                ui.label(message.text)
                        else:
                            with ui.chat_message(name="Agente"):
                                ui.markdown(message.text)

    def _show_problem(self) -> None:
        self.content.clear()
        with self.content:
            ui.label("Não foi possível abrir as conversas anteriores agora. Tente de novo.").classes("text-negative")


def _when(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y %H:%M")
