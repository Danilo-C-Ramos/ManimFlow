import shutil

import av
import numpy as np
import pytest
from PIL import Image

from conftest import FIXTURES

# Exports render at final quality; tests shrink them so the fixture renders fast.
SMALL = ("--resolution", "144", "--fps", "10")


def export(manimflow, lesson, preset, *options):
    result = manimflow("export", str(lesson), preset, *options, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    return result.report


def image_size(path):
    with Image.open(path) as image:
        return image.size


def video_frames(path) -> list[Image.Image]:
    with av.open(str(path)) as container:
        return [frame.to_image() for frame in container.decode(video=0)]


def add_second_transition(lesson):
    """Adds state S2 after S1, reached by T12, which moves the square up."""
    with open(lesson / "cenas.py", "a", encoding="utf-8") as scenes:
        scenes.write(
            "\n\nclass T12(Scene):\n"
            "    def construct(self):\n"
            "        from manim import UP\n"
            "        quadrado = Square(color=BLUE).shift(RIGHT)\n"
            "        self.add(quadrado)\n"
            "        self.play(quadrado.animate.shift(UP), run_time=0.5)\n"
        )
    plan = lesson / "plano.yaml"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "\ntransicoes:",
            "  - id: S2\n    titulo: Quadrado no alto\n    visivel: O quadrado subiu.\n    cena: T12\n"
            "\ntransicoes:",
        )
        + "  - de: S1\n    para: S2\n    descricao: O quadrado sobe.\n    duracao: 0.5\n    cena: T12\n",
        encoding="utf-8",
    )


def square_center(image: Image.Image) -> tuple[float, float]:
    """Column and row of the fixture square, the only thing drawn on the black background."""
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    rows, columns = np.nonzero(pixels.max(axis=2) > 40)
    return float(columns.mean()), float(rows.mean())


def test_powerpoint_writes_a_png_per_state_and_an_mp4_per_transition_in_plan_order(manimflow, lesson):
    report = export(manimflow, lesson, "powerpoint", *SMALL)

    folder = lesson / "saida" / "powerpoint"
    expected = [folder / "01_S0.png", folder / "02_S0-S1.mp4", folder / "03_S1.png"]
    assert report["ok"] is True
    assert report["command"] == "export"
    assert report["preset"] == "powerpoint"
    assert report["files"] == [str(path) for path in expected]
    assert sorted(folder.iterdir()) == expected
    assert image_size(folder / "01_S0.png") == (256, 144)
    assert image_size(folder / "03_S1.png") == (256, 144)
    frames = video_frames(folder / "02_S0-S1.mp4")
    assert frames[0].size == (256, 144)
    # The fixture transition lasts 0.5 s.
    assert len(frames) == 5


def test_beamer_writes_a_png_per_state(manimflow, lesson):
    report = export(manimflow, lesson, "beamer", *SMALL)

    folder = lesson / "saida" / "beamer"
    expected = [folder / "01_S0.png", folder / "02_S1.png"]
    assert report["files"] == [str(path) for path in expected]
    assert sorted(folder.iterdir()) == expected


def test_video_concatenates_the_transitions_in_plan_order(manimflow, lesson):
    add_second_transition(lesson)

    report = export(manimflow, lesson, "video", *SMALL)

    video = lesson / "saida" / "video" / "Aula Mínima.mp4"
    assert report["files"] == [str(video)]
    frames = video_frames(video)
    assert len(frames) == 10
    centers = [square_center(frame) for frame in frames]
    # S0-S1 moves the square right, then S1-S2 moves it up.
    assert centers[0][0] < centers[4][0]
    assert abs(centers[4][1] - centers[0][1]) < 2
    assert centers[9][1] < centers[5][1]
    assert abs(centers[9][0] - centers[5][0]) < 2


