import json
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import pytest

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


@pytest.fixture
def manimflow():
    """Run the installed `manimflow` console script, as a user would."""

    def run(*args: str) -> Result:
        proc = subprocess.run(
            [_manimflow_executable(), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        return Result(proc.returncode, proc.stdout, proc.stderr)

    return run


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
