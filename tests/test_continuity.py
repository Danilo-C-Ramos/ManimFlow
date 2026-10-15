from conftest import preview


def show_scene_for_state(lesson, state: str, scene: str) -> None:
    """Points a state of the fixture plan at another scene's image."""
    plan = lesson / "plano.yaml"
    text = plan.read_text(encoding="utf-8")
    old = f"  - id: {state}\n"
    start = text.index(old)
    cena = text.index("    cena: ", start)
    end = text.index("\n", cena)
    plan.write_text(text[:cena] + f"    cena: {scene}" + text[end:], encoding="utf-8")


def test_matching_transition_passes_with_a_report_per_pair(manimflow, lesson):
    preview(lesson, "S0", "T01")

    result = manimflow("check-continuity", str(lesson), "--json")

    assert result.returncode == 0, result.stdout
    report = result.report
    frames = lesson / "saida" / "previa" / "quadros"
    assert report["ok"] is True
    assert report["command"] == "check-continuity"
    assert report["channel_diff"] == 60
    assert report["max_fraction"] == 0.001
    assert [(p["transition"], p["position"], p["state"]) for p in report["pairs"]] == [
        ("S0-S1", "inicio", "S0"),
        ("S0-S1", "fim", "S1"),
    ]
    first, last = report["pairs"]
    assert first["state_image"] == str(frames / "S0.png")
    assert first["frame"] == str(frames / "S0-S1_inicio.png")
    assert last["frame"] == str(frames / "S0-S1_fim.png")
    for pair in report["pairs"]:
        assert pair["ok"] is True
        assert 0 <= pair["fraction"] < 0.001


def test_transition_that_ends_elsewhere_fails_and_names_the_pair(manimflow, lesson):
    # S1 is now the square's starting image, but the video still moves it right.
    show_scene_for_state(lesson, "S1", "S0")
    preview(lesson, "S0", "T01")

    result = manimflow("check-continuity", str(lesson), "--json")

    assert result.returncode != 0
    pairs = {(p["transition"], p["position"]): p for p in result.report["pairs"]}
    assert pairs[("S0-S1", "inicio")]["ok"] is True
    assert pairs[("S0-S1", "fim")]["ok"] is False
    assert pairs[("S0-S1", "fim")]["fraction"] >= 0.001
    assert any("S0-S1" in error and "S1" in error for error in result.report["errors"])


def test_transition_that_starts_elsewhere_fails_and_names_the_pair(manimflow, lesson):
    # S0 is now the square's final image, but the video still starts with it centered.
    show_scene_for_state(lesson, "S0", "T01")
    preview(lesson, "T01")

    result = manimflow("check-continuity", str(lesson), "--json")

    assert result.returncode != 0
    pairs = {(p["transition"], p["position"]): p for p in result.report["pairs"]}
    assert pairs[("S0-S1", "inicio")]["ok"] is False
    assert pairs[("S0-S1", "fim")]["ok"] is True
    assert result.report["errors"] == [
        "Transition S0-S1 starts on a different image than state S0: "
        f"{pairs[('S0-S1', 'inicio')]['fraction']:.3%} of pixels differ "
        "(compare S0-S1_inicio.png with S0.png)"
    ]


def test_thresholds_can_be_loosened(manimflow, lesson):
    show_scene_for_state(lesson, "S1", "S0")
    preview(lesson, "S0", "T01")

    result = manimflow("check-continuity", str(lesson), "--max-fraction", "0.5", "--channel-diff", "80", "--json")

    assert result.returncode == 0, result.stdout
    assert result.report["max_fraction"] == 0.5
    assert result.report["channel_diff"] == 80


def test_text_output_has_a_line_per_pair(manimflow, lesson):
    preview(lesson, "S0", "T01")

    result = manimflow("check-continuity", str(lesson))

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("ok") and "S0-S1" in lines[0] and "S0" in lines[0]


def test_missing_preview_fails(manimflow, lesson):
    preview(lesson, "S0")

    result = manimflow("check-continuity", str(lesson), "--json")

    assert result.returncode != 0
    assert any("T01" in error for error in result.report["errors"])
