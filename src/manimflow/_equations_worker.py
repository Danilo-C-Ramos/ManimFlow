"""Runs a lesson's equacoes() inside its own process, so lesson code can't crash the app.

Usage: python -m manimflow._equations_worker <lesson>

Prints one JSON object on stdout: {"entries": [[name, latex, value, unit], ...]} in
the order equacoes() returns them, or {"error": message} when the lesson code fails
or breaks the equations contract. The message is in Portuguese, for the teacher.
"""

import contextlib
import importlib.util
import json
import numbers
import sys
import traceback
from pathlib import Path
from typing import Any

PHYSICS_FILE = "fisica.py"


class _ContractError(Exception):
    """The physics file doesn't follow the equations contract; the message says how."""


def main(lesson: str) -> None:
    folder = Path(lesson).resolve()
    try:
        # Whatever the lesson code prints must not mix with the result.
        with contextlib.redirect_stdout(sys.stderr):
            result: dict = {"entries": _entries(folder)}
    except _ContractError as problem:
        result = {"error": str(problem)}
    except BaseException as error:  # noqa: BLE001 - lesson code may even call sys.exit()
        result = {"error": _failure(error, folder)}
    print(json.dumps(result))


def _entries(folder: Path) -> list[list]:
    path = folder / PHYSICS_FILE
    if not path.is_file():
        raise _ContractError(f"Esta aula ainda não tem {PHYSICS_FILE}.")
    # Lesson code imports its sibling modules, as when the agent runs it.
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    equacoes = getattr(module, "equacoes", None)
    if not callable(equacoes):
        raise _ContractError(f"{PHYSICS_FILE} não tem a função equacoes().")
    returned = equacoes()
    if isinstance(returned, (str, bytes)) or not hasattr(returned, "__iter__"):
        raise _ContractError("equacoes() precisa devolver uma lista de equações.")
    return [_entry(number, item) for number, item in enumerate(returned, start=1)]


def _entry(number: int, item: Any) -> list:
    name: object
    latex: object
    value: object
    unit: object
    try:
        name, latex, value, unit = item
    except (TypeError, ValueError):
        raise _ContractError(
            f"A equação {number} de equacoes() precisa ter nome, LaTeX, valor e unidade."
        ) from None
    if not all(isinstance(text, str) for text in (name, latex, unit)):
        raise _ContractError(f"Na equação {number} de equacoes(), o nome, o LaTeX e a unidade precisam ser textos.")
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise _ContractError(f"O valor da equação {number} ({name}) de equacoes() precisa ser um número.")
    return [name, latex, float(value), unit]


def _failure(error: BaseException, folder: Path) -> str:
    """Where the lesson code failed, and why, in one line."""
    if isinstance(error, SyntaxError) and error.filename:
        where: tuple[str, int | None] | None = (error.filename, error.lineno)
    else:
        frames = [frame for frame in traceback.extract_tb(error.__traceback__) if Path(frame.filename).parent == folder]
        where = (frames[-1].filename, frames[-1].lineno) if frames else None
    place = f" em {Path(where[0]).name}, linha {where[1]}" if where else ""
    reason = traceback.format_exception_only(error)[-1].strip()
    return f"O código da aula deu erro{place}: {reason}"


if __name__ == "__main__":
    main(*sys.argv[1:])
