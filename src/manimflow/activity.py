"""What the running app is doing to each lesson, which the lesson folder can't tell:
the agent working on it, a render or an export running, an export the teacher hasn't
looked at yet. The sidebar and the cards read it next to the lesson's status.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_working: Counter[Path] = Counter()
_exports: dict[Path, "FreshExport"] = {}


@dataclass(frozen=True)
class FreshExport:
    preset: str
    folder: Path
    when: datetime


def _key(lesson: Path) -> Path:
    return lesson.absolute()


def start(lesson: Path) -> None:
    """The agent, a render or an export started on the lesson; pair it with `stop`."""
    _working[_key(lesson)] += 1


def stop(lesson: Path) -> None:
    key = _key(lesson)
    _working[key] -= 1
    if _working[key] <= 0:
        del _working[key]


def working(lesson: Path) -> bool:
    return _working[_key(lesson)] > 0


def exported(lesson: Path, preset: str, folder: Path) -> None:
    """An export finished; it waits in "Precisa de você" until the teacher opens it."""
    _exports[_key(lesson)] = FreshExport(preset, folder, datetime.now())


def fresh_export(lesson: Path) -> FreshExport | None:
    return _exports.get(_key(lesson))


def seen_export(lesson: Path) -> None:
    _exports.pop(_key(lesson), None)
