"""Validates a lesson's plan file (plano.yaml): its states and the transitions between them.

The schema is documented in docs/plan.md. Errors are in Portuguese because the
teacher reads them.
"""

import ast
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manimflow.render import SCENES_FILE, scene_name_error

PLAN_FILE = "plano.yaml"

_STATE_FIELDS = ("id", "titulo", "visivel", "cena")
_TRANSITION_FIELDS = ("de", "para", "descricao", "duracao", "cena")


@dataclass
class PlanReport:
    lesson: Path
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "plan validate",
            "lesson": str(self.lesson),
            "errors": self.errors,
        }


@dataclass(frozen=True)
class State:
    id: str
    scene: str
    title: str


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    scene: str


@dataclass(frozen=True)
class Plan:
    states: list[State]
    transitions: list[Transition]


def validate_plan(lesson: Path) -> PlanReport:
    """Checks the lesson's plano.yaml against the schema and the lesson's scenes file."""
    report = PlanReport(lesson=lesson.absolute())
    report.errors = _plan_errors(report.lesson)
    return report


def load_plan(lesson: Path) -> tuple[Plan | None, list[str]]:
    """The lesson's plan, or None with the validation errors when it isn't valid."""
    report = validate_plan(lesson)
    if not report.ok:
        return None, report.errors
    plan = yaml.safe_load((report.lesson / PLAN_FILE).read_text(encoding="utf-8"))
    states = [State(item["id"], item["cena"], item["titulo"]) for item in plan["estados"]]
    transitions = [Transition(item["de"], item["para"], item["cena"]) for item in plan.get("transicoes") or []]
    return Plan(states, transitions), []


def _plan_errors(lesson: Path) -> list[str]:
    if not lesson.is_dir():
        return [f"Não encontrei a pasta da aula {lesson}."]
    plan_path = lesson / PLAN_FILE
    if not plan_path.is_file():
        return [f"Não encontrei o {PLAN_FILE} na pasta da aula {lesson}."]
    errors: list[str] = []
    text = _read_text(plan_path, errors)
    if text is None:
        return errors
    try:
        plan = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return [f"O {PLAN_FILE} não é um YAML válido: {error}"]
    if plan is None:
        plan = {}
    if not isinstance(plan, dict):
        return [f'O {PLAN_FILE} precisa ter a lista "estados" e, se houver, a lista "transicoes".']

    states = _items(plan, "estados", errors, required=True)
    transitions = _items(plan, "transicoes", errors, required=False)
    scenes = _lesson_scenes(lesson / SCENES_FILE, errors)

    # Every id the plan mentions, even on a broken state, so its transitions aren't
    # reported as pointing nowhere; and the positions of the usable ones, to check
    # that each transition joins neighbours.
    declared = {state["id"] for state in states if isinstance(state.get("id"), str)}
    position: dict[str, int] = {}
    for index, state in enumerate(states, start=1):
        where = f"Estado {state['id']}" if isinstance(state.get("id"), str) else f"Estado {index}"
        if not _check_fields(state, _STATE_FIELDS, where, errors):
            continue
        if scene_name_error(state["id"]):
            errors.append(
                f'{where}: "{state["id"]}" não serve como id de estado. Use um nome simples, como S0 '
                "ou S2b: letras sem acento, números e _, sem começar por número."
            )
        elif state["id"] in position:
            errors.append(f'Há mais de um estado com o id "{state["id"]}".')
        else:
            position[state["id"]] = index
        _check_scene(state["cena"], scenes, where, errors)
        comments = state.get("comentarios", [])
        if not (isinstance(comments, list) and all(isinstance(c, str) for c in comments)):
            errors.append(f'{where}: "comentarios" precisa ser uma lista de textos.')

    pairs: set[tuple[str, str]] = set()
    for index, transition in enumerate(transitions, start=1):
        named = all(isinstance(transition.get(end), str) for end in ("de", "para"))
        where = f"Transição {transition['de']} → {transition['para']}" if named else f"Transição {index}"
        if not _check_fields(transition, _TRANSITION_FIELDS, where, errors):
            continue
        source: str = transition["de"]
        target: str = transition["para"]
        for end in (source, target):
            if end not in declared:
                errors.append(f'{where}: o estado "{end}" não existe no plano.')
        if source in position and target in position and position[target] != position[source] + 1:
            errors.append(
                f"{where}: {target} não vem logo depois de {source} no plano. "
                "Uma transição liga um estado ao seguinte."
            )
        if (source, target) in pairs:
            errors.append(f"Há mais de uma transição de {source} para {target}.")
        pairs.add((source, target))
        _check_scene(transition["cena"], scenes, where, errors)
    return errors


