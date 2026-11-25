"""The lesson store: the teacher's lessons folder, the turmas and lessons in it, and the
bundled example.

The lessons live in `<Documents>/Aulas Manim` unless the teacher picks another
folder, and that choice is kept in ManimFlow's own folder. A turma is a folder of
lessons with a `turma.md` (ADR 0004). See docs/lessons.md.
"""

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from importlib.resources import files
from pathlib import Path

import yaml

from manimflow.paths import documents_dir
from manimflow.plan import PLAN_FILE, load_plan
from manimflow.render import OUTPUT_DIR, QUALITIES, SCENES_FILE
from manimflow.versioning import History, approval_file, plan_approved

LESSONS_FOLDER = "Aulas Manim"
PROFILE_FILE = "perfil.md"
# The turma's instructions, which the agent reads; also what makes a folder a turma.
TURMA_FILE = "turma.md"
# The turma's color, kept out of the teacher's sight.
_TURMA_META = ".turma.json"
# The flat colors a turma can take, by the name the teacher picks.
TURMA_COLORS = {
    "Azul": "#1d64d8",
    "Verde": "#16a34a",
    "Laranja": "#d9480f",
    "Roxo": "#7c3aed",
    "Turquesa": "#0d9488",
    "Rosa": "#db2777",
    "Âmbar": "#b45309",
    "Grafite": "#475569",
}
_NEW_TURMA_INSTRUCTIONS = (
    "# Instruções da turma\n\n"
    "Escreva aqui o que vale para todas as aulas desta turma: nível dos alunos, notação, livro-texto.\n"
)

_PACKAGE = Path(str(files("manimflow")))
# What a new lesson starts from: a plan with one placeholder state, and its empty scene.
_SCAFFOLD = _PACKAGE / "modelo"
# The scene of the scaffold's placeholder state, until the agent writes the plan.
PLACEHOLDER_SCENE: str = yaml.safe_load((_SCAFFOLD / PLAN_FILE).read_text(encoding="utf-8"))["estados"][0]["cena"]
_EXAMPLES = _PACKAGE / "exemplos"
# The example comes with a preview of every scene, so it shows its animations at once.
_PREVIEWS = Path(OUTPUT_DIR) / "previa"
EXAMPLE_NAME = "Relatividade - herói e espelho"
# The bundled example's profile is also every teacher's first one.
_DEFAULT_PROFILE = _EXAMPLES / PROFILE_FILE

_CONFIG = "config.json"
# Kept short so paths inside the lesson stay under Windows' 260-character limit.
_MAX_NAME = 80
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.IGNORECASE)


class LessonNameError(ValueError):
    """The name can't be a new lesson's or turma's; the message, in Portuguese, says why."""


class Status(Enum):
    """Where a lesson stands, read from its folder; the value is the teacher's word for it."""

    NEW = "Nova"
    PLAN = "Plano para aprovar"
    IN_PROGRESS = "Em produção"
    READY = "Pronta"
    EXPORTED = "Exportada"


@dataclass(frozen=True)
class Turma:
    name: str
    path: Path
    # A "#rrggbb" color.
    color: str


@dataclass(frozen=True)
class LessonSummary:
    name: str
    path: Path
    edited: datetime
    # None when plano.yaml is missing or has no list of states.
    states: int | None
    # The turma's name, None for a lesson directly in the lessons folder.
    turma: str | None = None

    @property
    def id(self) -> str:
        """The lesson's path inside the lessons folder, as its address names it."""
        return f"{self.turma}/{self.name}" if self.turma else self.name


