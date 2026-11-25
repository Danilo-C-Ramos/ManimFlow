"""The package that PyPI serves, built the way the release workflow builds it."""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture(scope="module")
def tagged_wheel(tmp_path_factory) -> Path:
    """Builds a wheel from a copy of this working tree, committed and tagged `v0.0.7`."""
    copy = _copy(tmp_path_factory.mktemp("repo"))
    _git(copy, "init", "--quiet")
    _git(copy, "add", "--all")
    _git(copy, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "release")
    _git(copy, "tag", "v0.0.7")
    return _build(copy)


def _copy(folder: Path) -> Path:
    """Copies this working tree's files into `folder`, without git."""
    if shutil.which("uv") is None:
        pytest.skip("building the package needs uv")
    tracked = _git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    for name in filter(None, tracked.split("\0")):
        source = REPO / name
        if source.is_file():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, folder / name)
    return folder


def _build(folder: Path) -> Path:
    out = folder / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=folder,
        check=True,
        capture_output=True,
    )
    (wheel,) = out.glob("*.whl")
    return wheel


def test_the_version_comes_from_the_tag(tagged_wheel):
    assert tagged_wheel.name == "manimflow-0.0.7-py3-none-any.whl"


def test_a_copy_without_git_builds(tmp_path):
    # GitHub's "Download ZIP" has no .git, and the README installs from it.
    assert _build(_copy(tmp_path)).name == "manimflow-0.0.0-py3-none-any.whl"


def test_the_wheel_ships_every_file_of_the_package(tagged_wheel):
    # The bundled example, the agent's instructions and the AppArmor profile aren't
    # Python modules, and `uvx manimflow` needs them all.
    package = _git(REPO, "ls-files", "src/manimflow").split()
    expected = {name.removeprefix("src/") for name in package}

    with zipfile.ZipFile(tagged_wheel) as wheel:
        shipped = set(wheel.namelist())

    assert expected <= shipped
    assert "manimflow/exemplos/relatividade/plano.yaml" in shipped


def test_the_wheel_installs_the_manimflow_command(tagged_wheel):
    with zipfile.ZipFile(tagged_wheel) as wheel:
        (entry_points,) = [n for n in wheel.namelist() if n.endswith(".dist-info/entry_points.txt")]
        text = wheel.read(entry_points).decode()

    assert "manimflow = manimflow.cli:main" in text


def test_uvx_runs_the_tagged_release(tagged_wheel):
    # What a teacher types, with the wheel standing in for PyPI.
    result = subprocess.run(
        ["uvx", "--from", str(tagged_wheel), "manimflow", "--version"],
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "manimflow 0.0.7"
