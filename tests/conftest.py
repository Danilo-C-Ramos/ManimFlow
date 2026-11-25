import json
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from manimflow.codex_agent import CodexAgent
from mock_model import MockModel

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = Path(str(files("manimflow"))) / "exemplos" / "relatividade"


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def report(self) -> dict:
        return json.loads(self.stdout)


def _manimflow_executable() -> str:
    scripts = Path(sysconfig.get_path("scripts"))
    name = "manimflow.exe" if sys.platform == "win32" else "manimflow"
    return str(scripts / name)


def run_manimflow(*args: str, env: dict[str, str] | None = None) -> Result:
    """Run the installed `manimflow` console script, as a user would, in `env` when given."""
    proc = subprocess.run(
        [_manimflow_executable(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        env=env,
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


@pytest.fixture
def manimflow():
    return run_manimflow


def preview(lesson: Path, *scenes: str) -> None:
    """Preview each scene, failing the test if any doesn't render."""
    for scene in scenes:
        result = run_manimflow("preview", str(lesson), scene)
        assert result.returncode == 0, result.stderr


@pytest.fixture
def lesson(tmp_path) -> Path:
    """A temporary copy of the minimal fixture lesson."""
    path = tmp_path / "Aula Mínima"
    shutil.copytree(FIXTURES / "aula_minima", path)
    return path


@pytest.fixture
def example(tmp_path) -> Path:
    """A temporary copy of the bundled relativity example lesson."""
    path = tmp_path / "Relatividade - herói e espelho"
    shutil.copytree(EXAMPLE, path)
    return path


@pytest.fixture
def mock_model():
    model = MockModel()
    yield model
    model.close()


@pytest.fixture
def codex_home(tmp_path, mock_model) -> Path:
    """ManimFlow's Codex home, pointed at the local mock model."""
    home = tmp_path / "codex"
    mock_model.configure(home)
    return home


@pytest.fixture
async def codex_agent(codex_home):
    agent = CodexAgent(codex_home)
    yield agent
    await agent.close()


def plan_scenes(lesson: Path) -> list[str]:
    """Every scene a lesson's plan uses, in plan order."""
    plan = yaml.safe_load((lesson / "plano.yaml").read_text(encoding="utf-8"))
    scenes = [item["cena"] for item in plan["estados"] + plan["transicoes"]]
    return list(dict.fromkeys(scenes))


@dataclass
class RenderedExample:
    path: Path
    previews: dict[str, Result]


@pytest.fixture(scope="session")
def rendered_example(tmp_path_factory) -> RenderedExample:
    """The bundled example with a preview of every scene in its plan, rendered once per run.

    Tests that change it work on their own copy (`rendered_example_copy`).
    """
    path = tmp_path_factory.mktemp("rendered") / "Relatividade - herói e espelho"
    shutil.copytree(EXAMPLE, path)
    previews = {scene: run_manimflow("preview", str(path), scene, "--json") for scene in plan_scenes(path)}
    return RenderedExample(path, previews)


@pytest.fixture
def rendered_example_copy(tmp_path, rendered_example) -> Path:
    path = tmp_path / rendered_example.path.name
    shutil.copytree(rendered_example.path, path)
    return path


def attached(received) -> dict[str, str]:
    """What a message carried besides the lesson's context, which goes with every message."""
    return {name: text for name, text in received.attachments.items() if name != "contexto-da-aula.md"}
