import pytest

INVALID_NAMES = [
    "../x",
    "..\\x",
    "--flag",
    "-ql",
    "S0.png",
    "a b",
    "x;rm -rf ~",
    "",
    "1S",
    "class",  # a keyword, not an identifier
    "CON",  # reserved file name on Windows
    "nul",
    "Ação",  # not plain ASCII
]


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_invalid_scene_name_is_rejected_before_rendering(manimflow, lesson, name):
    # `--` makes argparse pass flag-like names through as the scene argument.
    result = manimflow("preview", "--json", str(lesson), "--", name)

    assert result.returncode != 0
    report = result.report
    assert report["ok"] is False
    assert any("scene name" in error for error in report["errors"])
    assert report["files"] == []
    # Nothing reached Manim or the file system.
    assert sorted(p.name for p in lesson.iterdir()) == ["cenas.py"]
    assert list(lesson.parent.iterdir()) == [lesson]


def test_flag_as_scene_without_separator_is_a_usage_error(manimflow, lesson):
    result = manimflow("preview", str(lesson), "--flag")

    assert result.returncode != 0
    assert sorted(p.name for p in lesson.iterdir()) == ["cenas.py"]


def test_missing_lesson_folder_is_reported(manimflow, tmp_path):
    result = manimflow("preview", str(tmp_path / "nao-existe"), "S0", "--json")

    assert result.returncode != 0
    assert any("lesson" in error for error in result.report["errors"])
    assert list(tmp_path.iterdir()) == []
