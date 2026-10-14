import subprocess
import sys

import pytest
import yaml

from conftest import EXAMPLE


def plan_scenes() -> list[str]:
    plan = yaml.safe_load((EXAMPLE / "plano.yaml").read_text(encoding="utf-8"))
    scenes = [item["cena"] for item in plan["estados"] + plan["transicoes"]]
    return list(dict.fromkeys(scenes))


def test_example_ships_the_lesson_layout_and_a_profile():
    for name in ["CONTEXTO.md", "plano.yaml", "fisica.py", "cenas.py", "test_fisica.py"]:
        assert (EXAMPLE / name).is_file(), name
    # The profile is teacher-wide, so it sits one level above the lesson, as in "Aulas Manim/".
    assert (EXAMPLE.parent / "perfil.md").is_file()


def test_example_plan_is_valid(manimflow, example):
    result = manimflow("plan", "validate", str(example), "--json")

    assert result.returncode == 0, result.stdout
    assert result.report["ok"] is True


def test_example_physics_tests_pass(example):
    # The lesson's own tests, run from its folder as the agent will run them.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_fisica.py"],
        cwd=example,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert " passed" in result.stdout


@pytest.mark.parametrize("scene", plan_scenes())
def test_every_scene_in_the_example_plan_renders(manimflow, example, scene):
    result = manimflow("preview", str(example), scene, "--json")

    assert result.returncode == 0, result.report["manim_output"]
    assert (example / "saida" / "previa" / "png" / f"{scene}.png").is_file()
