"""The lesson's equations panel: every entry `equacoes()` returns, as math with its value and unit.

`equacoes()` lives in the lesson's physics file and runs in its own process
(manimflow._equations_worker), with a timeout, so lesson code that raises or
hangs only shows an error here. The panel watches the lesson's Python files and
the teacher's profile, so it shows the new equations after any change, whoever
made it: an agent turn, a manual edit and render, or the teacher in an editor.

Values use a decimal comma when the teacher's profile (`perfil.md`, one level
above the lesson, or two inside a turma) asks for a "vírgula decimal", as the
bundled profile does.
"""

import asyncio
import json
import logging
import math
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui

from manimflow.lessons import profile_of

logger = logging.getLogger(__name__)

# Seconds `equacoes()` may take before it is stopped.
TIMEOUT = 10.0
# Seconds between looks at the lesson folder.
REFRESH_INTERVAL = 0.5

_SUPERSCRIPTS = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


class Equation(ui.element, component="equation.js", esm={"manimflow-katex": "katex"}):
    """A LaTeX formula, typeset by KaTeX in the browser."""

    def __init__(self, latex: str) -> None:
        super().__init__()
        self._props["latex"] = latex


@dataclass(frozen=True)
class _Entry:
    name: str
    latex: str
    value: float
    unit: str


@dataclass(frozen=True)
class _Message:
    text: str
    details: tuple[str, ...] = ()


class EquationsPanel:
    def __init__(self, lesson: Path) -> None:
        self.lesson = lesson
        # The files `equacoes()` and the formatting depend on, as last computed.
        self._stamp: tuple | None = None
        with ui.column().classes("w-full gap-2").mark("equations"):
            ui.label("Equações").classes("text-lg")
            self.content = ui.column().classes("w-full gap-4")
            with self.content:
                ui.label("Calculando as equações…").classes("text-grey-7")
        ui.timer(REFRESH_INTERVAL, self._refresh)

    async def _refresh(self) -> None:
        """Computes the equations again when the lesson code or the profile changed."""
        stamp = self._current_stamp()
        if stamp == self._stamp:
            return
        # Taken before computing, so a change made meanwhile is computed on the next look.
        self._stamp = stamp
        result = await asyncio.to_thread(_compute, self.lesson)
        if not self.content.is_deleted:
            self._show(result, _decimal_comma(self.lesson))

    def _current_stamp(self) -> tuple:
        files = sorted(self.lesson.glob("*.py")) + [profile_of(self.lesson)]
        return tuple((path.name, *_signature(path)) for path in files)

    def _show(self, result: list[_Entry] | _Message, decimal_comma: bool) -> None:
        self.content.clear()
        with self.content:
            if isinstance(result, _Message):
                ui.label(result.text)
                for detail in result.details:
                    ui.label(detail).classes("text-negative text-sm")
                return
            if not result:
                ui.label("equacoes() ainda não devolve nenhuma equação.").classes("text-grey-7")
            for entry in result:
                with ui.column().classes("gap-1"):
                    ui.label(entry.name).classes("text-sm text-grey-7")
                    with ui.row().classes("items-baseline gap-2"):
                        Equation(entry.latex).classes("text-lg")
                        value = format_number(entry.value, decimal_comma)
                        ui.label(f"= {value} {entry.unit}".rstrip()).classes("text-lg")


def format_number(value: float, decimal_comma: bool) -> str:
    """Four significant digits without trailing zeros, and every digit before the point:
    1.25 -> 1,25; 10.6667 -> 10,67; 8.0 -> 8; 2.998e8 -> 2,998 × 10⁸."""
    if math.isnan(value):
        return "NaN"
    sign = "−" if value < 0 else ""
    if math.isinf(value):
        return f"{sign}∞"
    if value == 0:
        return "0"
    mantissa, exponent = f"{abs(value):.3e}".split("e")
    power = int(exponent)
    if -3 <= power < 6:
        text = _trim(f"{abs(value):.{max(0, 3 - power)}f}")
    else:
        text = f"{_trim(mantissa)} × 10{str(power).translate(_SUPERSCRIPTS)}"
    if decimal_comma:
        text = text.replace(".", ",")
    return sign + text


def _trim(number: str) -> str:
    return number.rstrip("0").rstrip(".") if "." in number else number


def _decimal_comma(lesson: Path) -> bool:
    try:
        profile = profile_of(lesson).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    plain = unicodedata.normalize("NFKD", profile.casefold()).encode("ascii", "ignore").decode()
    return "virgula decimal" in plain


def _signature(path: Path) -> tuple[int, int]:
    """The file's modification time in nanoseconds and its size, (0, -1) when it doesn't exist."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return (0, -1)
    return (stat.st_mtime_ns, stat.st_size)


def _compute(lesson: Path) -> list[_Entry] | _Message:
    """Runs the lesson's `equacoes()` in another process; blocking, so it runs in a thread."""
    try:
        worker = subprocess.run(
            [sys.executable, "-m", "manimflow._equations_worker", str(lesson.absolute())],
            cwd=lesson,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
            env={
                **os.environ,
                # Keep __pycache__ out of the teacher's lesson folder.
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
            },
        )
    except subprocess.TimeoutExpired:
        return _Message(
            f"O cálculo das equações passou de {format_number(TIMEOUT, True)} s e foi interrompido.",
            ("Confira se o código da aula não fica preso em um laço sem fim.",),
        )
    try:
        result = json.loads(worker.stdout)
    except ValueError:
        logger.debug("Equations worker failed: %s", worker.stderr)
        last_line = worker.stderr.strip().splitlines()[-1:]
        return _Message("O código da aula encerrou o cálculo das equações antes do fim.", tuple(last_line))
    if "error" in result:
        return _Message("Não foi possível calcular as equações.", (result["error"],))
    return [_Entry(*entry) for entry in result["entries"]]
