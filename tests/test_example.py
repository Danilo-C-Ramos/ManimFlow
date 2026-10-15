import subprocess
import sys

import pytest

from conftest import EXAMPLE, plan_scenes


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


@pytest.mark.parametrize("scene", plan_scenes(EXAMPLE))
def test_every_scene_in_the_example_plan_renders(rendered_example, scene):
    result = rendered_example.previews[scene]

    assert result.returncode == 0, result.report["manim_output"]
    assert (rendered_example.path / "saida" / "previa" / "png" / f"{scene}.png").is_file()


def test_example_transitions_are_continuous(manimflow, rendered_example_copy):
    result = manimflow("check-continuity", str(rendered_example_copy), "--json")

    assert result.returncode == 0, result.stdout
    report = result.report
    # Seven transitions, each checked at both ends.
    assert len(report["pairs"]) == 14
    assert all(pair["ok"] for pair in report["pairs"])


def test_example_check_can_be_limited_to_given_transitions(manimflow, rendered_example_copy):
    result = manimflow("check-continuity", str(rendered_example_copy), "S2-S2b", "S3v-R", "--json")

    assert result.returncode == 0, result.stdout
    assert [(pair["transition"], pair["position"]) for pair in result.report["pairs"]] == [
        ("S2-S2b", "inicio"),
        ("S2-S2b", "fim"),
        ("S3v-R", "inicio"),
        ("S3v-R", "fim"),
    ]


def test_example_with_a_broken_final_state_fails_on_that_pair(manimflow, rendered_example_copy):
    # The boost's last scene adds a square after its last animation, so R's image has a
    # square that the video never shows.
    scenes = rendered_example_copy / "cenas.py"
    text = scenes.read_text(encoding="utf-8")
    end_of_boost = "        self.play(Create(simetria), run_time=0.5)\n        self.wait(0.3)\n"
    assert text.count(end_of_boost) == 1
    scenes.write_text(
        text.replace(end_of_boost, end_of_boost + "        self.add(Square(side_length=4, fill_opacity=1))\n"),
        encoding="utf-8",
    )
    assert manimflow("preview", str(rendered_example_copy), "R_RefHeroi").returncode == 0

    result = manimflow("check-continuity", str(rendered_example_copy), "--json")

    assert result.returncode != 0
    failing = [(pair["transition"], pair["position"]) for pair in result.report["pairs"] if not pair["ok"]]
    assert failing == [("S3v-R", "fim")]
    assert len(result.report["errors"]) == 1
    assert "S3v-R" in result.report["errors"][0]
