"""A scripted agent that replays a fixed scenario, for tests and the demo mode.

A scenario is a list of turns, one per message the teacher sends. A turn is a
list of steps: events to emit, file edits to apply to the lesson folder, files
a command produces (such as renders), or an exception to raise, as a broken
engine would.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from manimflow.agent import (
    Account,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    ImageViewed,
    LoginFailed,
    Message,
    ModelOption,
    ModelSettings,
    PastSession,
    QuotaWindow,
)
from manimflow.model_presets import DEFAULT


@dataclass(frozen=True)
class EditFile:
    """Writes `content` to `path`, relative to the lesson folder, and reports it."""

    path: str
    content: str


@dataclass(frozen=True)
class Produce:
    """Writes `content` to `path`, relative to the lesson folder, without reporting it.

    The way a command the agent runs writes its outputs: `manimflow preview`
    writes images and videos that never show up as file changes.
    """

    path: str
    content: bytes


@dataclass(frozen=True)
class Received:
    """A message the teacher sent, with each attachment's name and content as sent."""

    text: str
    attachments: dict[str, str]


Step = Event | EditFile | Produce | Exception
Scenario = list[list[Step]]

ACCOUNT = Account(logged_in=True, method="chatgpt", email="professora@example.com")
MODELS = [
    ModelOption("gpt-6.1-sol", "GPT-6.1-Sol", ("low", "medium", "high", "xhigh"), "low"),
    ModelOption("gpt-6-luna", "GPT-6-Luna", ("low", "medium", "high"), "medium"),
]


_SOON = datetime.now(UTC) + timedelta(hours=2)
QUOTA = [QuotaWindow(5, 300, _SOON), QuotaWindow(80, 10080, _SOON + timedelta(days=3))]


class ScriptedAgent:
    def __init__(
        self,
        scenario: Scenario,
        delay: float = 0.0,
        logged_in: bool = True,
        login_failure: str | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.scenario = scenario
        # Seconds between steps, so the demo streams at a visible pace.
        self.delay = delay
        self._account = ACCOUNT if logged_in else Account(logged_in=False)
        # When set, every login attempt fails with this message.
        self._login_failure = login_failure
        self._settings = DEFAULT
        # The model settings each turn ran with, in order, across sessions.
        self.turn_settings: list[ModelSettings] = []
        # When each session started; the fake keeps its sessions in memory only.
        self._clock = clock
        self._sessions: list[ScriptedSession] = []
        # Every message sent to any of its sessions, with its attachments, in order.
        self.received: list[Received] = []

    async def start_session(self, lesson: Path) -> "ScriptedSession":
        """A new session, which plays the scenario from its first turn."""
        session = ScriptedSession(
            str(len(self._sessions) + 1),
            lesson,
            iter(self.scenario),
            self.delay,
            self._clock(),
            self._start_turn,
            self.received,
        )
        self._sessions.append(session)
        return session

    def _start_turn(self) -> None:
        self.turn_settings.append(self._settings)

    async def past_sessions(self, lesson: Path) -> list[PastSession]:
        return [
            PastSession(session.id, session.started_at, session.messages[0].text)
            for session in reversed(self._sessions)
            if session.lesson.resolve() == lesson.resolve() and session.messages
        ]

    async def session_messages(self, session_id: str) -> list[Message]:
        (session,) = [session for session in self._sessions if session.id == session_id]
        return list(session.messages)

    async def account(self) -> Account:
        return self._account

    async def login(self, api_key: str | None = None) -> Account:
        if self._login_failure is not None:
            raise LoginFailed(self._login_failure)
        self._account = ACCOUNT if api_key is None else Account(logged_in=True, method="api_key")
        return self._account

    async def logout(self) -> None:
        self._account = Account(logged_in=False)

    async def quota(self) -> list[QuotaWindow] | None:
        return QUOTA if self._account.method == "chatgpt" else None

    async def models(self) -> list[ModelOption]:
        return MODELS

    async def model_settings(self) -> ModelSettings:
        return self._settings

    async def set_model_settings(self, settings: ModelSettings) -> None:
        self._settings = settings

    async def close(self) -> None:
        pass


class ScriptedSession:
    def __init__(
        self,
        id: str,
        lesson: Path,
        turns: Iterator[list[Step]],
        delay: float,
        started_at: datetime,
        on_turn: Callable[[], None],
        received: list[Received],
    ) -> None:
        self.id = id
        self.lesson = lesson
        self.started_at = started_at
        self.messages: list[Message] = []
        self._turns = turns
        self._delay = delay
        self._on_turn = on_turn
        self._received = received

    async def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        self._on_turn()
        self.messages.append(Message("teacher", text))
        # Read now, as the Codex adapter does, since the files may change after the message.
        self._received.append(Received(text, {path.name: path.read_text(encoding="utf-8") for path in attachments}))
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
            elif isinstance(step, Produce):
                self._target(step.path).write_bytes(step.content)
            else:
                if isinstance(step, AssistantText):
                    self.messages.append(Message("agent", step.text))
                yield step

    def _edit(self, edit: EditFile) -> FileChanged:
        target = self._target(edit.path)
        existed = target.exists()
        target.write_text(edit.content, encoding="utf-8")
        return FileChanged(edit.path, "modified" if existed else "added")

    def _target(self, path: str) -> Path:
        """The file at `path` inside the lesson, with its folder created."""
        target = (self.lesson / path).resolve()
        if not target.is_relative_to(self.lesson.resolve()):
            raise ValueError(f"Scenario writes {path!r}, outside the lesson folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


# The demo mode's scenario, played on a copy of the bundled example.
DEMO: Scenario = [
    [
        AssistantText("Entendi. Vou deixar um rascunho da mudança e conferir a cena."),
        EditFile("rascunho.md", "# Rascunho\n\nTrocar a cor da luz para amarelo.\n"),
        CommandStarted("1", "manimflow preview . S2_Reflexao"),
        CommandFinished("1", "manimflow preview . S2_Reflexao", 0),
        ImageViewed("saida/previa/png/S2_Reflexao.png"),
        AssistantText("Renderizei a prévia de S2 e conferi o último quadro."),
    ],
    [
        AssistantText("Vou validar o plano antes de seguir."),
        CommandStarted("2", "manimflow plan validate ."),
        CommandFinished("2", "manimflow plan validate .", 1),
        AgentError("A validação do plano falhou. Esta é só uma demonstração de erro."),
    ],
]