def test_web_writes_a_gif_per_transition_and_a_static_gif_per_state(manimflow, lesson):
    report = export(manimflow, lesson, "web", *SMALL)

    folder = lesson / "saida" / "web"
    expected = [folder / "01_S0.gif", folder / "02_S0-S1.gif", folder / "03_S1.gif"]
    assert report["files"] == [str(path) for path in expected]
    assert sorted(folder.iterdir()) == expected
    with Image.open(folder / "02_S0-S1.gif") as transition:
        assert transition.size == (256, 144)
        assert transition.n_frames == 5
        assert transition.info["duration"] == 100
        # A transition plays once and stays on its last frame, the next state's image.
        assert "loop" not in transition.info
    for static in (folder / "01_S0.gif", folder / "03_S1.gif"):
        with Image.open(static) as image:
            assert image.n_frames == 1


def test_gifs_of_a_lesson_share_one_palette_and_states_are_their_transitions_last_frame(manimflow, lesson):
    add_second_transition(lesson)
    # S3 shows S0's image again after a plain slide change, so it has no incoming transition.
    plan = lesson / "plano.yaml"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "\ntransicoes:", "  - id: S3\n    titulo: De novo\n    visivel: O quadrado no centro.\n    cena: S0\n\ntransicoes:"
        ),
        encoding="utf-8",
    )

    report = export(manimflow, lesson, "web", *SMALL)

    folder = lesson / "saida" / "web"
    names = ["01_S0", "02_S0-S1", "03_S1", "04_S1-S2", "05_S2", "06_S3"]
    assert report["files"] == [str(folder / f"{name}.gif") for name in names]
    tables = {name: color_tables(folder / f"{name}.gif") for name in names}
    palette = tables["01_S0"][0]
    assert all(found == [palette] for found in tables.values()), "one global palette, no local ones"
    for transition, state in (("02_S0-S1", "03_S1"), ("04_S1-S2", "05_S2")):
        assert pixels(folder / f"{state}.gif") == pixels(folder / f"{transition}.gif", frame=-1)
    # States without an incoming transition use their scene's image, here the same one.
    assert pixels(folder / "06_S3.gif") == pixels(folder / "01_S0.gif")


def test_web_rejects_frame_rates_gifs_cant_play(manimflow, lesson):
    result = manimflow("export", str(lesson), "web", "--fps", "60", "--json")

    assert result.returncode != 0
    assert any("50" in error for error in result.report["errors"])


def pixels(path, frame: int = 0) -> bytes:
    with Image.open(path) as image:
        image.seek(getattr(image, "n_frames", 1) - 1 if frame == -1 else frame)
        return image.convert("RGB").tobytes()


def color_tables(path) -> list[bytes]:
    """The global and local color tables of a GIF file, in file order."""
    data = path.read_bytes()
    tables = []

    def table(flags: int, at: int) -> int:
        size = 3 * 2 ** ((flags & 7) + 1)
        tables.append(data[at : at + size])
        return at + size

    def skip_sub_blocks(at: int) -> int:
        while data[at]:
            at += data[at] + 1
        return at + 1

    at = 13
    if data[10] & 0x80:
        at = table(data[10], at)
    while data[at] != 0x3B:  # trailer
        if data[at] == 0x21:  # extension
            at = skip_sub_blocks(at + 2)
        elif data[at] == 0x2C:  # image descriptor
            flags = data[at + 9]
            at += 10
            if flags & 0x80:
                at = table(flags, at)
            at = skip_sub_blocks(at + 1)  # after the LZW minimum code size
        else:
            raise ValueError(f"unexpected GIF block {data[at]:#x} in {path}")
    return tables


def corner(image: Image.Image) -> tuple[int, ...]:
    return tuple(np.asarray(image.convert("RGB"))[2, 2].tolist())


