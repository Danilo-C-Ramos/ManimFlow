"""The `Agent` interface: everything the UI needs from the coding agent.

The UI only talks to this interface, so the engine behind it (the Codex
app-server, a scripted fake in tests and demos) can change without touching
the UI. Messages and errors that reach the teacher are in Portuguese.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class AssistantText:
    """Text the agent writes to the teacher."""

    text: str


@dataclass(frozen=True)
class CommandStarted:
    """The agent started a shell command; `id` pairs it with its CommandFinished."""

    id: str
    command: str


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


Event = AssistantText | CommandStarted | CommandFinished | FileChanged | ImageViewed | AgentError


@dataclass(frozen=True)
class Account:
    logged_in: bool
    method: Literal["chatgpt", "api_key"] | None = None
    email: str | None = None


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


@dataclass(frozen=True)
class Message:
    """One message of a conversation, by the teacher or by the agent."""

    author: Literal["teacher", "agent"]
    text: str


@dataclass(frozen=True)
class PastSession:
    """A lesson's earlier conversation, as the session list shows it."""

    id: str
    started_at: datetime
    first_request: str


class Session(Protocol):
    """One conversation thread about one lesson."""

    id: str
    lesson: Path

    def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        """Sends the teacher's message and streams the turn's events until it ends."""
        ...


class Agent(Protocol):
    async def start_session(self, lesson: Path) -> Session:
        """Starts a new conversation about the lesson; it never resumes an old one."""
        ...

    async def past_sessions(self, lesson: Path) -> list[PastSession]:
        """The lesson's sessions in which the teacher sent something, newest first."""
        ...

    async def session_messages(self, session_id: str) -> list[Message]:
        """The messages of a past session, in order."""
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

    async def model_settings(self) -> ModelSettings: ...

    async def set_model_settings(self, settings: ModelSettings) -> None: ...

    async def close(self) -> None:
        """Stops the engine when the app shuts down."""
        ...
