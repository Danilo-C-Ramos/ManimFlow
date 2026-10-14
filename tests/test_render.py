from PIL import Image


def png_size(path):
    with Image.open(path) as image:
        return image.size


def test_preview_of_static_scene_writes_png(manimflow, lesson):
    result = manimflow("preview", str(lesson), "S0")

    assert result.returncode == 0, result.stderr
    assert (lesson / "saida" / "previa" / "png" / "S0.png").is_file()
    assert not (lesson / "saida" / "previa" / "mp4" / "S0.mp4").exists()


def test_preview_of_transition_writes_last_frame_and_video(manimflow, lesson):
    result = manimflow("preview", str(lesson), "T01")

    assert result.returncode == 0, result.stderr
    png = lesson / "saida" / "previa" / "png" / "T01.png"
    mp4 = lesson / "saida" / "previa" / "mp4" / "T01.mp4"
    assert png_size(png) == (854, 480)
    assert mp4.stat().st_size > 0


def test_render_uses_final_quality(manimflow, lesson):
    result = manimflow("render", str(lesson), "T01")

    assert result.returncode == 0, result.stderr
    assert png_size(lesson / "saida" / "png" / "T01.png") == (1920, 1080)
    assert (lesson / "saida" / "mp4" / "T01.mp4").stat().st_size > 0


def test_json_report_lists_files_and_duration(manimflow, lesson):
    result = manimflow("preview", str(lesson), "T01", "--json")

    assert result.returncode == 0, result.stderr
    report = result.report
    assert report["ok"] is True
    assert report["command"] == "preview"
    assert report["scene"] == "T01"
    assert sorted(report["files"]) == sorted(
        [
            str(lesson / "saida" / "previa" / "png" / "T01.png"),
            str(lesson / "saida" / "previa" / "mp4" / "T01.mp4"),
        ]
    )
    assert report["duration_s"] > 0
    assert report["errors"] == []
    # Accented lesson paths stay readable for the agent, as in the plan report.
    assert "Aula Mínima" in result.stdout


def test_failing_scene_exits_nonzero_with_manim_error_output(manimflow, lesson):
    with open(lesson / "cenas.py", "a", encoding="utf-8") as scenes:
        scenes.write(
            "\n\nclass Quebrada(Scene):\n"
            "    def construct(self):\n"
            "        raise ValueError('raio negativo')\n"
        )

    result = manimflow("preview", str(lesson), "Quebrada", "--json")

    assert result.returncode != 0
    report = result.report
    assert report["ok"] is False
    assert report["files"] == []
    assert any("raio negativo" in error for error in report["errors"])
    assert "Traceback" in report["manim_output"]
    assert not (lesson / "saida" / "previa" / "png" / "Quebrada.png").exists()


def test_missing_scene_exits_nonzero(manimflow, lesson):
    result = manimflow("preview", str(lesson), "S9", "--json")

    assert result.returncode != 0
    assert any("S9" in error for error in result.report["errors"])


def test_failure_without_json_prints_errors_to_stderr(manimflow, lesson):
    result = manimflow("preview", str(lesson), "S9")

    assert result.returncode != 0
    assert "S9" in result.stderr
    assert result.stdout == ""


def test_scene_that_stops_animating_loses_its_old_video(manimflow, lesson):
    assert manimflow("preview", str(lesson), "T01").returncode == 0
    scenes = lesson / "cenas.py"
    scenes.write_text(
        scenes.read_text(encoding="utf-8").replace(
            "self.play(quadrado.animate.shift(RIGHT), run_time=0.5)",
            "quadrado.shift(RIGHT)",
        ),
        encoding="utf-8",
    )

    result = manimflow("preview", str(lesson), "T01", "--json")

    assert result.report["files"] == [str(lesson / "saida" / "previa" / "png" / "T01.png")]
    assert not (lesson / "saida" / "previa" / "mp4" / "T01.mp4").exists()


def test_report_includes_errors_manim_logs(manimflow, lesson):
    # Manim logs problems such as LaTeX errors through its logger, not the traceback.
    with open(lesson / "cenas.py", "a", encoding="utf-8") as scenes:
        scenes.write(
            "\n\nclass Quebrada(Scene):\n"
            "    def construct(self):\n"
            "        from manim import logger\n"
            "        logger.error('fórmula sem fechamento')\n"
            "        raise ValueError('latex error')\n"
        )

    result = manimflow("preview", str(lesson), "Quebrada", "--json")

    assert result.returncode != 0
    assert "fórmula sem fechamento" in result.report["manim_output"]
