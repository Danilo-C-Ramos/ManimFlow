"""The plan cards: the lesson's plano.yaml as one card per state, with the transitions between them.

The teacher edits the cards in place, and every change is written back to
plano.yaml at once. The edits are committed as the teacher's when the next turn
starts, and the comments stay in the file until an approval's turn handles them. Once a state is rendered, its card shows the image, so the
cards become the lesson's timeline.
"""

import copy
import difflib
import io
import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol

import yaml
from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import SingleQuotedScalarString
from ruamel.yaml.tokens import CommentToken

from manimflow.lessons import PLACEHOLDER_SCENE
from manimflow.plan import PLAN_FILE, validate_plan
from manimflow.preview import REFRESH_INTERVAL, latest_render, serve_outputs
from manimflow.render import SCENES_FILE
from manimflow.versioning import History

logger = logging.getLogger(__name__)

FILL_IN = "Preencha este campo."
CARD_EDITS = f"Edição manual em {PLAN_FILE}"
HANDLED_COMMENTS = "Comentários do plano atendidos"


class Chat(Protocol):
    """Where the approval goes: the lesson's chat with the agent."""

    @property
    def busy(self) -> bool: ...

    def on_busy(self, listener: Callable[[bool], None]) -> None:
        """Calls `listener` with True when a turn starts, before anything is committed."""
        ...

    async def submit(self, text: str, summary: str | None = None) -> bool:
        """False when the agent's turn failed; `summary` names the turn's version."""
        ...


