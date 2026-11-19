"""Turmas (ADR 0004), the lesson status the sidebar and the cards show, and starting a
lesson from a message."""

import json
import os
import shutil
from contextlib import asynccontextmanager

import pytest
from nicegui import ElementFilter, ui
from nicegui.testing.user_simulation import user_simulation

from manimflow import activity
from manimflow.agent import AssistantText
from manimflow.dialogs import lesson_url, turma_url
from manimflow.fake_agent import EditFile, ScriptedAgent
from manimflow.home import app_root
from manimflow.lessons import TURMA_COLORS, LessonNameError, Library, Status, profile_of, status
from manimflow.versioning import History
from conftest import FIXTURES

# Tries of should_see, 0.1 s apart, for what follows an agent turn: each turn
# commits a version, which takes seconds on Windows.
TURN = 100


@pytest.fixture
def library(tmp_path, monkeypatch) -> Library:
    monkeypatch.setattr("manimflow.lessons.documents_dir", lambda: tmp_path / "Documentos")
    library = Library(tmp_path / "dados")
    library.set_folder(tmp_path / "Aulas")
    return library


@asynccontextmanager
async def open_app(library, agent=None, path="/"):
    agent = agent or ScriptedAgent([])
    async with user_simulation(root=app_root(agent, library)) as user:
        await user.open(path)
        yield user


def add_lesson(folder, name):
    """Copies the minimal fixture lesson (two states, nothing rendered) into `folder`."""
    shutil.copytree(FIXTURES / "aula_minima", folder / name)
    return folder / name


def links(user, marker):
    with user:
        (container,) = user.find(marker=marker).elements
        return [element.text for element in container.descendants() if isinstance(element, ui.link)]


def labels(user, marker):
    with user:
        (container,) = user.find(marker=marker).elements
        return [element.text for element in container.descendants() if isinstance(element, ui.label)]


def render(lesson, path, age=0):
    target = lesson / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"render")
    if age:
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns - age * 10**9))


def older(path, seconds=60):
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns - seconds * 10**9))


# ── The store ──


def test_a_turma_is_a_folder_with_instructions_and_a_color(library):
    turma = library.create_turma("Relatividade Restrita", TURMA_COLORS["Roxo"])

    assert turma.path == library.folder / "Relatividade Restrita"
    assert (turma.path / "turma.md").read_text(encoding="utf-8").startswith("# Instruções da turma")
    assert json.loads((turma.path / ".turma.json").read_text(encoding="utf-8")) == {"cor": "#7c3aed"}
    assert [each.name for each in library.turmas()] == ["Relatividade Restrita"]
    # The agent reads the profile above the turma, so it is there before the first lesson.
    assert (library.folder / "perfil.md").is_file()


def test_folders_without_turma_md_are_not_turmas_and_lessons_stay_where_they_are(library):
    add_lesson(library.folder, "Aula antiga")
    (library.folder / "Rascunhos").mkdir()
    library.create_turma("Física 1", TURMA_COLORS["Verde"])

    assert [turma.name for turma in library.turmas()] == ["Física 1"]
    assert [lesson.id for lesson in library.lessons()] == ["Aula antiga"]


