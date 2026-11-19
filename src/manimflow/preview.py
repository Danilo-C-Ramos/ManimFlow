"""The lesson's preview: a stage with the picked state's image or transition's video, and a
filmstrip of the states in plan order with a play pill for each transition between them.

The panel watches the lesson's plan and output folder, so a render shows up
when it finishes, whoever started it: the agent, the UI or the teacher in a
terminal. On a state's image the teacher can pin a comment (`pins.py`).
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nicegui import app, ui
from nicegui.events import MouseEventArguments

from manimflow.pins import Pins
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
    # The state's id, or "S0 → S1" for a transition.
    id: str
    title: str
    scene: str
    url: str | None
    # The transition's approximate length in seconds.
    duration: float | None = None


@dataclass(frozen=True)
class _Message:
    text: str
    details: tuple[str, ...] = ()


_View = tuple[_Card, ...] | _Message


class PreviewPanel:
    def __init__(self, lesson: Path, pins: Pins | None = None) -> None:
        self.lesson = lesson
        self.pins = pins or Pins(lesson)
        self.served_at = serve_outputs(lesson)
        # The plan, checked again only when it or the scenes file changes.
        self._plan_stamp: tuple[int, ...] | None = None
        self._plan: Plan | _Message = _Message("")
        # The id of the card on the stage.
        self.selected: str | None = None
        self.pinning = False
        with ui.column().classes("mf-stagecol").mark("preview"):
            self.message = ui.column().classes("w-full gap-1")
            self.stage = ui.element("div").classes("mf-stage").mark("stage")
            with ui.row().classes("w-full items-center no-wrap gap-2").mark("stage-caption") as self.caption_row:
                self.caption = ui.label().classes("font-medium grow")
                self.pin_button = (
                    ui.button("Comentar na imagem", icon="push_pin", on_click=self._toggle_pinning)
                    .props("outline no-caps dense rounded")
                    .classes("px-3")
                    .mark("pin-mode")
                )
            self.film = ui.row().classes("mf-film").mark("filmstrip")
        self.view = self._view()
        self.frames: dict[str, ui.element] = {}
        self._build()
        self.pins.on_change(self._draw_stage)
        ui.timer(REFRESH_INTERVAL, self._refresh)

    def select(self, id: str) -> None:
        """Puts the state or transition with this id on the stage."""
        if self.selected == id:
            return
        self.selected = id
        self.pinning = False
        for card_id, frame in self.frames.items():
            frame.classes(add="on" if card_id == id else "", remove="" if card_id == id else "on")
        self._draw_stage()

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
            # Only redraw what changed, so a video the teacher is watching keeps playing.
            for before, after in zip(old, view):
                if before != after:
                    self._draw_frame_content(after)
                    if after.id == self.selected:
                        self._draw_stage()
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
            cards.append(_Card("state", state.id, state.title, state.scene, image))
            if transition := transitions.get(state.id):
                video = latest_render(self.lesson, self.served_at, transition.scene, "mp4")
                id = f"{transition.source} → {transition.target}"
                cards.append(
                    _Card("transition", id, transition.description, transition.scene, video, transition.duration)
                )
        return tuple(cards)

    def _current_plan(self) -> Plan | _Message:
        stamp = tuple(_modified(self.lesson / name) for name in (PLAN_FILE, SCENES_FILE))
        if stamp != self._plan_stamp:
            self._plan = _read_plan(self.lesson)
            self._plan_stamp = stamp
        return self._plan

    def _cards(self) -> dict[str, _Card]:
        return {card.id: card for card in self.view} if isinstance(self.view, tuple) else {}

    def _build(self) -> None:
        self.message.clear()
        self.film.clear()
        self.frames = {}
        cards = self._cards()
        showing = bool(cards)
        for element in (self.stage, self.caption_row, self.film):
            element.set_visibility(showing)
        if isinstance(self.view, _Message):
            with self.message:
                ui.label(self.view.text).classes("mf-muted" if not self.view.details else "")
                for detail in self.view.details:
                    ui.label(detail).classes("text-negative text-sm")
            return
        if self.selected not in cards:
            self.selected = next(iter(cards))
        with self.film:
            for card in self.view:
                if card.kind == "state":
                    frame = ui.column().classes("mf-frame").on("click", lambda id=card.id: self.select(id))
                else:
                    frame = ui.column().classes("mf-tpill").on("click", lambda id=card.id: self.select(id))
                frame.mark(f"frame-{card.id}")
                if card.id == self.selected:
                    frame.classes(add="on")
                self.frames[card.id] = frame
                self._draw_frame_content(card)
        self._draw_stage()

    def _draw_frame_content(self, card: _Card) -> None:
        frame = self.frames[card.id]
        frame.clear()
        with frame:
            if card.kind == "state":
                with ui.element("div").classes("mf-mini"):
                    if card.url is None:
                        ui.label(NOT_RENDERED)
                    else:
                        ui.image(card.url)
                with ui.row().classes("mf-cap items-center"):
                    ui.label(card.id).classes("mf-tag")
                    ui.label(card.title).classes("ellipsis min-w-0")
            else:
                ui.label("▶" if card.url else "·").classes("mf-play").tooltip(
                    card.title if card.url else f"{card.title} ({NOT_RENDERED.lower()})"
                )
                if card.duration is not None:
                    ui.label(f"{_seconds(card.duration)} s")

    def _draw_stage(self) -> None:
        card = self._cards().get(self.selected or "")
        self.stage.clear()
        self.stage.classes(remove="pinning")
        if card is None:
            return
        self.caption.set_text(f"{card.id} · {card.title}")
        self.pin_button.set_visibility(card.kind == "state" and card.url is not None)
        self.pin_button.props(f"color={'warning' if self.pinning else 'primary'}")
        self.pin_button.set_text("Clique na imagem…" if self.pinning else "Comentar na imagem")
        with self.stage:
            if card.url is None:
                ui.label(NOT_RENDERED)
            elif card.kind == "state":
                if self.pinning:
                    self.stage.classes(add="pinning")
                image = ui.interactive_image(
                    card.url, on_mouse=lambda event: self._pin_at(card, event), events=["click"], sanitize=False
                ).classes("w-full h-full")
                path = render_path(self.lesson, card.scene, "png")
                image.set_content(self.pins.svg(card.id, path))
            else:
                ui.video(card.url, autoplay=True).classes("w-full h-full")

    def _toggle_pinning(self) -> None:
        self.pinning = not self.pinning
        self._draw_stage()

    def _pin_at(self, card: _Card, event: MouseEventArguments) -> None:
        if not self.pinning:
            return
        self.pinning = False
        path = render_path(self.lesson, card.scene, "png")
        if path is None:
            return
        self.pins.ask(card.id, card.title, path, event.image_x, event.image_y)


def _read_plan(lesson: Path) -> Plan | _Message:
    if not (lesson / PLAN_FILE).is_file():
        return _Message("Esta aula ainda não tem plano.")
    plan, errors = load_plan(lesson)
    if plan is None:
        return _Message("O plano tem problemas, então a prévia não pode ser montada:", tuple(errors))
    return plan


def _same_cards(old: tuple[_Card, ...], new: tuple[_Card, ...]) -> bool:
    """Whether both views list the same states and transitions, renders aside."""
    return [(card.kind, card.id) for card in old] == [(card.kind, card.id) for card in new]


def render_path(lesson: Path, scene: str, extension: str) -> Path | None:
    """The scene's newest output with this extension, preview or final, if ever rendered."""
    rendered: list[tuple[int, Path]] = []
    for _, folder in QUALITIES.values():
        path = lesson / folder / extension / f"{scene}.{extension}"
        if modified := _modified(path):
            rendered.append((modified, path))
    return max(rendered)[1] if rendered else None


