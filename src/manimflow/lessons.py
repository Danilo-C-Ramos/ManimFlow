"""The lesson store: the teacher's lessons folder, the lessons in it and the bundled example.

The lessons live in `<Documents>/Aulas Manim` unless the teacher picks another
folder, and that choice is kept in ManimFlow's own folder. See docs/lessons.md.
"""

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import yaml

from manimflow.paths import documents_dir
from manimflow.plan import PLAN_FILE
from manimflow.render import OUTPUT_DIR, SCENES_FILE
from manimflow.versioning import History

LESSONS_FOLDER = "Aulas Manim"
PROFILE_FILE = "perfil.md"

_PACKAGE = Path(str(files("manimflow")))
# What a new lesson starts from: a plan with one placeholder state, and its empty scene.
_SCAFFOLD = _PACKAGE / "modelo"
_EXAMPLES = _PACKAGE / "exemplos"
EXAMPLE_NAME = "Relatividade - herói e espelho"
# The bundled example's profile is also every teacher's first one.
_DEFAULT_PROFILE = _EXAMPLES / PROFILE_FILE

_CONFIG = "config.json"
# Kept short so paths inside the lesson stay under Windows' 260-character limit.
_MAX_NAME = 80
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.IGNORECASE)


class LessonNameError(ValueError):
    """The name can't be a new lesson's; the message, in Portuguese, says why."""


@dataclass(frozen=True)
class LessonSummary:
    name: str
    path: Path
    edited: datetime
    # None when plano.yaml is missing or has no list of states.
    states: int | None


class Library:
    def __init__(self, data: Path) -> None:
        """`data` is ManimFlow's own folder: the choice of lessons folder and the
        example's copy are kept there."""
        self.data = data
        self._example: Path | None = None

    @property
    def folder(self) -> Path:
        """Where the teacher's lessons live; it may not exist before the first lesson."""
        chosen = self._config().get("lessons_folder")
        return Path(chosen) if isinstance(chosen, str) else documents_dir() / LESSONS_FOLDER

    def set_folder(self, folder: Path) -> None:
        """Keeps the lessons in `folder` from now on, creating it when it doesn't exist.

        The teacher's profile comes along when the new folder has none.
        """
        folder = folder.expanduser().absolute()
        folder.mkdir(parents=True, exist_ok=True)
        if self.profile_path.is_file() and not (folder / PROFILE_FILE).exists():
            shutil.copy(self.profile_path, folder / PROFILE_FILE)
        self._save_config({**self._config(), "lessons_folder": str(folder)})

    def lessons(self) -> list[LessonSummary]:
        """The lessons in the folder, the most recently edited first."""
        try:
            children = list(self.folder.iterdir())
        except OSError:
            return []
        summaries = [_summary(child) for child in children if _is_lesson(child)]
        return sorted(summaries, key=lambda lesson: lesson.edited, reverse=True)

    def lesson(self, name: str) -> Path | None:
        """The lesson called `name` in the folder, or None when there is none."""
        # A name comes from the address bar: never a path to elsewhere.
        if name in ("", ".", "..") or Path(name).name != name:
            return None
        path = self.folder / name
        return path if _is_lesson(path) else None

    def create(self, name: str) -> Path:
        """Creates a lesson called `name` from the scaffold, with the profile next to it
        and its first version, and returns its folder.

        Raises LessonNameError when `name` can't be used.
        """
        name = name.strip()
        problem = _name_error(name)
        if problem is None and (self.folder / name).exists():
            problem = "Já existe uma aula com esse nome."
        if problem is not None:
            raise LessonNameError(problem)
        self.folder.mkdir(parents=True, exist_ok=True)
        # The agent reads it one level above the lesson.
        if not self.profile_path.exists():
            shutil.copy(_DEFAULT_PROFILE, self.profile_path)
        lesson = self.folder / name
        lesson.mkdir()
        try:
            for template in _SCAFFOLD.iterdir():
                if template.is_file():
                    shutil.copy(template, lesson)
            (lesson / OUTPUT_DIR).mkdir()
        except BaseException:
            # Nothing of the teacher's is in it yet, and a half-made lesson would be listed.
            shutil.rmtree(lesson, ignore_errors=True)
            raise
        History.open(lesson)
        return lesson

    @property
    def profile_path(self) -> Path:
        """The teacher-wide profile, shared by every lesson in the folder."""
        return self.folder / PROFILE_FILE

    def profile(self) -> str:
        """The teacher's profile, or the one every teacher starts from before saving their own."""
        path = self.profile_path if self.profile_path.is_file() else _DEFAULT_PROFILE
        return path.read_text(encoding="utf-8")

    def save_profile(self, text: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        # newline="" keeps the teacher's line endings as typed.
        self.profile_path.write_text(text, encoding="utf-8", newline="")

    def example(self) -> Path:
        """The copy of the bundled example the teacher opens, so the original stays pristine.

        Made fresh the first time each Library is asked, which is once per launch.
        It lives in ManimFlow's folder, not in the lessons folder, so it never mixes
        with the teacher's lessons, and not in the temp folder, where Codex's Windows
        sandbox never lets the agent in.
        """
        if self._example is None:
            examples = self.data / "exemplo"
            shutil.rmtree(examples, ignore_errors=True)
            examples.mkdir(parents=True)
            # Its own profile, which the bundled CONTEXTO.md relies on.
            shutil.copy(_DEFAULT_PROFILE, examples)
            self._example = Path(shutil.copytree(_EXAMPLES / "relatividade", examples / EXAMPLE_NAME))
        return self._example

    def _config(self) -> dict:
        try:
            config = json.loads((self.data / _CONFIG).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return config if isinstance(config, dict) else {}

    def _save_config(self, config: dict) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / _CONFIG).write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _name_error(name: str) -> str | None:
    """Why `name` can't be a lesson folder's name on any system, or None when it can."""
    if not name:
        return "Dê um nome para a aula."
    if len(name) > _MAX_NAME:
        return f"Use um nome de até {_MAX_NAME} caracteres."
    if _FORBIDDEN.search(name):
        return 'O nome não pode ter estes caracteres: < > : " / \\ | ? *'
    if name.startswith(".") or name.endswith("."):
        return "O nome não pode começar nem terminar com ponto."
    if _RESERVED.fullmatch(name):
        return "Esse nome é reservado pelo Windows. Escolha outro."
    return None


def _is_lesson(path: Path) -> bool:
    # Other folders the teacher keeps next to the lessons are left out.
    return path.is_dir() and not path.name.startswith(".") and any(
        (path / name).is_file() for name in (PLAN_FILE, SCENES_FILE)
    )


def _summary(lesson: Path) -> LessonSummary:
    return LessonSummary(lesson.name, lesson, _edited(lesson), _state_count(lesson))


def _edited(lesson: Path) -> datetime:
    """When the teacher or the agent last changed one of the lesson's own files.

    Renders, caches and the history live in subfolders, so they don't count.
    """
    times = [
        path.stat().st_mtime for path in lesson.iterdir() if path.is_file() and not path.name.startswith(".")
    ]
    return datetime.fromtimestamp(max(times, default=lesson.stat().st_mtime))


def _state_count(lesson: Path) -> int | None:
    try:
        plan = yaml.safe_load((lesson / PLAN_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    states = plan.get("estados") if isinstance(plan, dict) else None
    return len(states) if isinstance(states, list) else None