class PlanCards:
    def __init__(self, lesson: Path, chat: Chat, history: History) -> None:
        self.lesson = lesson
        self.chat = chat
        self.history = history
        # The plan's text as the cards show it, and as the agent last saw it, to tell it what the teacher changed.
        self.text: str | None = None
        self.approved = ""
        self.plan: Any = None
        self._stamp: tuple[int, ...] = ()
        self.served_at = serve_outputs(lesson)
        # Each card's thumbnail slot and the render it shows, None before the state is rendered.
        self.thumbnails: dict[str, tuple[ui.element, str | None]] = {}
        with ui.column().classes("w-full gap-0").mark("plan"):
            with ui.row().classes("w-full items-center justify-between no-wrap px-4 pt-3"):
                with ui.row().classes("items-baseline gap-2 no-wrap min-w-0"):
                    ui.label("Plano").classes("text-[15px] font-semibold")
                    ui.label("Edite o texto ou comente; vai tudo numa mensagem só.").classes(
                        "text-xs mf-faint ellipsis"
                    ).mark("plan-hint")
                self.approve_button = ui.button("Aprovar plano", on_click=self.approve).props(
                    "unelevated no-caps rounded dense"
                ).classes("px-3").mark("approve-plan")
                self.approve_button.set_visibility(False)
            self.content = ui.row().classes("mf-board")
        self._build()
        self._refresh()
        ui.timer(REFRESH_INTERVAL, self._refresh)
        chat.on_busy(self._commit_edits)

    def _commit_edits(self, busy: bool) -> None:
        """Commits the cards' edits as the teacher's before a turn starts, so neither the
        agent's version nor the edits made outside ManimFlow take them."""
        if not busy or self.text is None or self.text != _read(self.lesson / PLAN_FILE):
            return
        try:
            self.history.commit_manual_edit(CARD_EDITS, [PLAN_FILE])
        except Exception:
            # The turn's own commits pick the edits up.
            logger.exception("Committing the plan edits failed")

    def _refresh(self) -> None:
        """Redraws the cards when the plan changes on disk, by the agent or anyone but these cards,
        and each thumbnail when its state is rendered again."""
        self._refresh_plan()
        self._refresh_thumbnails()

    def _refresh_thumbnails(self) -> None:
        if self.plan is None:
            return
        for state in self.plan["estados"]:
            slot, shown = self.thumbnails[state["id"]]
            url = latest_render(self.lesson, self.served_at, state["cena"], "png")
            if url != shown:
                slot.clear()
                if url is not None:
                    with slot:
                        ui.image(url).props("ratio=1.7778").classes("w-full rounded border")
                self.thumbnails[state["id"]] = (slot, url)

    def _refresh_plan(self) -> bool:
        """Whether the cards were redrawn from the plan on disk."""
        stamp = tuple(_modified(self.lesson / name) for name in (PLAN_FILE, SCENES_FILE))
        if stamp == self._stamp:
            return False
        self._stamp = stamp
        try:
            text: str | None = (self.lesson / PLAN_FILE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        # The cards' own writes change nothing they show; the scenes file only matters to a plan that isn't valid yet.
        if text == self.text and (self.plan is not None or text is None):
            return False
        if text != self.text:
            self.text = text
            self.approved = text or ""
        try:
            self.plan = _yaml().load(text) if text is not None and validate_plan(self.lesson).ok else None
        except Exception:
            # The agent may be rewriting the plan right now; the next look will read it whole.
            logger.debug("Plan refresh failed", exc_info=True)
            self.plan = None
        # The scaffold's placeholder is no plan yet: the agent writes the first one.
        self.approve_button.set_visibility(self.can_approve)
        self._build()
        return True

    @property
    def can_approve(self) -> bool:
        """Whether there is a plan to approve: a valid one, not the scaffold's placeholder."""
        return self.plan is not None and not _placeholder(self.plan)

    async def approve(self) -> None:
        """Sends the plan's approval, with the teacher's changes and comments, in one message."""
        if self.plan is None:
            return
        if self.chat.busy:
            ui.notify("Espere o agente terminar para aprovar o plano.")
            return
        if self._refresh_plan():
            ui.notify("O plano mudou. Confira os cartões e aprove de novo.")
            return
        sent_comments = [(state["id"], comment) for state in self.plan["estados"] for comment in _comments(state)]
        titles = {state["id"]: state["titulo"] for state in self.plan["estados"]}
        comments = [f"- {state} ({titles[state]}): {comment}" for state, comment in sent_comments]
        previous = self.approved
        before, sent = _without_comments(previous), _without_comments(_dump(self.plan))
        self.approved = sent
        if not await self.chat.submit(_approval(before, sent, comments), summary="Aprovei o plano"):
            # The comments stay on the file for the next approval, and a plan the agent
            # rewrote meanwhile is the new baseline.
            if self.approved == sent:
                self.approved = previous
            return
        self._clear_handled(sent_comments)
        try:
            # The plan as the agent left it after acting on the approval.
            self.history.approve_plan()
        except Exception:
            logger.exception("Recording the approval failed")

    def _clear_handled(self, handled: list[tuple[str, str]]) -> None:
        """Takes the comments the agent handled off the plan on disk, leaving any the
        teacher wrote during the turn."""
        self._refresh_plan()
        if self.plan is None:
            return
        cleared = False
        for state in self.plan["estados"]:
            comments = _comments(state)
            for handled_state, comment in handled:
                if handled_state == state["id"] and comment in comments:
                    comments.remove(comment)
                    cleared = True
            _set_comments(state, comments)
        if not cleared:
            return
        self._write()
        self._build()
        try:
            self.history.commit_manual_edit(HANDLED_COMMENTS, [PLAN_FILE])
        except Exception:
            logger.exception("Committing the handled comments failed")

    def _build(self) -> None:
        self.content.clear()
        self.thumbnails = {}
        with self.content:
            if self.plan is None:
                if self.text is None:
                    ui.label("Esta aula ainda não tem plano.").classes("text-grey-7")
                else:
                    ui.label("O plano tem problemas. Veja os detalhes na prévia.").classes("text-grey-7")
                return
            transitions = {item["de"]: item for item in self.plan.get("transicoes") or []}
            for state in self.plan["estados"]:
                self._draw_state(state)
                if transition := transitions.get(state["id"]):
                    with ui.column().classes("mf-parrow"):
                        ui.icon("arrow_forward", size="18px")
                        ui.label(f"~{_seconds(transition['duracao'])} s · {transition['descricao']}")
            with ui.column().classes("justify-center px-3"):
                ui.button("+ estado", on_click=self._add_state).props("outline no-caps rounded").classes(
                    "whitespace-nowrap"
                )
        self._refresh_thumbnails()

    def _draw_state(self, state: Any) -> None:
        with ui.card().classes("mf-pcard"):
            ui.label(state["id"]).classes("mf-tag self-start")
            self.thumbnails[state["id"]] = (ui.element().classes("w-full"), None)
            self._field(ui.input, "Título", state, "titulo")
            self._field(ui.textarea, "O que aparece", state, "visivel").props("autogrow")
            for index, comment in enumerate(_comments(state)):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.icon("chat_bubble_outline", color="warning")
                    ui.label(comment).classes("grow text-[12px] text-amber-10")
                    ui.button(icon="close", on_click=lambda index=index: self._remove_comment(state, index)).props(
                        "flat dense round size=sm"
                    ).tooltip("Apagar comentário").mark(f"remover-comentario-{state['id']}")
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                comment_input = ui.input("Comentário").props("dense").classes("grow").mark(f"comentario-{state['id']}")
                comment_input.on("keydown.enter", lambda: self._add_comment(state, comment_input.value))
                ui.button(icon="send", on_click=lambda: self._add_comment(state, comment_input.value)).props(
                    "flat dense round size=sm"
                ).tooltip("Comentar").mark(f"comentar-{state['id']}")

    def _field(self, kind: type[ui.input], label: str, state: Any, key: str) -> ui.input:
        """An input for one of the state's texts, written to the plan as the teacher types."""

        def write(event: ValueChangeEventArguments) -> None:
            # An empty field would make the plan invalid, so the file keeps the last text until it is filled.
            if (event.value or "").strip() and not self._refresh_plan():
                state[key] = _text(event.value)
                self._write()

        field = kind(label, value=state[key], on_change=write, validation={FILL_IN: _filled})
        return field.classes("w-full").mark(f"{key}-{state['id']}")

    def _add_state(self) -> None:
        if self._refresh_plan():
            return
        states = self.plan["estados"]
        taken = {state["id"] for state in states}
        number = len(states)
        while f"S{number}" in taken:
            number += 1
        # A state needs a scene to stay valid. Until the agent draws its own, it shows the image
        # of the state before it, as a state that repeats an earlier image does.
        state = CommentedMap(
            id=f"S{number}",
            titulo="Novo estado",
            visivel="Descreva o que aparece neste estado.",
            cena=states[-1]["cena"],
        )
        # Spaced from the next one as the state before it is, when that space is only blank lines.
        gap = _take_gap(states[-1])
        _put_gap(states[-1], gap)
        if gap is not None and not gap.value.strip():
            _put_gap(state, copy.copy(gap))
        states.append(state)
        self._write()
        self._build()

    def _add_comment(self, state: Any, text: str | None) -> None:
        text = (text or "").strip()
        if not text or self._refresh_plan():
            return
        _set_comments(state, [*_comments(state), _text(text)])
        self._write()
        self._build()

    def _remove_comment(self, state: Any, index: int) -> None:
        if self._refresh_plan():
            return
        comments = _comments(state)
        del comments[index]
        _set_comments(state, comments)
        self._write()
        self._build()

    def _write(self) -> None:
        self.text = _dump(self.plan)
        path = self.lesson / PLAN_FILE
        # The file's own line endings, so its history shows only what changed.
        path.write_text(self.text, encoding="utf-8", newline=_line_ending(path))


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _placeholder(plan: Any) -> bool:
    """Whether the plan is still the new lesson's placeholder, with states the teacher
    may have added, all on the scaffold's empty scene."""
    return not plan.get("transicoes") and all(state["cena"] == PLACEHOLDER_SCENE for state in plan["estados"])


def _line_ending(path: Path) -> str:
    """The line ending the file uses, CRLF or LF; LF for a new file."""
    try:
        return "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    except FileNotFoundError:
        return "\n"


def _modified(path: Path) -> int:
    """The file's modification time in nanoseconds, 0 when it doesn't exist."""
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def _approval(before: str, after: str, comments: list[str]) -> str:
    """The one message that tells the agent the plan is approved, with the teacher's changes and comments."""
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            f"{PLAN_FILE} antes",
            f"{PLAN_FILE} aprovado",
        )
    )
    if not diff and not comments:
        return "Aprovei o plano como está, sem mudanças nem comentários."
    parts = ["Aprovei o plano."]
    if diff:
        parts.append(f"Mudei o {PLAN_FILE} assim:\n\n```diff\n{diff}```")
    if comments:
        parts.append("Comentários:\n" + "\n".join(comments))
    return "\n\n".join(parts)


