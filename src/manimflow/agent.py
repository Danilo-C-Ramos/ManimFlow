"""The `Agent` interface: everything the UI needs from the coding agent.

The UI only talks to this interface, so the engine behind it (the Codex
app-server, a scripted fake in tests and demos) can change without touching
the UI. Messages and errors that reach the teacher are in Portuguese.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class AssistantText:
    """Text the agent writes to the teacher."""

    text: str


@dataclass(frozen=True)
class CommandStarted:
    """The agent started a shell command; `id` pairs it with its CommandFinished.

    `reads` holds the files the command only reads, relative to the lesson when inside
    it, so the teacher sees "Lendo o plano" instead of a shell command.
    """

    id: str
    command: str
    reads: tuple[str, ...] = field(default=(), compare=False)


@dataclass(frozen=True)
class CommandFinished:
    id: str
    command: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class FileChanged:
    """The agent changed a file; `path` is relative to the lesson folder."""

    path: str
    change: Literal["added", "modified", "deleted"] = "modified"


@dataclass(frozen=True)
class ImageViewed:
    """The agent looked at an image, such as a rendered frame; `path` is relative to the lesson folder."""

    path: str


@dataclass(frozen=True)
class AgentError:
    """The turn failed; `message` explains why, for the teacher.

    `delivered` is False when the message never reached the agent, so it handled
    nothing of it, attachments included.
    """

    message: str
    delivered: bool = True


@dataclass(frozen=True)
class Working:
    """What the agent does between the other events, such as "Pensando", for the progress
    bar only: it never shows in the conversation."""

    label: str


@dataclass(frozen=True)
class ChecklistStep:
    text: str
    status: Literal["pending", "inProgress", "completed"]


@dataclass(frozen=True)
class Checklist:
    """The agent's own list of steps for the request, as it updates it; the progress bar
    shows where it is."""

    steps: tuple[ChecklistStep, ...]


Event = AssistantText | CommandStarted | CommandFinished | FileChanged | ImageViewed | AgentError | Working | Checklist


@dataclass(frozen=True)
class Account:
    logged_in: bool
    method: Literal["chatgpt", "api_key"] | None = None
    email: str | None = None
    # The ChatGPT plan, as Codex names it: "free", "go", "plus", "pro" and so on.
    plan: str | None = None


@dataclass(frozen=True)
class QuotaWindow:
    """How much of one of the ChatGPT plan's usage limits is spent."""

    used_percent: int
    # How long the limit's window lasts, such as 300 for five hours.
    minutes: int | None
    resets_at: datetime | None


class LoginFailed(Exception):
    """Signing in failed; the message explains why, for the teacher."""


@dataclass(frozen=True)
class ModelSettings:
    model: str
    effort: str


@dataclass(frozen=True)
class ModelOption:
    """A model the account may use, with the reasoning efforts it accepts."""

    model: str
    name: str
    efforts: tuple[str, ...]
    default_effort: str
    # The model the account's catalog starts on when nothing else is asked for.
    default: bool = False


# Between the teacher's words and each attachment, in the one text an engine gets.
_ATTACHMENT = "\n\n----- Anexo {name} -----\n\n"


def with_attachments(text: str, attachments: Sequence[Path]) -> str:
    """The teacher's message and each attachment's content, as one text for the agent.

    Read now, since the files may change after the message.
    """
    return text + "".join(
        _ATTACHMENT.format(name=path.name) + path.read_text(encoding="utf-8") for path in attachments
    )


def teachers_words(message: str) -> str:
    """A message made by `with_attachments`, without the attachments."""
    return message.split(_ATTACHMENT.split("{")[0], 1)[0]


@dataclass(frozen=True)
class PastTurn:
    """One turn of a lesson's conversation, as the chat shows it again.

    `session` is the thread it ran in: a lesson whose conversation outgrew the model's
    context, or that was used before conversations continued, has more than one.
    """

    id: str
    session: str
    # Aware; None when the engine didn't record it.
    started_at: datetime | None
    # The teacher's words, without the attachments.
    request: str
    events: list[Event]
    seconds: float | None = None


class Session(Protocol):
    """A lesson's conversation, which every message continues."""

    lesson: Path

    @property
    def last_turn(self) -> str | None:
        """The id of the turn the last `send` started, which the turn's version records;
        None when it started none."""
        ...

    def send(
        self, text: str, attachments: Sequence[Path] = (), output_schema: dict | None = None
    ) -> AsyncIterator[Event]:
        """Sends the teacher's message and streams the turn's events until it ends.

        With `output_schema`, the agent's last text is JSON that follows it.
        """
        ...

    async def stop(self) -> None:
        """Interrupts the turn that is running, if any; it ends with an AgentError."""
        ...


class Agent(Protocol):
    async def session(self, lesson: Path) -> Session:
        """The lesson's conversation: its newest thread in which the teacher wrote, which
        the next message continues, or a new one started by the first message."""
        ...

    async def lesson_history(self, lesson: Path) -> list[PastTurn]:
        """Every turn of the lesson's conversations, oldest first."""
        ...

    async def archive(self, lesson: Path) -> None:
        """Puts the lesson's conversations away, so its next message starts a new one."""
        ...

    async def account(self) -> Account: ...

    async def login(self, api_key: str | None = None) -> Account:
        """Signs in with the API key, or with ChatGPT in the browser when there is none.

        Raises LoginFailed when the teacher can't be signed in.
        """
        ...

    async def logout(self) -> None:
        """Signs out and deletes the stored credentials."""
        ...

    async def quota(self) -> list[QuotaWindow] | None:
        """How much of the ChatGPT plan is used; None without a plan, as with an API key."""
        ...

    async def models(self) -> list[ModelOption]:
        """The models the account may pick, in the engine's order."""
        ...

    async def presets(self) -> dict[str, ModelSettings]:
        """The "Rápido / Caprichado" switch, on the model chosen for the account's plan."""
        ...

    async def model_settings(self) -> ModelSettings:
        """What the next turn uses: the pick in "Avançado", else the switch's position on the account's model."""
        ...

    async def set_model_settings(self, settings: ModelSettings) -> None:
        """A pick in "Avançado"; signing in or out drops it, since another plan may lack the model."""
        ...

    async def use_preset(self, name: str) -> None:
        """Moves the switch to `name`, which each turn reads on the account it runs with."""
        ...

    async def close(self) -> None:
        """Stops the engine when the app shuts down."""
        ...
