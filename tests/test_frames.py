import numpy as np
from PIL import Image

from conftest import preview
from manimflow.continuity import compare_images


def test_frames_saves_transition_positions_and_state_images(manimflow, lesson):
    preview(lesson, "S0", "T01")

    result = manimflow("frames", str(lesson), "--json")

    assert result.returncode == 0, result.stdout
    frames = lesson / "saida" / "previa" / "quadros"
    expected = [
        frames / "S0.png",
        frames / "S1.png",
        frames / "S0-S1_inicio.png",
        frames / "S0-S1_meio.png",
        frames / "S0-S1_fim.png",
    ]
    report = result.report
    assert report["ok"] is True
    assert report["command"] == "frames"
    assert sorted(report["files"]) == sorted(str(path) for path in expected)
    for path in expected:
        with Image.open(path) as image:
            assert image.size == (854, 480), path


def test_transition_frames_follow_the_video(manimflow, lesson):
    preview(lesson, "S0", "T01")

    manimflow("frames", str(lesson))

    # The fixture's square moves right, so its frames' blue pixels move right too.
    frames = lesson / "saida" / "previa" / "quadros"
    centers = [blue_center_x(frames / f"S0-S1_{position}.png") for position in ("inicio", "meio", "fim")]
    assert centers[0] < centers[1] < centers[2]


def test_state_image_of_a_transition_is_its_videos_last_frame(manimflow, lesson):
    # Manim draws a transition's still mobjects onto a background once; the scene's
    # image must not draw them over it again, or their anti-aliased edges darken.
    (lesson / "cenas.py").write_text(
        "from manim import BLUE, LEFT, ORANGE, RIGHT, UP, Line, Scene, Square, VGroup\n\n\n"
        "class S0(Scene):\n"
        "    def construct(self):\n"
        "        self.add(Square(color=BLUE))\n\n\n"
        "class T01(Scene):\n"
        "    def construct(self):\n"
        "        linhas = VGroup(*(Line(3 * LEFT, 3 * RIGHT, color=ORANGE, stroke_width=2).shift(0.4 * k * UP)"
        " for k in range(-4, 5)))\n"
        "        quadrado = Square(color=BLUE)\n"
        "        self.add(linhas, quadrado)\n"
        "        self.play(quadrado.animate.shift(RIGHT), run_time=0.5)\n"
        "        self.wait(0.2)\n",
        encoding="utf-8",
    )
    preview(lesson, "S0", "T01")

    result = manimflow("frames", str(lesson), "--json")

    assert result.returncode == 0, result.stdout
    frames = lesson / "saida" / "previa" / "quadros"
    with Image.open(frames / "S1.png") as state, Image.open(frames / "S0-S1_fim.png") as last:
        assert compare_images(state, last).fraction < 0.0002


def test_frames_can_be_limited_to_given_transitions(manimflow, lesson):
    # A third state, reached by a plain slide change, is outside the S0-S1 transition.
    plan_text = (lesson / "plano.yaml").read_text(encoding="utf-8").replace(
        "\ntransicoes:",
        "  - id: S2\n    titulo: De novo\n    visivel: O quadrado no centro.\n    cena: S0\n\ntransicoes:",
    )
    (lesson / "plano.yaml").write_text(plan_text, encoding="utf-8")
    preview(lesson, "S0", "T01")

    everything = manimflow("frames", str(lesson), "--json")
    limited = manimflow("frames", str(lesson), "S0-S1", "--json")

    assert everything.returncode == 0, everything.stdout
    assert str(lesson / "saida" / "previa" / "quadros" / "S2.png") in everything.report["files"]
    assert limited.returncode == 0, limited.stdout
    assert len(limited.report["files"]) == 5
    assert str(lesson / "saida" / "previa" / "quadros" / "S2.png") not in limited.report["files"]


def test_unknown_transition_is_an_error(manimflow, lesson):
    preview(lesson, "S0", "T01")

    result = manimflow("frames", str(lesson), "S1-S0", "--json")

    assert result.returncode != 0
    assert any("S1-S0" in error for error in result.report["errors"])


def test_missing_preview_is_an_error_naming_the_scene(manimflow, lesson):
    preview(lesson, "S0")

    result = manimflow("frames", str(lesson), "--json")

    assert result.returncode != 0
    assert any("T01" in error for error in result.report["errors"])


def test_final_reads_the_final_render(manimflow, lesson):
    for scene in ("S0", "T01"):
        assert manimflow("render", str(lesson), scene).returncode == 0

    result = manimflow("frames", str(lesson), "--final", "--json")

    assert result.returncode == 0, result.stdout
    fim = lesson / "saida" / "quadros" / "S0-S1_fim.png"
    assert str(fim) in result.report["files"]
    with Image.open(fim) as image:
        assert image.size == (1920, 1080)


def test_invalid_plan_is_an_error(manimflow, lesson):
    (lesson / "plano.yaml").write_text("estados: []\n", encoding="utf-8")

    result = manimflow("frames", str(lesson), "--json")

    assert result.returncode != 0
    assert result.report["errors"]


def blue_center_x(path) -> float:
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    blue = (pixels[:, :, 2] - pixels[:, :, 0]) > 80
    return float(np.nonzero(blue)[1].mean())
