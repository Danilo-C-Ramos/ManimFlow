"""A lesson's conversation with the agent, kept by the server for as long as the app runs.

A lesson has one conversation, which every message continues (ADR 0005). Pages only
show it: a turn runs here to its end, saves its version and keeps what it showed,
whatever the pages do meanwhile, so a page opened in the middle of a turn joins it,
and every page on the lesson shows the same chat.
"""

import asyncio
import logging
import time
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from nicegui import background_tasks

from manimflow import activity, plan_turn
from manimflow.agent import Agent, AgentError, AssistantText, Checklist, Event, Session, Working
from manimflow.lessons import PLACEHOLDER_SCENE, TURMA_FILE, status
from manimflow.plan import load_plan
from manimflow.plan_turn import PlanReply
from manimflow.render import cache_dir
from manimflow.versioning import OUTSIDE_EDITS, History, Version

logger = logging.getLogger(__name__)

# The teacher's own edits since the agent's last turn, attached to the next message.
MANUAL_EDITS = "edicoes-manuais.diff"
# Which lesson the message is about, attached to every message.
LESSON_CONTEXT = "contexto-da-aula.md"

_UNEXPECTED = "O agente parou por um erro inesperado."
_STOPPED = "A resposta foi interrompida antes de terminar."


@dataclass
class ChatTurn:
    """One request and the agent's turn on it, as the chat shows it."""

    request: str
    # Lines under the teacher's message, such as the comments pinned on images.
    notes: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    # The thread it ran in; the chat marks where an older conversation ends.
    session: str | None = None
    id: str | None = None
    started_at: datetime | None = None
    seconds: float | None = None
    running: bool = False
    ok: bool = True
    # False when the message never reached the agent, which handled nothing of it.
    delivered: bool = True
    # The version that holds what the turn changed, None when it changed nothing.
    version: Version | None = None
    # The agent's own list of steps, while the turn runs.
    checklist: Checklist | None = None
    # The plan turn's answer, when it was one, and whether its plan was written.
    plan: PlanReply | None = None
    plan_written: bool = False
    # "Parar" was pressed; the turn stops as soon as it can.
    stop_requested: bool = False
    # Lines the app adds to the turn, such as an attachment it couldn't send.
    problems: list[str] = field(default_factory=list)
    _clock: float = field(default_factory=time.monotonic, repr=False)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._clock


class Listener(Protocol):
    """A page that shows the conversation."""

    def turn_started(self, turn: ChatTurn) -> None: ...

    def turn_event(self, turn: ChatTurn, event: Event) -> None: ...

    def turn_ended(self, turn: ChatTurn) -> None: ...

    def conversation_closed(self) -> None:
        """The lesson's conversation started over, as when the example is restored."""
        ...


_conversations: "weakref.WeakKeyDictionary[object, dict[Path, Conversation]]" = weakref.WeakKeyDictionary()


def conversation(agent: Agent, lesson: Path, example: bool = False) -> "Conversation":
    """The lesson's conversation, made the first time a page asks for it."""
    lessons = _conversations.setdefault(agent, {})
    key = lesson.absolute()
    if key not in lessons:
        lessons[key] = Conversation(agent, lesson, example)
    return lessons[key]


def forget(agent: Agent, lesson: Path) -> None:
    """Drops what the app keeps of the lesson's conversation, as when it starts over; the
    pages that show it are told."""
    talk = _conversations.get(agent, {}).pop(lesson.absolute(), None)
    if talk is not None:
        talk.closed = True
        talk.replaced.set()
        talk._tell("conversation_closed")


