"""Comments pinned on a state's image: the teacher clicks a spot of the frame and types a
note, and the note goes with the next message, the way manual edits do.

Each note reaches the agent as the attachment `comentarios-na-imagem.md`: the state,
the spot as a fraction of the frame, the text, and a copy of the frame with the
numbered pin drawn on it, inside the lesson so the agent can look at it. A pin turns
green once the turn that carried it has run.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui
from PIL import Image, ImageDraw, ImageFont

from manimflow.render import cache_dir

logger = logging.getLogger(__name__)

ATTACHMENT = "comentarios-na-imagem.md"
_IMAGES = "comentarios"
_PENDING = "#f59f00"
_DONE = "#16a34a"


@dataclass
class Pin:
    number: int
    state: str
    title: str
    # The render the pin was placed on, and the spot on it in pixels.
    image: Path
    x: float
    y: float
    width: int
    height: int
    text: str
    done: bool = False

    @property
    def where(self) -> tuple[float, float]:
        """The spot as a fraction of the frame's width and height, from the top left."""
        return self.x / self.width, self.y / self.height


class Pins:
    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        self.items: list[Pin] = []
        self._listeners: list[Callable[[], None]] = []
        self._asking: tuple[str, str, Path, float, float] | None = None
        with ui.dialog() as self.dialog, ui.card().classes("w-96 items-stretch gap-2"):
            self.heading = ui.label().classes("font-medium")
            self.text = (
                ui.input(placeholder="Ex.: baixe um pouco este rótulo")
                .props("outlined dense autofocus")
                .mark("pin-text")
            )
            self.text.on("keydown.enter", self._save)
            with ui.row().classes("justify-end"):
                ui.button("Cancelar", on_click=self.dialog.close).props("flat")
                ui.button("Comentar", on_click=self._save).mark("save-pin")

    def on_change(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def ask(self, state: str, title: str, image: Path, x: float, y: float) -> None:
        """Asks for the note to pin at (x, y), in pixels of `image`, the render of `state`."""
        self._asking = (state, title, image, x, y)
        self.heading.set_text(f"Comentário no estado {state} · {title}")
        self.text.value = ""
        self.dialog.open()

    def _save(self) -> None:
        text = (self.text.value or "").strip()
        if not text or self._asking is None:
            return
        state, title, image, x, y = self._asking
        try:
            with Image.open(image) as frame:
                width, height = frame.size
        except OSError:
            logger.exception("Reading the frame to pin failed")
            ui.notify("Não foi possível ler esta imagem. Renderize o estado de novo.", type="negative")
            return
        number = max((pin.number for pin in self.items), default=0) + 1
        self.items.append(Pin(number, state, title, image, x, y, width, height, text))
        self._asking = None
        self.dialog.close()
        self._changed()

    def pending(self) -> list[Pin]:
        return [pin for pin in self.items if not pin.done]

    def remove(self, pin: Pin) -> None:
        self.items.remove(pin)
        self._changed()

    def resolved(self, pins: list[Pin]) -> None:
        """The agent ran the turn that carried `pins`."""
        for pin in pins:
            pin.done = True
        self._changed()

    def svg(self, state: str, image: Path | None) -> str:
        """The pins on the state's image, as SVG over it in the image's own pixels."""
        pins = [pin for pin in self.items if pin.state == state and pin.image == image]
        shapes = []
        for pin in pins:
            radius = max(pin.width / 70, 8)
            color = _DONE if pin.done else _PENDING
            shapes.append(
                f'<circle cx="{pin.x}" cy="{pin.y}" r="{radius}" fill="{color}" stroke="white" stroke-width="{radius / 5}"/>'
                f'<text x="{pin.x}" y="{pin.y}" fill="white" font-size="{radius * 1.1}" font-family="sans-serif" '
                f'font-weight="600" text-anchor="middle" dominant-baseline="central">{pin.number}</text>'
            )
        return "".join(shapes)

    def attachment(self, pins: list[Pin]) -> Path:
        """Writes the notes and the marked frames for the agent, and returns the notes' file."""
        folder = cache_dir(self.lesson) / _IMAGES
        folder.mkdir(exist_ok=True)
        lines = ["# Comentários na imagem", ""]
        for pin in pins:
            marked = folder / f"{pin.number}-{pin.state}.png"
            _draw(pin, marked)
            x, y = pin.where
            lines += [
                f"{pin.number}. Estado {pin.state} ({pin.title}), em x = {_fraction(x)} e y = {_fraction(y)} do quadro: "
                f"{pin.text}",
                f"   Imagem com o marcador: {marked.relative_to(self.lesson).as_posix()}",
            ]
        notes = cache_dir(self.lesson) / ATTACHMENT
        notes.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return notes

    def _changed(self) -> None:
        for listener in self._listeners:
            listener()


def _draw(pin: Pin, target: Path) -> None:
    with Image.open(pin.image) as frame:
        marked = frame.convert("RGB")
    draw = ImageDraw.Draw(marked)
    radius = max(pin.width / 70, 8)
    draw.ellipse(
        (pin.x - radius, pin.y - radius, pin.x + radius, pin.y + radius),
        fill=_PENDING,
        outline="white",
        width=max(int(radius / 5), 1),
    )
    font = ImageFont.load_default(size=radius * 1.1)
    draw.text((pin.x, pin.y), str(pin.number), fill="white", font=font, anchor="mm")
    marked.save(target)


def _fraction(value: float) -> str:
    """0,62 for 0.62: the agent reads it in the teacher's language."""
    return f"{value:.2f}".replace(".", ",")
