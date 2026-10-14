"""A scripted agent that replays a fixed scenario, for tests and the demo mode.

A scenario is a list of turns, one per message the teacher sends. A turn is a
list of steps: events to emit, file edits to apply to the lesson folder, or an
exception to raise, as a broken engine would.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from manimflow.agent import (
    Account,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    LoginFailed,
    ModelSettings,
)


@dataclass(frozen=True)
class EditFile:
    """Writes `content` to `path`, relative to the lesson folder, and reports it."""

    path: str
    content: str


Step = Event | EditFile | Exception
Scenario = list[list[Step]]

ACCOUNT = Account(logged_in=True, method="chatgpt", email="professora@example.com")
MODEL_SETTINGS = ModelSettings(model="gpt-5-codex", effort="medium")


class ScriptedAgent:
    def __init__(
        self,
        scenario: Scenario,
        delay: float = 0.0,
        logged_in: bool = True,
        login_failure: str | None = None,
    ) -> None:
        self.scenario = scenario
        # Seconds between steps, so the demo streams at a visible pace.
        self.delay = delay
        self._account = ACCOUNT if logged_in else Account(logged_in=False)
        # When set, every login attempt fails with this message.
        self._login_failure = login_failure

    async def start_session(self, lesson: Path) -> "ScriptedSession":
        return ScriptedSession(lesson, iter(self.scenario), self.delay)

    async def account(self) -> Account:
        return self._account

    async def login(self, api_key: str | None = None) -> Account:
        if self._login_failure is not None:
            raise LoginFailed(self._login_failure)
        self._account = ACCOUNT if api_key is None else Account(logged_in=True, method="api_key")
        return self._account

    async def model_settings(self) -> ModelSettings:
        return MODEL_SETTINGS

    async def set_model_settings(self, settings: ModelSettings) -> None:
        pass

    async def close(self) -> None:
        pass


class ScriptedSession:
    def __init__(self, lesson: Path, turns: Iterator[list[Step]], delay: float) -> None:
        self.lesson = lesson
        self._turns = turns
        self._delay = delay

    async def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        turn = next(self._turns, None)
        if turn is None:
            yield AgentError("O roteiro do agente de demonstração acabou.")
            return
        for step in turn:
            await asyncio.sleep(self._delay)
            if isinstance(step, Exception):
                raise step
            if isinstance(step, EditFile):
                yield self._edit(step)
            else:
                yield step

    def _edit(self, edit: EditFile) -> FileChanged:
        target = (self.lesson / edit.path).resolve()
        if not target.is_relative_to(self.lesson.resolve()):
            raise ValueError(f"Scenario edits {edit.path!r}, outside the lesson folder")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(edit.content, encoding="utf-8")
        return FileChanged(edit.path, "modified" if existed else "added")


# The demo mode's scenario, played on a copy of the bundled example.
DEMO: Scenario = [
    [
        AssistantText("Entendi. Vou deixar um rascunho da mudança e conferir a cena."),
        EditFile("rascunho.md", "# Rascunho\n\nTrocar a cor da luz para amarelo.\n"),
        CommandStarted("1", "manimflow preview . S2_Reflexao"),
        CommandFinished("1", "manimflow preview . S2_Reflexao", 0),
        AssistantText("Renderizei a prévia de S2 e conferi o último quadro."),
    ],
    [
        AssistantText("Vou validar o plano antes de seguir."),
        CommandStarted("2", "manimflow plan validate ."),
        CommandFinished("2", "manimflow plan validate .", 1),
        AgentError("A validação do plano falhou. Esta é só uma demonstração de erro."),
    ],
]