def _without_comments(text: str) -> str:
    """The plan's text as `_dump` writes it, without the teacher's comments."""
    plan = _yaml().load(text)
    for state in plan["estados"]:
        _set_comments(state, [])
    return _dump(plan)


def _text(value: str) -> str:
    """The value, quoted when PyYAML, which validates the plan, would read it as something else.

    The round-trip YAML writes YAML 1.2, where `1:30` and `yes` are plain text; PyYAML reads
    YAML 1.1, where they are a number and a boolean.
    """
    try:
        plain = yaml.safe_load(value) == value
    except yaml.YAMLError:
        plain = False
    return value if plain else SingleQuotedScalarString(value)


def _comments(state: Any) -> list[str]:
    return list(state.get("comentarios") or [])


def _set_comments(state: Any, comments: list[str]) -> None:
    """Replaces the state's comments, dropping the key when there are none, and keeps
    the blank lines and YAML comments that follow the state where they were."""
    gap = _take_gap(state)
    if comments:
        state["comentarios"] = CommentedSeq(comments)
    else:
        state.pop("comentarios", None)
    _put_gap(state, gap)


def _take_gap(state: Any) -> CommentToken | None:
    """Removes what follows the state in the file (blank lines, YAML comments) and returns it.

    The round-trip YAML attaches it to the state's last value, or to the last item when that
    value is a list, so it has to move whenever the state's last key changes.
    """
    key = list(state)[-1]
    if isinstance(state[key], CommentedSeq) and state[key]:
        item = state[key].ca.items.pop(len(state[key]) - 1, None)
        return item[0] if item else None
    entry = state.ca.items.pop(key, None)
    return entry[2] if entry else None


def _put_gap(state: Any, gap: CommentToken | None) -> None:
    if gap is None:
        return
    key = list(state)[-1]
    if isinstance(state[key], CommentedSeq) and state[key]:
        state[key].ca.items[len(state[key]) - 1] = [gap, None, None, None]
    else:
        state.ca.items[key] = [None, None, gap, None]


def _filled(value: str | None) -> bool:
    return bool((value or "").strip())


def _yaml() -> YAML:
    """A round-trip YAML that keeps the plan's comments and layout when it writes the file back."""
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    return yaml


def _dump(plan: Any) -> str:
    text = io.StringIO()
    _yaml().dump(plan, text)
    return text.getvalue()


def _seconds(duration: float) -> str:
    """`4,7` for 4.7: the teacher reads a decimal comma."""
    return f"{duration:g}".replace(".", ",")
