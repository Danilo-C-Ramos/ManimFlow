"""The `Agent` interface: everything the UI needs from the coding agent.

The UI only talks to this interface, so the engine behind it (the Codex
app-server, a scripted fake in tests and demos) can change without touching
the UI. Messages and errors that reach the teacher are in Portuguese.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
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
    """The turn failed; `message` explains why, for the teacher."""

    message: str


Event = AssistantText | CommandStarted | CommandFinished | FileChanged | ImageViewed | AgentError


@dataclass(frozen=True)
class Account:
    logged_in: bool
    method: Literal["chatgpt", "api_key"] | None = None
    email: str | None = None


class LoginFailed(Exception):
    """Signing in failed; the message explains why, for the teacher."""


@dataclass(frozen=True)
class ModelSettings:
    model: str
    effort: str


class Session(Protocol):
    """One conversation thread about one lesson."""

    lesson: Path

    def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        """Sends the teacher's message and streams the turn's events until it ends."""
        ...


class Agent(Protocol):
    async def start_session(self, lesson: Path) -> Session: ...

    async def account(self) -> Account: ...

    async def login(self, api_key: str | None = None) -> Account:
        """Signs in with the API key, or with ChatGPT in the browser when there is none.

        Raises LoginFailed when the teacher can't be signed in.
        """
        ...

    async def model_settings(self) -> ModelSettings: ...

    async def set_model_settings(self, settings: ModelSettings) -> None: ...

    async def close(self) -> None:
        """Stops the engine when the app shuts down."""
        ...
