"""A scripted agent that replays a fixed scenario, for tests and the demo mode.

A scenario is a list of turns, one per message the teacher sends. A turn is a
list of steps: events to emit, file edits to apply to the lesson folder, files
a command produces (such as renders), or an exception to raise, as a broken
engine would.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, replace
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
    ModelOption,
    ModelSettings,
    PastTurn,
    QuotaWindow,
    Working,
)
from manimflow.model_presets import QUICK, choose_model, presets


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
    """A message the teacher sent, with each attachment's name and content as sent, and
    the format its answer was asked in."""

    text: str
    attachments: dict[str, str]
    output_schema: dict | None = None


Step = Event | EditFile | Produce | Exception
Scenario = list[list[Step]]

ACCOUNT = Account(logged_in=True, method="chatgpt", email="professora@example.com", plan="plus")
MODELS = [
    ModelOption("gpt-6.2-sol", "GPT-6.2-Sol", ("low", "medium", "high", "xhigh"), "low", default=True),
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
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        plan: str = "plus",
    ) -> None:
        self.scenario = scenario
        # Seconds between steps, so the demo streams at a visible pace.
        self.delay = delay
        # The ChatGPT plan a ChatGPT login signs in with.
        self._chatgpt = replace(ACCOUNT, plan=plan)
        self._account = self._chatgpt if logged_in else Account(logged_in=False)
        # When set, every login attempt fails with this message.
        self._login_failure = login_failure
        # The switch's position and a pick in "Avançado", kept as Codex keeps them.
        self._preset = QUICK
        self._settings: ModelSettings | None = None
        # The model settings each turn ran with, in order, across sessions.
        self.turn_settings: list[ModelSettings] = []
        # When each turn started; the fake keeps its conversations in memory only.
        self._clock = clock
        self._sessions: dict[Path, ScriptedSession] = {}
        # Every message sent to any lesson, with its attachments, in order.
        self.received: list[Received] = []
        # The lessons whose conversations were put away, in order.
        self.archived: list[Path] = []

    async def session(self, lesson: Path) -> "ScriptedSession":
        """The lesson's conversation, which plays the scenario from its first turn."""
        key = lesson.resolve()
        if key not in self._sessions:
            self._sessions[key] = ScriptedSession(
                lesson, iter(self.scenario), self.delay, self._clock, self._start_turn, self.received
            )
        return self._sessions[key]

    async def lesson_history(self, lesson: Path) -> list[PastTurn]:
        session = self._sessions.get(lesson.resolve())
        return list(session.turns) if session is not None else []

    async def archive(self, lesson: Path) -> None:
        self._sessions.pop(lesson.resolve(), None)
        self.archived.append(lesson)

    def _start_turn(self) -> None:
        self.turn_settings.append(self._current())

    def _presets(self) -> dict[str, ModelSettings]:
        return presets(choose_model(self._account.plan, MODELS))

    def _current(self) -> ModelSettings:
        return self._settings or self._presets()[self._preset]

    async def account(self) -> Account:
        return self._account

    async def login(self, api_key: str | None = None) -> Account:
        if self._login_failure is not None:
            raise LoginFailed(self._login_failure)
        self._account = self._chatgpt if api_key is None else Account(logged_in=True, method="api_key")
        self._settings = None
        return self._account

    async def logout(self) -> None:
        self._account = Account(logged_in=False)
        self._settings = None

    async def quota(self) -> list[QuotaWindow] | None:
        return QUOTA if self._account.method == "chatgpt" else None

    async def models(self) -> list[ModelOption]:
        return MODELS

    async def presets(self) -> dict[str, ModelSettings]:
        return self._presets()

    async def model_settings(self) -> ModelSettings:
        return self._current()

    async def set_model_settings(self, settings: ModelSettings) -> None:
        self._settings = settings

    async def use_preset(self, name: str) -> None:
        self._preset = name
        self._settings = None

    async def close(self) -> None:
        pass


class ScriptedSession:
    def __init__(
        self,
        lesson: Path,
        turns: Iterator[list[Step]],
        delay: float,
        clock: Callable[[], datetime],
        on_turn: Callable[[], None],
        received: list[Received],
    ) -> None:
        self.lesson = lesson
        # What each turn showed, kept as Codex keeps a thread.
        self.turns: list[PastTurn] = []
        self._turns = turns
        self._delay = delay
        self._clock = clock
        self._on_turn = on_turn
        self._received = received
        self._last_turn: str | None = None
        self._stopping = False

    @property
    def last_turn(self) -> str | None:
        return self._last_turn

    async def send(
        self, text: str, attachments: Sequence[Path] = (), output_schema: dict | None = None
    ) -> AsyncIterator[Event]:
        self._on_turn()
        self._stopping = False
        self._last_turn = f"turno-{len(self.turns) + 1}"
        turn = PastTurn(self._last_turn, "1", self._clock(), text, [])
        self.turns.append(turn)
        # Read now, as the Codex adapter does, since the files may change after the message.
        self._received.append(
            Received(text, {path.name: path.read_text(encoding="utf-8") for path in attachments}, output_schema)
        )
        steps = next(self._turns, None)
        if steps is None:
            yield self._kept(turn, AgentError("O roteiro do agente de demonstração acabou."))
            return
        for step in steps:
            await asyncio.sleep(self._delay)
            if self._stopping:
                yield self._kept(turn, AgentError("A resposta foi interrompida antes de terminar."))
                return
            if isinstance(step, Exception):
                raise step
            if isinstance(step, EditFile):
                yield self._kept(turn, self._edit(step))
            elif isinstance(step, Produce):
                self._target(step.path).write_bytes(step.content)
            else:
                yield self._kept(turn, step)

    async def stop(self) -> None:
        self._stopping = True

    @staticmethod
    def _kept(turn: PastTurn, event: Event) -> Event:
        # Codex keeps what the chat shows again, not what only shows while the turn runs.
        if not isinstance(event, Working):
            turn.events.append(event)
        return event

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
