"""The plan turn: until the teacher first approves a lesson's plan, ManimFlow asks the agent
for the plan in a fixed format and writes plano.yaml itself.

A model that follows long instructions loosely, as GPT-6 Luna on ChatGPT Free does, used
to describe the plan in the chat without writing it, so the approval never showed up. In
a plan turn the agent's last text must be the plan, as JSON (Codex's `output_schema`),
with the teacher's files in the message, so it needs no tool at all. See docs/plan.md.
"""

import ast
import json
import logging
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml

from manimflow.lessons import PLACEHOLDER_SCENE, PROFILE_FILE, TURMA_FILE, Status, status
from manimflow.plan import PLAN_FILE, load_plan, validate_plan
from manimflow.render import SCENES_FILE, cache_dir
from manimflow.versioning import approval_file

logger = logging.getLogger(__name__)

# The attachment that asks for the plan, written for each plan turn.
BRIEF = "pedido-de-plano.md"
# The attachment that goes with an approval: make the whole lesson now.
GO_AHEAD = "plano-aprovado.md"
CONTEXT_FILE = "CONTEXTO.md"

_TEXT = {"type": "string"}
_STATE = {
    "type": "object",
    "properties": {
        "id": {**_TEXT, "description": "S0, S1, S2... na ordem dos slides."},
        "titulo": {**_TEXT, "description": "Duas a quatro palavras."},
        "visivel": {**_TEXT, "description": "O que a imagem deste estado mostra, para o professor."},
        "cena": {**_TEXT, "description": "A classe de cena cujo último quadro é esta imagem, como S0_Eixos."},
    },
    "required": ["id", "titulo", "visivel", "cena"],
    "additionalProperties": False,
}
_TRANSITION = {
    "type": "object",
    "properties": {
        "de": _TEXT,
        "para": _TEXT,
        "descricao": {**_TEXT, "description": "O que o vídeo entre os dois estados faz."},
        "duracao": {"type": "number", "description": "Segundos, aproximados."},
        "cena": {**_TEXT, "description": "A classe de cena do vídeo, que termina na imagem de `para`."},
    },
    "required": ["de", "para", "descricao", "duracao", "cena"],
    "additionalProperties": False,
}
SCHEMA: dict = {
    "type": "object",
    "properties": {
        "mensagem": {**_TEXT, "description": "Duas ou três frases para o professor, em português."},
        "plano": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "estados": {"type": "array", "items": _STATE},
                        "transicoes": {"type": "array", "items": _TRANSITION},
                    },
                    "required": ["estados", "transicoes"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
        "aprovado": {"type": "boolean"},
    },
    "required": ["mensagem", "plano", "aprovado"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """# Pedido de plano (do ManimFlow)

Esta aula ainda não tem um plano aprovado pelo professor. Neste turno você só combina o plano: não escreva arquivos, não rode comandos e não escreva código. O ManimFlow grava o `plano.yaml` com a sua resposta e mostra o plano ao professor em cartões, com o botão de aprovar.

Responda só no formato pedido:

- `plano`: o plano completo, do zero ou com as mudanças que o professor pediu. Estados na ordem dos slides, com ids S0, S1, S2...; cada transição liga um estado ao seguinte, com a duração aproximada em segundos. Os nomes de cena são classes Python: letras sem acento, números e _, sem começar por número, como S0_Eixos ou T01_Viagem. Um estado e a transição que chega nele podem usar a mesma cena, cujo último quadro é a imagem do estado. Use `null` quando a mensagem do professor não pede uma animação nem uma mudança no plano, como uma pergunta.
- `mensagem`: duas ou três frases para o professor, em português, sobre o plano ou a resposta à pergunta dele. Não fale de botões nem de arquivos.
- `aprovado`: `true` só quando o professor aprova o plano atual como está ("pode seguir", "aprovado", "está bom"), sem pedir mudanças; nesse caso, `plano` é `null`. Não comece a animação neste turno: o ManimFlow manda a aprovação em seguida, e você anima no próximo turno.

Siga o perfil do professor, as instruções da turma e o contexto da aula abaixo, nesta ordem, do mais geral ao mais específico. Os `comentarios` no plano atual são notas do professor sobre cada estado: atenda todas no plano que você devolver.
"""


# GPT-6 Luna answered a bare approval with what it would do, and ended the turn; with
# these steps in the message it made the lesson in the same turn.
_GO_AHEAD = """# Plano aprovado: hora de animar (do ManimFlow)

O professor aprovou o plano, e o ManimFlow já registrou a aprovação. Neste turno, faça a aula inteira, sem parar para perguntar nem para anunciar o que vai fazer:

1. Escreva a física em `fisica.py`, com `equacoes()`, e os testes em `test_fisica.py`.
2. Desenhe em `cenas.py` cada cena que o plano nomeia.
3. Rode o ciclo de conferência do skill `manimflow`: `manimflow plan validate .`, os testes de física, `manimflow preview . <Cena>` para cada cena, `manimflow check-continuity .`, e olhe os quadros.
4. Registre no `CONTEXTO.md` o que ficou combinado.

Só termine o turno quando as prévias estiverem renderizadas e conferidas, ou depois da 4ª tentativa, dizendo o que falta.
"""


@dataclass(frozen=True)
class PlanReply:
    message: str
    # The plan as the agent wrote it, None when the message asked for no plan.
    plan: dict | None
    approved: bool


def pending(lesson: Path) -> bool:
    """Whether a message to this lesson asks for the plan: the teacher never approved one,
    and the plan is the scaffold's placeholder or waits for the first approval."""
    if approval_file(lesson).exists():
        return False
    plan, _ = load_plan(lesson)
    if plan is None:
        return False
    placeholder = not plan.transitions and all(state.scene == PLACEHOLDER_SCENE for state in plan.states)
    return placeholder or status(lesson) == Status.PLAN


def brief(lesson: Path) -> Path:
    """Writes the attachment that asks for the plan, with the files the agent would read."""
    sections = [_INSTRUCTIONS]
    for title, path in [
        ("Perfil do professor", _profile(lesson)),
        ("Instruções da turma", lesson.parent / TURMA_FILE),
        (f"Contexto da aula ({CONTEXT_FILE})", lesson / CONTEXT_FILE),
        (f"Plano atual ({PLAN_FILE})", lesson / PLAN_FILE),
    ]:
        if path is not None and (text := _read(path)):
            sections.append(f"## {title}\n\n{text.strip()}\n")
    attachment = cache_dir(lesson) / BRIEF
    attachment.write_text("\n".join(sections), encoding="utf-8")
    return attachment


def go_ahead(lesson: Path) -> Path:
    """Writes the attachment that goes with the teacher's approval."""
    attachment = cache_dir(lesson) / GO_AHEAD
    attachment.write_text(_GO_AHEAD, encoding="utf-8")
    return attachment


def parse(text: str) -> PlanReply | None:
    """The plan turn's answer in the agent's text, None when the text is something else."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("mensagem"), str):
        return None
    plan = data.get("plano")
    return PlanReply(data["mensagem"], plan if isinstance(plan, dict) else None, data.get("aprovado") is True)


def apply(lesson: Path, reply: PlanReply) -> list[str]:
    """Writes the reply's plan to plano.yaml, with an empty scene in cenas.py for each scene
    it names that the file lacks. Returns why it couldn't, in Portuguese; then the lesson's
    files stay as they were."""
    if reply.plan is None:
        return []
    plan_path, scenes_path = lesson / PLAN_FILE, lesson / SCENES_FILE
    # As bytes, so a restore keeps the files' own line endings.
    before = {path: path.read_bytes() if path.is_file() else None for path in (plan_path, scenes_path)}
    plan = {
        "estados": [_only(state, ("id", "titulo", "visivel", "cena")) for state in reply.plan.get("estados") or []],
        "transicoes": [
            _only(transition, ("de", "para", "descricao", "duracao", "cena"))
            for transition in reply.plan.get("transicoes") or []
        ],
    }
    plan_path.write_text(_HEADER + yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
    scenes = [item["cena"] for item in plan["estados"] + plan["transicoes"] if isinstance(item.get("cena"), str)]
    _add_scenes(scenes_path, list(dict.fromkeys(scenes)), fresh=_read(scenes_path) == _read(_SCAFFOLD_SCENES))
    report = validate_plan(lesson)
    if report.ok:
        return []
    for path, data in before.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(data)
    return report.errors


_HEADER = "# Os estados da aula na ordem dos slides e as transições entre eles.\n"
_SCAFFOLD_SCENES = Path(str(files("manimflow"))) / "modelo" / SCENES_FILE
_SCENES_HEADER = '"""Cenas da aula, na ordem da apresentação. Só desenho: todo número vem de fisica.py."""\n\nimport manim\n'
# With its own base, so it works in a file that imports Manim another way.
_EMPTY_SCENE = '''

class {name}(manim.Scene):
    """Ainda vazia: o agente desenha esta cena depois que o plano for aprovado."""

    def construct(self):
        pass
'''


def _add_scenes(path: Path, scenes: list[str], fresh: bool) -> None:
    """Adds an empty scene for each of `scenes` that the file lacks; with `fresh`, the file
    is the untouched scaffold, and starts over."""
    text = _SCENES_HEADER if fresh else (_read(path) or _SCENES_HEADER)
    known = set(_classes(text))
    missing = [name for name in scenes if name not in known and name.isidentifier()]
    # Only a plain `import manim` binds the name the stubs use.
    if missing and not re.search(r"^import manim[ \t]*(#.*)?$", text, re.MULTILINE):
        text += "\n\nimport manim\n"
    text += "".join(_EMPTY_SCENE.format(name=name) for name in missing)
    path.write_text(text, encoding="utf-8")


def _classes(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]


def _only(item: object, keys: tuple[str, ...]) -> dict:
    return {key: item.get(key) for key in keys} if isinstance(item, dict) else {}


def _profile(lesson: Path) -> Path | None:
    for folder in (lesson.parent, lesson.parent.parent):
        if (folder / PROFILE_FILE).is_file():
            return folder / PROFILE_FILE
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