def latest_render(lesson: Path, served_at: str, scene: str, extension: str) -> str | None:
    """The URL of the scene's newest output with this extension, preview or final, if ever rendered.

    `served_at` is the URL path `serve_outputs` returned for the lesson.
    """
    path = render_path(lesson, scene, extension)
    if path is None:
        return None
    # The same name gets new content on every render, so the browser must not reuse the old one.
    return f"{served_at}/{path.relative_to(lesson).as_posix()}?v={_modified(path)}"


def _modified(path: Path) -> int:
    """The file's modification time in nanoseconds, 0 when it doesn't exist."""
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        # Never written, or a render is replacing it right now.
        return 0


def _seconds(duration: float) -> str:
    """`4,7` for 4.7: the teacher reads a decimal comma."""
    return f"{duration:g}".replace(".", ",")


def serve_outputs(lesson: Path) -> str:
    """Serves the lesson's output folder, once, and returns the URL path the lesson is served under."""
    prefix = f"/_manimflow/aula/{hashlib.sha256(str(lesson.resolve()).encode()).hexdigest()[:16]}"
    folder = f"{prefix}/{OUTPUT_DIR}"
    # The route add_media_files registers; tests reset NiceGUI's routes between pages.
    if not any(getattr(route, "path", None) == f"{folder}/{{filename:path}}" for route in app.routes):
        # Media files, so the browser can seek inside a video.
        app.add_media_files(folder, lesson / OUTPUT_DIR)
    return prefix