class Conversation:
    def __init__(self, agent: Agent, lesson: Path, example: bool = False) -> None:
        self.agent = agent
        self.lesson = lesson
        self.example = example
        self.history = History.open(lesson)
        self.running: ChatTurn | None = None
        # Once the conversation started over, nothing more is sent through this one.
        self.closed = False
        # Set once a new conversation took this one's place.
        self.replaced = asyncio.Event()
        # The turns read from the agent, None until a read worked; and the turns that ran
        # since the app started, which a read may also hold.
        self._turns: list[ChatTurn] | None = None
        self._recent: list[ChatTurn] = []
        self._loading: asyncio.Lock = asyncio.Lock()
        self._session: Session | None = None
        self._listeners: list[Listener] = []

    @property
    def busy(self) -> bool:
        return self.running is not None

    def listen(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def forget(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def load(self) -> None:
        """Reads the turns that ended from the agent, once; then they are kept here. After
        a failed read, the next page reads again."""
        async with self._loading:
            # Not during a turn: the agent's copy may hold it half done. A turn that started
            # while it was read may be in it too, so then the next page reads again.
            if self._turns is None and self.running is None:
                past = await self._past()
                if self.running is None:
                    self._turns = past

    @property
    def loaded(self) -> bool:
        return self._turns is not None

    @property
    def ended(self) -> list[ChatTurn]:
        """The turns that ended, oldest first: those read from the agent, then those that ran
        since the app started, each once."""
        recent = {turn.id for turn in self._recent if turn.id is not None}
        return [turn for turn in self._turns or [] if turn.id not in recent] + self._recent

    async def _past(self) -> list[ChatTurn] | None:
        try:
            past = await self.agent.lesson_history(self.lesson)
        except Exception:
            # The chat still works; only the earlier messages don't show.
            logger.exception("Reading the lesson's conversation failed")
            return None
        try:
            versions = self.history.turn_versions()
        except Exception:
            logger.exception("Reading the lesson's versions failed")
            versions = {}
        turns = []
        for item in past:
            turn = ChatTurn(
                item.request,
                session=item.session,
                id=item.id,
                started_at=item.started_at,
                seconds=item.seconds,
                version=versions.get(item.id),
            )
            for event in item.events:
                turn.events.append(_shown(turn, event, planning=True))
            turn.ok = not any(isinstance(event, AgentError) for event in turn.events)
            turn.plan_written = turn.ok and turn.plan is not None and turn.plan.plan is not None
            turns.append(turn)
        return turns

    def start(
        self,
        text: str,
        *,
        summary: str | None = None,
        notes: Sequence[str] = (),
        attachments: Sequence[Path] = (),
        plan: bool = False,
        after: Callable[[ChatTurn], None] | None = None,
    ) -> "asyncio.Task[ChatTurn]":
        """Sends `text` to the agent, as a plan turn when `plan`, and runs the turn here
        until it ends, whoever watches.

        The turn's version is named after `summary` when given, else after `text`.
        `after` runs once the turn's version is saved, also when no page is left.
        """
        if self.running is not None or self.closed:
            raise RuntimeError("the agent is still working on the lesson, or its conversation started over")
        turn = ChatTurn(text, notes=list(notes), running=True, started_at=datetime.now(UTC))
        self.running = turn
        activity.start(self.lesson)
        # Pages commit their own pending edits now, before the turn's first commit.
        self._tell("turn_started", turn)
        return background_tasks.create(self._run(turn, summary, attachments, plan, after), name="agent turn")

    async def stop(self) -> None:
        if self.running is None:
            return
        # Also before the turn reached the agent: then it never starts.
        self.running.stop_requested = True
        if self._session is not None:
            try:
                await self._session.stop()
            except Exception:
                logger.exception("Stopping the turn failed")

    async def _run(
        self,
        turn: ChatTurn,
        summary: str | None,
        extra: Sequence[Path],
        plan: bool,
        after: Callable[[ChatTurn], None] | None,
    ) -> ChatTurn:
        try:
            # So the agent's commit holds only what the agent changed.
            self._save(turn, lambda: self.history.commit_manual_edit(OUTSIDE_EDITS))
            attachments = self._context(turn) + self._manual_edits(turn) + list(extra)
            if plan:
                attachments.append(plan_turn.brief(self.lesson))
            if self._session is None:
                self._session = await self.agent.session(self.lesson)
            if turn.stop_requested:
                turn.delivered = False
                self._show(turn, AgentError(_STOPPED, delivered=False))
                return turn
            schema = plan_turn.SCHEMA if plan else None
            async for event in self._session.send(turn.request, attachments, schema):
                if isinstance(event, AgentError) and not event.delivered:
                    turn.delivered = False
                self._show(turn, event, planning=plan)
        except Exception:
            # The engine's own message is in English and meant for developers.
            logger.exception("Agent turn failed")
            if not turn.events:
                # It broke before the agent showed anything, such as while resuming the
                # conversation: the manual edits go with the next message.
                turn.delivered = False
            self._show(turn, AgentError(_UNEXPECTED))
        finally:
            # Also for a turn that broke off: its version still names it.
            turn.id = self._session.last_turn if self._session is not None and turn.delivered else None
            turn.ok = not any(isinstance(event, AgentError) for event in turn.events)
            if turn.plan is not None and turn.plan.plan is not None and turn.ok:
                try:
                    errors = plan_turn.apply(self.lesson, turn.plan)
                except Exception:
                    logger.exception("Writing the plan failed")
                    errors = ["Não foi possível gravar o plano na pasta da aula."]
                turn.problems += errors
                turn.plan_written = not errors
            elif plan and turn.ok and turn.plan is None:
                turn.problems.append(
                    "O agente não devolveu o plano desta vez. Mande o pedido de novo, ou mude para Caprichado."
                )
            # Even a failed turn may have changed files, and they must not be lost. A message
            # the agent never got leaves the manual edits for the next one.
            if turn.delivered:
                request = summary or turn.request
                commit = self._save(turn, lambda: self.history.commit_agent_turn(request, turn.id))
                if commit is not None:
                    turn.version = Version(commit, f"Pedido: {request}", datetime.now().astimezone(), turn.id)
            turn.seconds = turn.elapsed
            turn.running = False
            if after is not None:
                try:
                    after(turn)
                except Exception:
                    logger.exception("The step after the turn failed")
            self._recent.append(turn)
            self.running = None
            activity.stop(self.lesson)
            self._tell("turn_ended", turn)
        return turn

    def _show(self, turn: ChatTurn, event: Event, planning: bool = False) -> None:
        if isinstance(event, Checklist):
            turn.checklist = event
        elif not isinstance(event, Working):
            event = _shown(turn, event, planning)
            turn.events.append(event)
        self._tell("turn_event", turn, event)

    def _tell(self, what: str, *args: object) -> None:
        for listener in list(self._listeners):
            try:
                getattr(listener, what)(*args)
            except Exception:
                # A page that went away while the turn ran.
                logger.debug("A page stopped following the conversation", exc_info=True)
                self.forget(listener)

    def _save(self, turn: ChatTurn, commit: Callable[[], str | None]) -> str | None:
        try:
            return commit()
        except Exception:
            logger.exception("Commit failed")
            turn.problems.append("Não foi possível salvar uma versão desta mudança.")
            return None

    def _manual_edits(self, turn: ChatTurn) -> list[Path]:
        """The diff of the teacher's edits since the agent's last turn, as an attachment
        file, so the agent builds on them; none when there are no such edits."""
        try:
            diff = self.history.manual_changes()
            if not diff:
                return []
            attachment = cache_dir(self.lesson) / MANUAL_EDITS
            # As is: the diff holds each file's own line endings.
            attachment.write_text(diff, encoding="utf-8", newline="")
        except Exception:
            # The message still goes: the teacher can tell the agent what they changed.
            logger.exception("Manual changes failed")
            turn.problems.append("Não foi possível mandar ao agente as suas edições no código.")
            return []
        return [attachment]

    def _context(self, turn: ChatTurn) -> list[Path]:
        try:
            attachment = cache_dir(self.lesson) / LESSON_CONTEXT
            attachment.write_text(lesson_context(self.lesson, self.example), encoding="utf-8")
        except Exception:
            logger.exception("Writing the lesson's context failed")
            return []
        return [attachment]


def _shown(turn: ChatTurn, event: Event, planning: bool) -> Event:
    """The event as the chat shows it: a plan turn's answer becomes its message. Only a turn
    that asked for the plan has one; a past turn's is shown, never written again."""
    if planning and isinstance(event, AssistantText) and (reply := plan_turn.parse(event.text)) is not None:
        turn.plan = reply
        return AssistantText(reply.message)
    return event


_EXAMPLE = (
    "Esta é a aula de exemplo que vem com o ManimFlow, já pronta: o plano está aprovado e as "
    "cenas estão desenhadas e renderizadas. O professor abriu o exemplo para conhecer a ferramenta. "
    "Responda sobre esta aula a partir dos arquivos desta pasta e, quando ele pedir uma mudança, "
    "faça nesta cópia, que é dele: o ManimFlow guarda o original."
)


def lesson_context(lesson: Path, example: bool = False) -> str:
    """Which lesson the teacher has open, for the agent, written fresh for every message."""
    turma = lesson.parent.name if (lesson.parent / TURMA_FILE).is_file() else None
    lines = [
        "# A aula aberta no ManimFlow",
        "",
        "O ManimFlow manda este resumo com cada mensagem. Os detalhes estão nos arquivos da pasta.",
        "",
        f"- Aula: {lesson.name}",
        f"- Turma: {turma}" if turma else "- Sem turma",
    ]
    try:
        lines.append(f"- Situação: {status(lesson).value}")
        plan, _ = load_plan(lesson)
        if plan is not None and not all(state.scene == PLACEHOLDER_SCENE for state in plan.states):
            lines.append("- Estados do plano: " + "; ".join(f"{state.id} · {state.title}" for state in plan.states))
        elif plan is not None:
            lines.append("- O plano ainda não foi combinado.")
    except Exception:
        logger.debug("Reading the lesson's plan for its context failed", exc_info=True)
    if example:
        lines += ["", _EXAMPLE]
    return "\n".join(lines) + "\n"