def _read_text(path: Path, errors: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"O {path.name} não está em UTF-8. Salve o arquivo de novo com a codificação UTF-8.")
        return None


def _items(plan: dict, key: str, errors: list[str], required: bool) -> list[dict]:
    """The list under `key`, keeping only its entries that are mappings."""
    items = plan.get(key)
    if items is None:
        if required:
            errors.append(f'Falta a lista "{key}" no {PLAN_FILE}.')
        return []
    if not isinstance(items, list):
        errors.append(f'"{key}" precisa ser uma lista.')
        return []
    if required and not items:
        errors.append(f'A lista "{key}" precisa ter pelo menos um item.')
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f'O item {index} de "{key}" precisa ter campos, como "id" ou "cena".')
    return [item for item in items if isinstance(item, dict)]


def _check_fields(item: dict, fields: tuple[str, ...], where: str, errors: list[str]) -> bool:
    """Reports missing or mistyped fields; True when the item can be checked further."""
    complete = True
    for name in fields:
        value: Any = item.get(name)
        if value is None or value == "":
            errors.append(f'{where}: falta o campo "{name}".')
            complete = False
        elif name == "duracao":
            number = isinstance(value, (int, float)) and not isinstance(value, bool)
            if not (number and math.isfinite(value) and value > 0):
                errors.append(f'{where}: "{name}" precisa ser um número de segundos maior que zero.')
        elif not isinstance(value, str):
            errors.append(f'{where}: "{name}" precisa ser um texto.')
            complete = False
    return complete


@dataclass
class _Scenes:
    """The top-level classes of a scenes file, and which of them are Manim scenes."""

    classes: set[str]
    scenes: set[str]


def _check_scene(scene: str, found: _Scenes | None, where: str, errors: list[str]) -> None:
    if scene_name_error(scene):
        errors.append(
            f'{where}: "{scene}" não serve como nome de cena. '
            "Use o nome de uma classe de cena, como S0 ou T01."
        )
    elif found is None or scene in found.scenes:
        return
    elif scene in found.classes:
        errors.append(f'{where}: a classe "{scene}" de {SCENES_FILE} não é uma cena.')
    else:
        errors.append(f'{where}: a cena "{scene}" não existe em {SCENES_FILE}.')


def _lesson_scenes(scenes_file: Path, errors: list[str]) -> _Scenes | None:
    """Reads the scenes file without running it. None when it can't be read, after reporting why.

    A class is a scene when one of its bases is named like a Manim scene (Scene,
    MovingCameraScene, ...) or is itself a scene of this file.
    """
    if not scenes_file.is_file():
        errors.append(f"Não encontrei o {SCENES_FILE}, então não deu para conferir as cenas.")
        return None
    text = _read_text(scenes_file, errors)
    if text is None:
        return None
    try:
        tree = ast.parse(text, filename=scenes_file.name)
    except SyntaxError as error:
        line = f" na linha {error.lineno}" if error.lineno else ""
        errors.append(f"O {SCENES_FILE} tem um erro de sintaxe{line}, então não deu para conferir as cenas.")
        return None

    bases = {
        node.name: [_base_name(base) for base in node.bases]
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    scenes: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, names in bases.items():
            if name not in scenes and any(b.endswith("Scene") or b in scenes for b in names):
                scenes.add(name)
                changed = True
    return _Scenes(classes=set(bases), scenes=scenes)


def _base_name(base: ast.expr) -> str:
    """`Scene` for both `Scene` and `manim.Scene`; empty for anything else."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return ""