class Library:
    def __init__(self, data: Path) -> None:
        """`data` is ManimFlow's own folder: the choice of lessons folder and the
        example's copy are kept there."""
        self.data = data

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

    def lessons(self, turma: str | None = None) -> list[LessonSummary]:
        """The lessons directly in the folder, or in the turma called `turma`, the most
        recently edited first."""
        folder = self.folder if turma is None else self.folder / turma
        try:
            children = list(folder.iterdir())
        except OSError:
            return []
        summaries = [_summary(child, turma) for child in children if _is_lesson(child)]
        return sorted(summaries, key=lambda lesson: lesson.edited, reverse=True)

    def all_lessons(self) -> list[LessonSummary]:
        """Every lesson, in a turma or not, the most recently edited first."""
        lessons = self.lessons() + [lesson for turma in self.turmas() for lesson in self.lessons(turma.name)]
        return sorted(lessons, key=lambda lesson: lesson.edited, reverse=True)

    def lesson(self, id: str) -> Path | None:
        """The lesson with this id (`Aula` or `Turma/Aula`), or None when there is none."""
        # An id comes from the address bar: never a path to elsewhere.
        parts = id.split("/")
        if len(parts) > 2 or any(not _plain_name(part) for part in parts):
            return None
        if len(parts) == 2 and self.turma(parts[0]) is None:
            return None
        path = self.folder.joinpath(*parts)
        return path if _is_lesson(path) else None

    def lesson_id(self, lesson: Path) -> str | None:
        """The id of the lesson folder `lesson`, None when it isn't in the lessons folder."""
        try:
            parts = lesson.relative_to(self.folder).parts
        except ValueError:
            return None
        return "/".join(parts) if 1 <= len(parts) <= 2 else None

    def turmas(self) -> list[Turma]:
        """The turmas in the folder, by name."""
        try:
            children = list(self.folder.iterdir())
        except OSError:
            return []
        turmas = [_turma(child) for child in children if _is_turma(child)]
        return sorted(turmas, key=lambda turma: turma.name.casefold())

    def turma(self, name: str) -> Turma | None:
        if not _plain_name(name):
            return None
        path = self.folder / name
        return _turma(path) if _is_turma(path) else None

    def turma_of(self, lesson: Path) -> Turma | None:
        """The turma the lesson folder is in, None when it has none."""
        return _turma(lesson.parent) if _is_turma(lesson.parent) else None

    def create_turma(self, name: str, color: str) -> Turma:
        """Creates a turma called `name` with a `#rrggbb` color and starter instructions.

        Raises LessonNameError when `name` can't be used.
        """
        name = name.strip()
        problem = _name_error(name, "turma")
        if problem is None and (self.folder / name).exists():
            problem = _taken(self.folder / name)
        if problem is not None:
            raise LessonNameError(problem)
        path = self.folder / name
        path.mkdir(parents=True)
        (path / TURMA_FILE).write_text(_NEW_TURMA_INSTRUCTIONS, encoding="utf-8")
        self.set_turma_color(name, color)
        self._ensure_profile()
        return _turma(path)

    def set_turma_color(self, name: str, color: str) -> None:
        (self.folder / name / _TURMA_META).write_text(json.dumps({"cor": color}), encoding="utf-8")

    def turma_instructions(self, name: str) -> str:
        return (self.folder / name / TURMA_FILE).read_text(encoding="utf-8")

    def save_turma_instructions(self, name: str, text: str) -> None:
        # newline="" keeps the teacher's line endings as typed.
        (self.folder / name / TURMA_FILE).write_text(text, encoding="utf-8", newline="")

    def create(self, name: str, turma: str | None = None) -> Path:
        """Creates a lesson called `name`, in the turma called `turma` when given, from the
        scaffold, with the profile in the lessons folder and its first version, and
        returns its folder.

        Raises LessonNameError when `name` can't be used.
        """
        name = name.strip()
        folder = self.folder if turma is None else self.folder / turma
        problem = _name_error(name)
        if problem is None and (folder / name).exists():
            problem = _taken(folder / name)
        if problem is not None:
            raise LessonNameError(problem)
        if turma is not None and self.turma(turma) is None:
            raise LessonNameError("Essa turma não existe mais.")
        folder.mkdir(parents=True, exist_ok=True)
        self._ensure_profile()
        lesson = folder / name
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

    def free_name(self, text: str, turma: str | None = None) -> str:
        """A lesson name made from the start of `text`, such as the teacher's first
        message, that no folder in the turma has yet."""
        words = " ".join(_FORBIDDEN.sub(" ", text).split()).strip(" .")
        base = words[:60].rsplit(" ", 1)[0] if len(words) > 60 else words
        base = base.strip(" .") or "Nova aula"
        if _RESERVED.fullmatch(base):
            base = f"Aula {base}"
        folder = self.folder if turma is None else self.folder / turma
        name, number = base, 2
        while (folder / name).exists():
            name, number = f"{base} ({number})", number + 1
        return name

    def _ensure_profile(self) -> None:
        # The agent reads it above the lesson, so it must exist before the first one.
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self.profile_path.exists():
            shutil.copy(_DEFAULT_PROFILE, self.profile_path)

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

        Made the first time it is needed, then kept, with the teacher's changes and their
        history, as any lesson is. It lives in ManimFlow's folder, not in the lessons
        folder, so it never mixes with the teacher's lessons, and not in the temp folder,
        where Codex's Windows sandbox never lets the agent in.
        """
        examples = self.data / "exemplo"
        example = examples / EXAMPLE_NAME
        if not (examples / PROFILE_FILE).is_file() or not _is_lesson(example):
            self._copy_example()
        else:
            # A copy made before the previews came with the example gets the ones it lacks;
            # what the teacher rendered since is newer, and the preview shows the newest.
            _add_missing(_EXAMPLES / "relatividade" / _PREVIEWS, example / _PREVIEWS)
        if not approval_file(example).exists():
            # Its plan was agreed long ago: it doesn't wait for the teacher's approval,
            # also in a copy made before approvals were recorded.
            History.open(example).approve_plan()
        return example

    def reset_example(self) -> Path:
        """Brings the example's copy back to the bundled original, dropping the teacher's
        changes and their history."""
        self._copy_example()
        return self.example()

    def _copy_example(self) -> None:
        examples = self.data / "exemplo"
        # Copied aside and then moved in, so a copy cut short is never taken for the example.
        staging = self.data / "exemplo.novo"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        # Its own profile, which the bundled CONTEXTO.md relies on.
        shutil.copy(_DEFAULT_PROFILE, staging)
        shutil.copytree(_EXAMPLES / "relatividade", staging / EXAMPLE_NAME)
        shutil.rmtree(examples, ignore_errors=True)
        staging.rename(examples)

    def _config(self) -> dict:
        try:
            config = json.loads((self.data / _CONFIG).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return config if isinstance(config, dict) else {}

    def _save_config(self, config: dict) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / _CONFIG).write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _add_missing(source: Path, target: Path) -> None:
    """Copies the files of `source` that `target` lacks, dated long ago, so a render the
    teacher made before stays the newest of its scene."""
    for path in source.rglob("*"):
        copy = target / path.relative_to(source)
        if path.is_file() and not copy.exists():
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, copy)
            # Not 0, which the status reads as "never rendered".
            os.utime(copy, (1, 1))


def _name_error(name: str, what: str = "aula") -> str | None:
    """Why `name` can't be a lesson's or turma's folder name on any system, or None when it can."""
    if not name:
        return f"Dê um nome para a {what}."
    if len(name) > _MAX_NAME:
        return f"Use um nome de até {_MAX_NAME} caracteres."
    if _FORBIDDEN.search(name):
        return 'O nome não pode ter estes caracteres: < > : " / \\ | ? *'
    if name.startswith(".") or name.endswith("."):
        return "O nome não pode começar nem terminar com ponto."
    if _RESERVED.fullmatch(name):
        return "Esse nome é reservado pelo Windows. Escolha outro."
    return None