def test_background_applies_to_every_output(manimflow, lesson):
    # Rendered first with the lesson's own black background, so a cached animation
    # with the old background would show up below.
    export(manimflow, lesson, "powerpoint", *SMALL)

    report = export(manimflow, lesson, "powerpoint", *SMALL, "--background", "#FFCC00")
    gifs = export(manimflow, lesson, "web", *SMALL, "--background", "gold")

    assert report["settings"]["background"] == "#ffcc00"
    folder = lesson / "saida" / "powerpoint"
    for name in ("01_S0.png", "03_S1.png"):
        with Image.open(folder / name) as image:
            assert corner(image) == (255, 204, 0), name
    for frame in video_frames(folder / "02_S0-S1.mp4"):
        assert all(abs(a - b) <= 6 for a, b in zip(corner(frame), (255, 204, 0)))
    for path in gifs["files"]:
        with Image.open(path) as image:
            # Pillow's "gold" is #ffd700.
            assert corner(image) == (255, 215, 0), path


def square_width(image: Image.Image) -> int:
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    columns = np.nonzero((pixels.max(axis=2) > 40).any(axis=0))[0]
    return int(columns.max() - columns.min())


def test_aspect_ratio_applies_to_every_output_and_keeps_the_whole_drawing(manimflow, lesson):
    wide = export(manimflow, lesson, "powerpoint", *SMALL)
    with Image.open(wide["files"][0]) as image:
        wide_square = square_width(image)

    report = export(manimflow, lesson, "powerpoint", *SMALL, "--aspect-ratio", "4:3")

    assert report["settings"]["aspect_ratio"] == "4:3"
    folder = lesson / "saida" / "powerpoint"
    for name in ("01_S0.png", "03_S1.png"):
        assert image_size(folder / name) == (192, 144), name
    assert video_frames(folder / "02_S0-S1.mp4")[0].size == (192, 144)
    # The 16:9 drawing fits across the narrower frame, so it shows at 3/4 of the size
    # instead of losing its sides.
    with Image.open(folder / "01_S0.png") as image:
        assert abs(square_width(image) / wide_square - 0.75) < 0.1


@pytest.mark.parametrize("ratio", ["4x3", "0:9", "5:1"])
def test_invalid_aspect_ratio_is_rejected(manimflow, lesson, ratio):
    result = manimflow("export", str(lesson), "powerpoint", "--aspect-ratio", ratio)

    assert result.returncode != 0
    assert "--aspect-ratio" in result.stderr and "width:height" in result.stderr


def test_exports_render_at_final_quality_by_default(manimflow, lesson):
    report = export(manimflow, lesson, "beamer")

    assert report["settings"] == {
        "resolution": 1080,
        "fps": 60,
        "aspect_ratio": "16:9",
        "background": None,
        "width": 1920,
        "height": 1080,
    }
    for path in report["files"]:
        assert image_size(path) == (1920, 1080), path
    assert report["duration_s"] > 0
    assert report["errors"] == []


def test_export_replaces_the_previous_export_of_the_preset(manimflow, lesson):
    add_second_transition(lesson)
    export(manimflow, lesson, "powerpoint", *SMALL)
    folder = lesson / "saida" / "powerpoint"
    (folder / "notas.txt").write_text("minhas notas", encoding="utf-8")
    # Back to the fixture's plan: S2 and its transition are gone.
    shutil.copyfile(FIXTURES / "aula_minima" / "plano.yaml", lesson / "plano.yaml")

    report = export(manimflow, lesson, "powerpoint", *SMALL)

    exported = [folder / "01_S0.png", folder / "02_S0-S1.mp4", folder / "03_S1.png"]
    assert report["files"] == [str(path) for path in exported]
    assert sorted(folder.iterdir()) == sorted([*exported, folder / "notas.txt"])


def test_failed_export_keeps_the_previous_one(manimflow, lesson):
    export(manimflow, lesson, "beamer", *SMALL)
    before = sorted((lesson / "saida" / "beamer").iterdir())
    scenes = lesson / "cenas.py"
    scenes.write_text(scenes.read_text(encoding="utf-8") + "\nraise ValueError('quebrada')\n", encoding="utf-8")

    result = manimflow("export", str(lesson), "beamer", *SMALL, "--json")

    assert result.returncode != 0
    assert result.report["files"] == []
    assert any("quebrada" in error for error in result.report["errors"])
    assert "Traceback" in result.report["manim_output"]
    assert sorted((lesson / "saida" / "beamer").iterdir()) == before
