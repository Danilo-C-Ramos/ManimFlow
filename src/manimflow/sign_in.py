"""Signing in with ChatGPT or an OpenAI API key: on the lesson screen before the chat opens,
and in the settings when nobody is signed in. Every UI string is in Portuguese."""

import logging
from collections.abc import Awaitable, Callable

from nicegui import ui

from manimflow.agent import Agent, LoginFailed

logger = logging.getLogger(__name__)


class SignIn:
    """Signs the teacher in, then calls `on_signed_in`. `card` draws it as the page's own
    card; without it, it fits inside another, as the settings dialog."""

    def __init__(self, agent: Agent, on_signed_in: Callable[[], Awaitable[None]], card: bool = True) -> None:
        self.agent = agent
        self.on_signed_in = on_signed_in
        frame: ui.element
        if card:
            frame = ui.card().classes("mx-auto mt-16 w-full max-w-md items-stretch gap-4")
        else:
            frame = ui.column().classes("w-full items-stretch gap-3")
        with frame.mark("sign-in"):
            ui.label("Entre para conversar com o agente").classes("text-lg" if card else "font-medium")
            ui.label("Use a sua conta do ChatGPT, de qualquer plano, ou uma chave de API da OpenAI.").classes(
                "text-grey-7"
            )
            self.chatgpt = ui.button("Entrar com o ChatGPT", on_click=self.with_chatgpt).mark("sign-in-chatgpt")
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