def test_a_lesson_in_a_turma_has_the_turma_in_its_id_and_its_address(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    lesson = library.create("Aula 01", "Física 1")

    assert lesson == library.folder / "Física 1" / "Aula 01"
    assert [summary.id for summary in library.lessons("Física 1")] == ["Física 1/Aula 01"]
    assert library.lesson("Física 1/Aula 01") == lesson
    assert library.lesson_id(lesson) == "Física 1/Aula 01"
    assert lesson_url("Física 1/Aula 01") == "/aula/F%C3%ADsica%201/Aula%2001"
    assert [summary.id for summary in library.all_lessons()] == ["Física 1/Aula 01"]


@pytest.mark.parametrize("id", ["../Fora", "Física 1/../Fora", "Física 1/Aula 01/saida", "Rascunhos/Aula"])
def test_an_id_outside_the_turmas_names_no_lesson(library, tmp_path, id):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    library.create("Aula 01", "Física 1")
    add_lesson(tmp_path, "Fora")
    (library.folder / "Rascunhos").mkdir()
    add_lesson(library.folder / "Rascunhos", "Aula")

    assert library.lesson(id) is None


def test_names_are_checked_against_what_is_already_there(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    add_lesson(library.folder, "Aula 01")

    with pytest.raises(LessonNameError, match="Já existe uma turma com esse nome."):
        library.create("Física 1")
    with pytest.raises(LessonNameError, match="Já existe uma aula com esse nome."):
        library.create_turma("Aula 01", TURMA_COLORS["Azul"])
    with pytest.raises(LessonNameError, match="Dê um nome para a turma."):
        library.create_turma("  ", TURMA_COLORS["Azul"])


def test_the_profile_is_one_per_lessons_folder_also_inside_a_turma(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    in_turma = library.create("Aula 01", "Física 1")
    loose = library.create("Aula 02")

    assert profile_of(in_turma) == library.folder / "perfil.md"
    assert profile_of(loose) == library.folder / "perfil.md"


def test_a_name_made_from_a_message_is_short_valid_and_free(library):
    library.create_turma("Ondas", TURMA_COLORS["Azul"])
    library.create("Uma onda estacionária numa corda", "Ondas")

    assert library.free_name("Uma onda estacionária numa corda", "Ondas") == "Uma onda estacionária numa corda (2)"
    assert library.free_name("Luz: reflexão / refração?") == "Luz reflexão refração"
    long = library.free_name("palavra " * 20)
    assert len(long) <= 60 and not long.endswith(" ")


# ── Status ──


def test_a_new_lesson_is_new(library):
    assert status(library.create("Aula 01")) == Status.NEW


def test_a_plan_the_agent_wrote_waits_for_the_teacher_until_approved(library):
    lesson = add_lesson(library.folder, "Aula 01")
    assert status(lesson) == Status.PLAN

    History.open(lesson).approve_plan()
    assert status(lesson) == Status.IN_PROGRESS


def test_a_plan_changed_after_its_renders_waits_again(library):
    lesson = add_lesson(library.folder, "Aula 01")
    older(lesson / "plano.yaml")
    render(lesson, "saida/previa/png/S0.png")
    assert status(lesson) == Status.IN_PROGRESS

    (lesson / "plano.yaml").write_text(
        (lesson / "plano.yaml").read_text(encoding="utf-8").replace("Quadrado deslocado", "Quadrado ao lado"),
        encoding="utf-8",
    )
    assert status(lesson) == Status.PLAN


def test_a_lesson_with_every_state_rendered_is_ready_and_an_export_after_it_makes_it_exported(library):
    lesson = add_lesson(library.folder, "Aula 01")
    older(lesson / "plano.yaml", 120)
    render(lesson, "saida/previa/png/S0.png", age=60)
    render(lesson, "saida/png/T01.png", age=60)
    assert status(lesson) == Status.READY

    render(lesson, "saida/powerpoint/01-S0.png")
    assert status(lesson) == Status.EXPORTED


def test_the_example_never_waits_for_an_approval(library):
    assert status(library.example()) != Status.PLAN


# ── Pages ──


async def test_a_turma_is_created_from_the_sidebar_with_its_color_and_opens(library):
    async with open_app(library) as user:
        user.find(marker="new-turma").click()
        user.find(marker="turma-name-input").type("Eletromagnetismo")
        user.find(marker="cor-Laranja").click()
        user.find("Criar turma").click()

        await user.should_see(marker="turma-counts")
    turma = library.turma("Eletromagnetismo")
    assert turma is not None and turma.color == TURMA_COLORS["Laranja"]


async def test_the_sidebar_maps_turmas_lessons_and_lessons_without_a_turma(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    add_lesson(library.folder / "Física 1", "Aula 01")
    add_lesson(library.folder, "Aula solta")
    async with open_app(library, path=lesson_url("Física 1/Aula 01")) as user:
        await user.should_see(marker="current-lesson", retries=TURN)
        # The open lesson's turma is unfolded.
        assert links(user, "turmas") == ["Física 1", "Aula 01"]
        assert links(user, "loose-lessons") == ["Aula solta"]
        # Both plans wait for the teacher.
        assert labels(user, "inbox") == ["Aprovar o plano", "Física 1 · Aula 01", "Aprovar o plano", "Aula solta"]


async def test_a_lesson_is_created_in_a_turma_from_the_turma_page(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    async with open_app(library, path=turma_url("Física 1")) as user:
        user.find(marker="new-lesson-card").click()
        user.find(marker="lesson-name-input").type("Aula 01")
        user.find("Criar").click()

        await user.should_see(marker="message", retries=TURN)
    assert (library.folder / "Física 1" / "Aula 01" / "plano.yaml").is_file()


async def test_the_turma_page_counts_its_lessons_and_edits_its_instructions(library):
    library.create_turma("Física 1", TURMA_COLORS["Verde"])
    add_lesson(library.folder / "Física 1", "Aula 01")
    library.create("Aula 02", "Física 1")
    async with open_app(library, path=turma_url("Física 1")) as user:
        with user:
            stats = [element.content for element in ElementFilter(kind=ui.html).within(marker="turma-counts")]
        assert stats == ["<b>2</b>aulas", "<b>0</b>prontas", "<b>1</b>para aprovar"]
        assert set(links(user, "lessons")) == {"Aula 01", "Aula 02"}

        user.find("Editar").click()
        user.find(marker="instructions-input").clear().type("Notação: c = 1.")
        user.find("Salvar instruções").click()
        await user.should_see("Instruções salvas.")
    assert library.turma_instructions("Física 1") == "Notação: c = 1."


async def test_a_message_on_the_home_starts_a_lesson_in_the_chosen_turma_and_sends_it(library):
    library.create_turma("Ondas", TURMA_COLORS["Azul"])
    agent = ScriptedAgent([[AssistantText("Vou montar o plano.")]])
    async with open_app(library, agent) as user:
        with user:
            (turma,) = user.find(marker="start-turma").elements
            turma.value = "Ondas"
        user.find(marker="start-message").type("Uma onda estacionária numa corda com 3 harmônicos")
        user.find(marker="start").click()

        await user.should_see("Vou montar o plano.", retries=TURN)
    lesson = library.folder / "Ondas" / "Uma onda estacionária numa corda com 3 harmônicos"
    assert (lesson / "plano.yaml").is_file()
    assert [received.text for received in agent.received] == ["Uma onda estacionária numa corda com 3 harmônicos"]


async def test_the_agent_at_work_shows_in_the_sidebar(library):
    lesson = add_lesson(library.folder, "Aula 01")
    History.open(lesson).approve_plan()
    activity.start(lesson)
    try:
        async with open_app(library) as user:
            assert labels(user, "inbox") == ["O agente está trabalhando", "Aula 01"]
    finally:
        activity.stop(lesson)


async def test_an_approval_records_the_plan_so_it_stops_waiting(library):
    lesson = add_lesson(library.folder, "Aula 01")
    agent = ScriptedAgent([[EditFile("CONTEXTO.md", "Plano aprovado.\n"), AssistantText("Sigo o plano.")]])
    async with open_app(library, agent, lesson_url("Aula 01")) as user:
        await user.should_see(marker="approve-bar-button", retries=TURN)
        user.find(marker="approve-bar-button").click()
        await user.should_see("Sigo o plano.", retries=TURN)
        await user.should_not_see(marker="approve-bar-button", retries=TURN)
    assert agent.received[0].text.startswith("Aprovei o plano")
    assert status(lesson) == Status.IN_PROGRESS