def _taken(path: Path) -> str:
    if _is_turma(path):
        return "Já existe uma turma com esse nome."
    if _is_lesson(path):
        return "Já existe uma aula com esse nome."
    return "Já existe uma pasta com esse nome."


def _plain_name(name: str) -> bool:
    return name not in ("", ".", "..") and Path(name).name == name and "\\" not in name


def _is_lesson(path: Path) -> bool:
    # Other folders the teacher keeps next to the lessons are left out.
    return path.is_dir() and not path.name.startswith(".") and any(
        (path / name).is_file() for name in (PLAN_FILE, SCENES_FILE)
    )


def _is_turma(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith(".") and (path / TURMA_FILE).is_file() and not _is_lesson(path)


def _turma(path: Path) -> Turma:
    try:
        color = json.loads((path / _TURMA_META).read_text(encoding="utf-8")).get("cor")
    except (OSError, ValueError, AttributeError):
        color = None
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        # Stable across launches, unlike hash().
        palette = list(TURMA_COLORS.values())
        color = palette[int(hashlib.sha256(path.name.encode()).hexdigest(), 16) % len(palette)]
    return Turma(path.name, path, color)


def profile_of(lesson: Path) -> Path:
    """The teacher's profile a lesson follows: in the lessons folder, one level up, or
    two inside a turma."""
    return lesson.parent.parent / PROFILE_FILE if _is_turma(lesson.parent) else lesson.parent / PROFILE_FILE


def _summary(lesson: Path, turma: str | None = None) -> LessonSummary:
    return LessonSummary(lesson.name, lesson, _edited(lesson), _state_count(lesson), turma)


_statuses: dict[Path, tuple[tuple[int, ...], Status]] = {}


def status(lesson: Path) -> Status:
    """Where the lesson stands, from its folder alone.

    The plan waits for the teacher when it isn't the one they last approved and nothing
    was rendered since it changed: the agent wrote it and stopped, or the teacher edited it.
    Read again only when one of the files it depends on changes, since the sidebar asks
    every few seconds.
    """
    output = lesson / OUTPUT_DIR
    folders = [output]
    for parent in (output, output / "previa"):
        try:
            folders += [child for child in parent.iterdir() if child.is_dir()]
        except OSError:
            pass
    stamp = tuple(_modified(path) for path in (lesson / PLAN_FILE, lesson / SCENES_FILE, approval_file(lesson), *folders))
    cached = _statuses.get(lesson)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    current = _status(lesson)
    _statuses[lesson] = (stamp, current)
    return current


def _status(lesson: Path) -> Status:
    plan, _ = load_plan(lesson)
    if plan is None or _is_placeholder(plan.states, plan.transitions):
        return Status.NEW
    renders = [
        _modified(lesson / folder / extension / f"{scene}.{extension}")
        for _, folder in QUALITIES.values()
        for scenes, extension in (
            ([state.scene for state in plan.states], "png"),
            ([transition.scene for transition in plan.transitions], "mp4"),
        )
        for scene in scenes
    ]
    newest_render = max(renders, default=0)
    if newest_render < _modified(lesson / PLAN_FILE) and not plan_approved(lesson):
        return Status.PLAN
    rendered = all(
        any(_modified(lesson / folder / "png" / f"{state.scene}.png") for _, folder in QUALITIES.values())
        for state in plan.states
    )
    if not rendered:
        return Status.IN_PROGRESS
    exported = [
        _modified(path)
        for path in (lesson / OUTPUT_DIR).glob("*/*")
        if path.parent.name not in ("previa", "png", "mp4") and path.is_file()
    ]
    return Status.EXPORTED if max(exported, default=0) > newest_render else Status.READY


def _is_placeholder(states: list, transitions: list) -> bool:
    """Whether the plan is still the new lesson's placeholder: no transitions, and every
    state, the teacher's added ones too, on the scaffold's empty scene."""
    return not transitions and all(state.scene == PLACEHOLDER_SCENE for state in states)


def _modified(path: Path) -> int:
    """The file's modification time in nanoseconds, 0 when it doesn't exist."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _edited(lesson: Path) -> datetime:
    """When the teacher or the agent last changed one of the lesson's own files.

    Renders, caches and the history live in subfolders, so they don't count.
    """
    times = [
        path.stat().st_mtime for path in lesson.iterdir() if path.is_file() and not path.name.startswith(".")
    ]
    return datetime.fromtimestamp(max(times, default=lesson.stat().st_mtime))


_state_counts: dict[Path, tuple[int, int | None]] = {}


def _state_count(lesson: Path) -> int | None:
    """The number of states in the plan, read again only when the plan changes: the
    sidebar lists every lesson every few seconds."""
    path = lesson / PLAN_FILE
    stamp = _modified(path)
    cached = _state_counts.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    count = _read_state_count(lesson)
    _state_counts[path] = (stamp, count)
    return count


def _read_state_count(lesson: Path) -> int | None:
    try:
        plan = yaml.safe_load((lesson / PLAN_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    states = plan.get("estados") if isinstance(plan, dict) else None
    return len(states) if isinstance(states, list) else None
