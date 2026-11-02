"""The lesson's preview panel: each state's image and each transition's video, in plan order.

The panel watches the lesson's plan and output folder, so a render shows up
when it finishes, whoever started it: the agent, the UI or the teacher in a
terminal.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nicegui import app, ui

from manimflow.plan import PLAN_FILE, Plan, load_plan
from manimflow.render import OUTPUT_DIR, QUALITIES, SCENES_FILE

logger = logging.getLogger(__name__)

NOT_RENDERED = "Ainda não renderizado"
# Seconds between looks at the lesson folder.
REFRESH_INTERVAL = 0.5


@dataclass(frozen=True)
class _Card:
    """A state or a transition; `url` is its newest render, None when it was never rendered."""

    kind: Literal["state", "transition"]
    title: str
    url: str | None


@dataclass(frozen=True)
class _Message:
    text: str
    details: tuple[str, ...] = ()


_View = tuple[_Card, ...] | _Message


class PreviewPanel:
    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        self.served_at = serve_outputs(lesson)
        # The plan, checked again only when it or the scenes file changes.
        self._plan_stamp: tuple[int, ...] | None = None
        self._plan: Plan | _Message = _Message("")
        with ui.column().classes("w-full gap-2").mark("preview"):
            ui.label("Prévia").classes("text-lg")
            self.content = ui.column().classes("w-full gap-2")
        self.view = self._view()
        self.cards: list[ui.card] = []
        self._build()
        ui.timer(REFRESH_INTERVAL, self._refresh)

    def _refresh(self) -> None:
        """Redraws what changed in the plan or the renders since the panel was drawn."""
        try:
            view = self._view()
        except Exception:
            # The agent may be rewriting the plan right now; the next look will read it whole.
            logger.debug("Preview refresh failed", exc_info=True)
            return
        old, self.view = self.view, view
        if view == old:
            return
        if isinstance(old, tuple) and isinstance(view, tuple) and _same_cards(old, view):
            # Only redraw the cards that changed, so a video the teacher is watching keeps playing.
            for container, before, after in zip(self.cards, old, view):
                if before != after:
                    container.clear()
                    with container:
                        _draw(after)
        else:
            self._build()

    def _view(self) -> _View:
        plan = self._current_plan()
        if isinstance(plan, _Message):
            return plan
        transitions = {transition.source: transition for transition in plan.transitions}
        cards: list[_Card] = []
        for state in plan.states:
            image = latest_render(self.lesson, self.served_at, state.scene, "png")
            cards.append(_Card("state", f"{state.id} · {state.title}", image))
            if transition := transitions.get(state.id):
                title = f"{transition.source} → {transition.target}"
                video = latest_render(self.lesson, self.served_at, transition.scene, "mp4")
                cards.append(_Card("transition", title, video))
        return tuple(cards)

    def _current_plan(self) -> Plan | _Message:
        stamp = tuple(_modified(self.lesson / name) for name in (PLAN_FILE, SCENES_FILE))
        if stamp != self._plan_stamp:
            self._plan = _read_plan(self.lesson)
            self._plan_stamp = stamp
        return self._plan

    def _build(self) -> None:
        self.content.clear()
        self.cards = []
        with self.content:
            if isinstance(self.view, _Message):
                ui.label(self.view.text).classes("text-grey-7" if not self.view.details else "")
                for detail in self.view.details:
                    ui.label(detail).classes("text-negative text-sm")
                return
            for card in self.view:
                with ui.card().classes("w-full") as container:
                    _draw(card)
                self.cards.append(container)


def _read_plan(lesson: Path) -> Plan | _Message:
    if not (lesson / PLAN_FILE).is_file():
        return _Message("Esta aula ainda não tem plano.")
    plan, errors = load_plan(lesson)
    if plan is None:
        return _Message("O plano tem problemas, então a prévia não pode ser montada:", tuple(errors))
    return plan


def _same_cards(old: tuple[_Card, ...], new: tuple[_Card, ...]) -> bool:
    """Whether both views list the same states and transitions, renders aside."""
    return [(card.kind, card.title) for card in old] == [(card.kind, card.title) for card in new]


def _draw(card: _Card) -> None:
    ui.label(card.title)
    if card.url is None:
        ui.label(NOT_RENDERED).classes("text-grey-7")
    elif card.kind == "state":
        ui.image(card.url).classes("w-full")
    else:
        ui.video(card.url).classes("w-full")


def latest_render(lesson: Path, served_at: str, scene: str, extension: str) -> str | None:
    """The URL of the scene's newest output with this extension, preview or final, if ever rendered.

    `served_at` is the URL path `serve_outputs` returned for the lesson.
    """
    rendered: list[tuple[int, Path]] = []
    for _, folder in QUALITIES.values():
        path = lesson / folder / extension / f"{scene}.{extension}"
        if modified := _modified(path):
            rendered.append((modified, path))
    if not rendered:
        return None
    modified, path = max(rendered)
    # The same name gets new content on every render, so the browser must not reuse the old one.
    return f"{served_at}/{path.relative_to(lesson).as_posix()}?v={modified}"


def _modified(path: Path) -> int:
    """The file's modification time in nanoseconds, 0 when it doesn't exist."""
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        # Never written, or a render is replacing it right now.
        return 0


def serve_outputs(lesson: Path) -> str:
    """Serves the lesson's output folder, once, and returns the URL path the lesson is served under."""
    prefix = f"/_manimflow/aula/{hashlib.sha256(str(lesson.resolve()).encode()).hexdigest()[:16]}"
    folder = f"{prefix}/{OUTPUT_DIR}"
    # The route add_media_files registers; tests reset NiceGUI's routes between pages.
    if not any(getattr(route, "path", None) == f"{folder}/{{filename:path}}" for route in app.routes):
        # Media files, so the browser can seek inside a video.
        app.add_media_files(folder, lesson / OUTPUT_DIR)
    return prefix
