"""The plan cards: the lesson's plano.yaml as one card per state, with the transitions between them.

The teacher edits the cards in place, and every change is written back to
plano.yaml at once. Once a state is rendered, its card shows the image, so the
cards become the lesson's timeline.
"""

import copy
import difflib
import io
import logging
from pathlib import Path
from typing import Any, Protocol

from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.tokens import CommentToken

from manimflow.plan import PLAN_FILE, validate_plan
from manimflow.preview import REFRESH_INTERVAL, latest_render, serve_outputs
from manimflow.render import SCENES_FILE

logger = logging.getLogger(__name__)

FILL_IN = "Preencha este campo."


class Chat(Protocol):
    """Where the approval goes: the lesson's chat with the agent."""

    @property
    def busy(self) -> bool: ...

    async def submit(self, text: str) -> None: ...


class PlanCards:
    def __init__(self, lesson: Path, chat: Chat) -> None:
        self.lesson = lesson
        self.chat = chat
        # The plan's text as the cards show it, and as the agent last saw it, to tell it what the teacher changed.
        self.text: str | None = None
        self.approved = ""
        self.plan: Any = None
        self._stamp: tuple[int, ...] = ()
        self.served_at = serve_outputs(lesson)
        # Each card's thumbnail slot and the render it shows, None before the state is rendered.
        self.thumbnails: dict[str, tuple[ui.element, str | None]] = {}
        with ui.card().classes("w-full"), ui.column().classes("w-full gap-2").mark("plan"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Plano").classes("text-lg")
                self.approve_button = ui.button("Aprovar plano", on_click=self._approve)
                self.approve_button.set_visibility(False)
            self.content = ui.column().classes("w-full gap-2")
        self._build()
        self._refresh()
        ui.timer(REFRESH_INTERVAL, self._refresh)

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
                        ui.image(url).classes("w-48 rounded")
                self.thumbnails[state["id"]] = (slot, url)

    def _refresh_plan(self) -> None:
        stamp = tuple(_modified(self.lesson / name) for name in (PLAN_FILE, SCENES_FILE))
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            text: str | None = (self.lesson / PLAN_FILE).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = None
        # The cards' own writes change nothing they show; the scenes file only matters to a plan that isn't valid yet.
        if text == self.text and (self.plan is not None or text is None):
            return
        if text != self.text:
            self.text = text
            self.approved = text or ""
        try:
            self.plan = _yaml().load(text) if text is not None and validate_plan(self.lesson).ok else None
        except Exception:
            # The agent may be rewriting the plan right now; the next look will read it whole.
            logger.debug("Plan refresh failed", exc_info=True)
            self.plan = None
        self.approve_button.set_visibility(self.plan is not None)
        self._build()

    async def _approve(self) -> None:
        if self.plan is None:
            return
        if self.chat.busy:
            ui.notify("Espere o agente terminar para aprovar o plano.")
            return
        comments: list[str] = []
        for state in self.plan["estados"]:
            comments += [f"- {state['id']} ({state['titulo']}): {comment}" for comment in _comments(state)]
            _set_comments(state, [])
        self._write()
        before, self.approved = _without_comments(self.approved), _dump(self.plan)
        self._build()
        await self.chat.submit(_approval(before, self.approved, comments))

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
                    ui.label(f"~{_seconds(transition['duracao'])} s · {transition['descricao']}")
            ui.button("+ estado", on_click=self._add_state).props("outline")
        self._refresh_thumbnails()

    def _draw_state(self, state: Any) -> None:
        with ui.card().classes("w-full"):
            ui.label(state["id"]).classes("font-bold")
            self.thumbnails[state["id"]] = (ui.element(), None)
            self._field(ui.input, "Título", state, "titulo")
            self._field(ui.textarea, "O que aparece", state, "visivel").props("autogrow")
            for index, comment in enumerate(_comments(state)):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    ui.icon("chat_bubble_outline", color="grey-7")
                    ui.label(comment).classes("grow")
                    ui.button(icon="close", on_click=lambda index=index: self._remove_comment(state, index)).props(
                        "flat dense round size=sm"
                    ).tooltip("Apagar comentário").mark(f"remover-comentario-{state['id']}")
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                comment_input = ui.input("Comentário").props("dense").classes("grow").mark(f"comentario-{state['id']}")
                comment_input.on("keydown.enter", lambda: self._add_comment(state, comment_input.value))
                ui.button("Comentar", on_click=lambda: self._add_comment(state, comment_input.value)).props(
                    "flat"
                ).mark(f"comentar-{state['id']}")

    def _field(self, kind: type[ui.input], label: str, state: Any, key: str) -> ui.input:
        """An input for one of the state's texts, written to the plan as the teacher types."""

        def write(event: ValueChangeEventArguments) -> None:
            # An empty field would make the plan invalid, so the file keeps the last text until it is filled.
            if (event.value or "").strip():
                state[key] = event.value
                self._write()

        field = kind(label, value=state[key], on_change=write, validation={FILL_IN: _filled})
        return field.classes("w-full").mark(f"{key}-{state['id']}")

    def _add_state(self) -> None:
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
        if not text:
            return
        _set_comments(state, [*_comments(state), text])
        self._write()
        self._build()

    def _remove_comment(self, state: Any, index: int) -> None:
        comments = _comments(state)
        del comments[index]
        _set_comments(state, comments)
        self._write()
        self._build()

    def _write(self) -> None:
        self.text = _dump(self.plan)
        (self.lesson / PLAN_FILE).write_text(self.text, encoding="utf-8")


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
