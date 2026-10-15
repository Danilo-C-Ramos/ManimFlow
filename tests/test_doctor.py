import os
import shutil
from pathlib import Path

import pytest

LATEX_PROGRAMS = ("latex", "kpsewhich", "dvisvgm", "tlmgr")


def without_system_latex() -> dict[str, str]:
    """This environment with a PATH that leaves out every folder with a LaTeX program."""
    path = os.pathsep.join(
        folder
        for folder in os.environ.get("PATH", "").split(os.pathsep)
        if not any(shutil.which(program, path=folder) for program in LATEX_PROGRAMS)
    )
    return {**os.environ, "PATH": path}


def without_latex(data_dir) -> dict[str, str]:
    """An environment with no LaTeX at all: ManimFlow's data folder is `data_dir`, with no
    TinyTeX in it, and the PATH has no LaTeX either."""
    return {**without_system_latex(), "XDG_DATA_HOME": str(data_dir), "LOCALAPPDATA": str(data_dir)}


def checks_by_name(report: dict) -> dict[str, dict]:
    return {check["name"]: check for check in report["checks"]}


def test_check_reports_missing_latex_in_portuguese_and_fails(manimflow, tmp_path):
    result = manimflow("doctor", "--json", env=without_latex(tmp_path))

    assert result.returncode == 1
    report = result.report
    assert report["ok"] is False
    assert report["command"] == "doctor"
    checks = checks_by_name(report)
    for name in ("latex", "dvisvgm", "latex-packages"):
        assert checks[name]["ok"] is False
        assert "manimflow doctor --install" in checks[name]["message"]
    assert "não encontrado" in checks["latex"]["message"]
    assert "physics" in checks["latex-packages"]["missing"]
    # The Python render stack ships with ManimFlow, so it is there.
    for name in ("manim", "pycairo", "manimpango", "pyav"):
        assert checks[name]["ok"] is True, checks[name]["message"]


def test_check_prints_each_dependency_with_its_explanation(manimflow, tmp_path):
    result = manimflow("doctor", env=without_latex(tmp_path))

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert any(line.startswith("falta") and "LaTeX não encontrado" in line for line in lines)
    assert any(line.startswith("ok") and "manim" in line for line in lines)


@pytest.fixture
def tinytex(manimflow) -> Path:
    """ManimFlow's own TinyTeX, which CI installs with `manimflow doctor --install` before the
    tests run."""
    report = manimflow("doctor", "--json").report
    root = Path(report["tinytex"])
    latex = checks_by_name(report)["latex"]["path"]
    if not (latex and Path(latex).is_relative_to(root)):
        message = "ManimFlow's TinyTeX isn't installed: run `manimflow doctor --install`"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    return root


def test_check_passes_once_tinytex_is_installed(manimflow, tinytex):
    result = manimflow("doctor", "--json")

    assert result.returncode == 0, result.stdout
    report = result.report
    assert report["ok"] is True
    assert all(check["ok"] for check in report["checks"])
    assert Path(checks_by_name(report)["dvisvgm"]["path"]).is_relative_to(tinytex)


def tree(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under `root`, with its size and modification time."""
    return {
        str(path.relative_to(root)): (path.lstat().st_size, path.lstat().st_mtime_ns)
        for path in root.rglob("*")
    }


def test_install_again_changes_nothing(manimflow, tinytex):
    before = tree(tinytex)

    result = manimflow("doctor", "--install", "--json")

    assert result.returncode == 0, result.stderr
    assert result.report["installed"] == []
    assert result.report["ok"] is True
    assert tree(tinytex) == before


MATH_SCENE = """from manim import MathTex, Scene


class Formula(Scene):
    def construct(self):
        self.add(MathTex(r"\\gamma = \\frac{1}{\\sqrt{1 - v^2/c^2}}"))
"""


def test_math_renders_with_tinytex_alone(manimflow, tinytex, tmp_path):
    lesson = tmp_path / "Aula com Fórmula"
    lesson.mkdir()
    (lesson / "cenas.py").write_text(MATH_SCENE, encoding="utf-8")

    result = manimflow("preview", str(lesson), "Formula", env=without_system_latex())

    assert result.returncode == 0, result.stderr
    assert (lesson / "saida" / "previa" / "png" / "Formula.png").is_file()
