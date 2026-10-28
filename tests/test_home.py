import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import pygit2
import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.fake_agent import EditFile, ScriptedAgent
from manimflow.home import app_root
from manimflow.lessons import Library
from conftest import EXAMPLE, FIXTURES


@pytest.fixture
def library(tmp_path) -> Library:
    """ManimFlow's own folder in `tmp_path / "dados"`, with the lessons in `tmp_path / "Aulas"`."""
    library = Library(tmp_path / "dados")
    library.set_folder(tmp_path / "Aulas")
    return library


@asynccontextmanager
async def open_home(library, scenario=()):
    agent = ScriptedAgent(list(scenario))
    async with user_simulation(root=app_root(agent, library)) as user:
        await user.open("/")
        yield user


def add_lesson(folder, name, edited):
    """Copies the minimal fixture lesson (two states) into `folder`, last edited at `edited`."""
    lesson = folder / name
    shutil.copytree(FIXTURES / "aula_minima", lesson)
    for path in lesson.iterdir():
        os.utime(path, (edited.timestamp(), edited.timestamp()))
    return lesson


def labels(user, marker):
    """The text of every label and link inside the element marked `marker`, in page order."""
    with user:
        (container,) = user.find(marker=marker).elements
        return [element.text for element in container.descendants() if isinstance(element, (ui.label, ui.link))]


async def test_lists_the_lessons_in_the_folder_with_last_edit_and_states(library):
    add_lesson(library.folder, "Aula 09 - Minkowski", datetime(2026, 10, 5, 14, 30))
    add_lesson(library.folder, "Aula 10 - Gêmeos", datetime(2026, 10, 12, 9, 0))
    (library.folder / "Rascunhos").mkdir()

    async with open_home(library) as user:
        await user.should_see("Minhas aulas")
        assert labels(user, "lessons") == [
            "Aula 10 - Gêmeos",
            "editada em 12/10/2026 · 2 estados",
            "Aula 09 - Minkowski",
            "editada em 05/10/2026 · 2 estados",
        ]


def history(lesson):
    """The messages of the lesson's commits, newest first."""
    repo = pygit2.Repository(str(lesson / ".git"))
    return [commit.message for commit in repo.walk(repo.head.target)]


def create_lesson(user, name):
    user.find(kind=ui.button, content="+ Nova aula").click()
    user.find(marker="lesson-name-input").type(name)
    user.find("Criar").click()


async def test_a_new_lesson_gets_the_layout_the_profile_and_a_first_version_and_opens(library, manimflow):
    async with open_home(library) as user:
        create_lesson(user, "Aula 11 - Óptica")

        await user.should_see(marker="message")
        await user.should_see("Aula 11 - Óptica")

    lesson = library.folder / "Aula 11 - Óptica"
    assert sorted(path.name for path in lesson.iterdir()) == [
        ".git", "CONTEXTO.md", "cenas.py", "fisica.py", "plano.yaml", "saida", "test_fisica.py",
    ]  # fmt: skip
    assert history(lesson) == ["Primeira versão da aula"]
    # The plan cards draw a new lesson's plan, so it must already be valid.
    assert manimflow("plan", "validate", str(lesson)).returncode == 0
    assert "vírgula decimal" in (library.folder / "perfil.md").read_text(encoding="utf-8")


async def test_the_new_lesson_shows_up_on_the_home(library):
    async with open_home(library) as user:
        create_lesson(user, "Aula 11 - Óptica")
        await user.should_see(marker="message")

        await user.open("/")
        assert labels(user, "lessons")[0] == "Aula 11 - Óptica"


async def test_a_lesson_card_opens_the_lesson_and_the_lesson_leads_back_home(library):
    add_lesson(library.folder, "Aula 09 - Minkowski", datetime(2026, 10, 5, 14, 30))
    async with open_home(library) as user:
        user.find(kind=ui.link, content="Aula 09 - Minkowski").click()
        await user.should_see(marker="message")

        user.find(kind=ui.button, content="Minhas aulas").click()
        await user.should_see("+ Nova aula")


async def test_an_address_outside_the_lessons_folder_opens_no_lesson(library, tmp_path):
    add_lesson(tmp_path, "Fora", datetime(2026, 10, 5))
    async with open_home(library) as user:
        await user.open("/aula/..%2FFora")
        await user.should_see("Esta aula não está na pasta das aulas.")
        await user.should_not_see(marker="message")


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("   ", "Dê um nome para a aula."),
        ("Aula 1/2", 'O nome não pode ter estes caracteres: < > : " / \\ | ? *'),
        ("CON", "Esse nome é reservado pelo Windows. Escolha outro."),
        ("Aula 09 - Minkowski", "Já existe uma aula com esse nome."),
    ],
)
async def test_a_name_that_cant_be_a_lesson_is_explained_and_nothing_is_created(library, name, problem):
    add_lesson(library.folder, "Aula 09 - Minkowski", datetime(2026, 10, 5))
    async with open_home(library) as user:
        create_lesson(user, name)

        await user.should_see(problem)
    assert [path.name for path in library.folder.iterdir()] == ["Aula 09 - Minkowski"]



def snapshot(folder):
    """Every file under `folder` with its content."""
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


async def test_the_example_has_its_own_strip_and_never_shows_among_the_lessons(library):
    add_lesson(library.folder, "Aula 09 - Minkowski", datetime(2026, 10, 5))
    async with open_home(library) as user:
        await user.should_see("Exemplo · Relatividade - herói e espelho")
        assert labels(user, "lessons")[::2] == ["Aula 09 - Minkowski"]


async def test_opening_the_example_works_on_a_copy_and_leaves_the_bundled_one_alone(library):
    bundled = snapshot(EXAMPLE)
    scenario = [[EditFile("cenas.py", "# mudado\n")]]
    async with open_home(library, scenario) as user:
        user.find("Abrir o exemplo").click()
        await user.should_see(marker="message")
        await user.should_see("Relatividade - herói e espelho")

        user.find(marker="message").type("muda tudo")
        user.find("Enviar").click()
        await user.should_see("Arquivo alterado: cenas.py")

    assert snapshot(EXAMPLE) == bundled
    # Nor does the copy land among the teacher's lessons.
    assert [path.name for path in library.folder.iterdir()] == []


def change_folder(user, folder):
    user.find(kind=ui.button, content="Mudar pasta").click()
    user.find(marker="folder-input").clear().type(str(folder))
    user.find("Salvar pasta").click()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows names Documents through its known-folder API")
@pytest.mark.parametrize(
    ("user_dirs", "documents"),
    [(None, "Documents"), ('XDG_DOCUMENTS_DIR="$HOME/Documentos"\n', "Documentos")],
)
async def test_the_lessons_folder_defaults_to_the_documents_folder(monkeypatch, tmp_path, user_dirs, documents):
    home = tmp_path / "casa"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    if user_dirs is not None:
        (home / ".config").mkdir(parents=True)
        (home / ".config" / "user-dirs.dirs").write_text(user_dirs, encoding="utf-8")

    async with open_home(Library(tmp_path / "dados")) as user:
        await user.should_see(f"Pasta das aulas: {home / documents / 'Aulas Manim'}")
    # Only a first lesson creates it.
    assert not (home / documents).exists()


async def test_the_lessons_folder_can_be_changed_and_the_choice_persists(library, tmp_path):
    synced = tmp_path / "Drive" / "Aulas"
    synced.mkdir(parents=True)
    add_lesson(synced, "Aula 12 - Doppler", datetime(2026, 10, 7))
    add_lesson(library.folder, "Aula 09 - Minkowski", datetime(2026, 10, 5))

    async with open_home(library) as user:
        change_folder(user, synced)

        await user.should_see(f"Pasta das aulas: {synced}")
        assert labels(user, "lessons")[::2] == ["Aula 12 - Doppler"]

    async with open_home(Library(library.data)) as user:
        await user.should_see(f"Pasta das aulas: {synced}")
        assert labels(user, "lessons")[::2] == ["Aula 12 - Doppler"]


async def test_a_new_lessons_folder_is_created(library, tmp_path):
    async with open_home(library) as user:
        change_folder(user, tmp_path / "Nova pasta" / "Aulas Manim")
        await user.should_see(f"Pasta das aulas: {tmp_path / 'Nova pasta' / 'Aulas Manim'}")

        create_lesson(user, "Aula 1")
        await user.should_see(marker="message")
    assert (tmp_path / "Nova pasta" / "Aulas Manim" / "Aula 1" / "plano.yaml").is_file()


@pytest.mark.parametrize(
    ("folder", "problem"),
    [
        ("Aulas", "Use o caminho completo da pasta"),
        ("{file}", "Não foi possível usar essa pasta."),
    ],
)
async def test_a_folder_that_cant_hold_lessons_is_explained_and_not_kept(library, tmp_path, folder, problem):
    (tmp_path / "arquivo.txt").write_text("", encoding="utf-8")
    before = library.folder
    async with open_home(library) as user:
        change_folder(user, folder.format(file=tmp_path / "arquivo.txt"))
        await user.should_see(problem)
    assert Library(library.data).folder == before


def profile_field(user):
    with user:
        (field,) = user.find(marker="profile-input").elements
        return field.value


async def test_the_profile_starts_from_the_bundled_one_and_new_lessons_read_the_edited_one(library):
    async with open_home(library) as user:
        user.find(kind=ui.button, content="Perfil do professor").click()
        assert profile_field(user) == (EXAMPLE.parent / "perfil.md").read_text(encoding="utf-8")

        user.find(marker="profile-input").clear().type("# Perfil\n\n- Números com vírgula decimal.\n- Fundo preto.\n")
        user.find("Salvar perfil").click()
        await user.should_see("Perfil salvo.")

        create_lesson(user, "Aula 1")
        await user.should_see(marker="message")

    lesson = library.folder / "Aula 1"
    # Where the agent and the equations panel read it.
    assert (lesson.parent / "perfil.md").read_text(encoding="utf-8").endswith("- Fundo preto.\n")


async def test_the_profile_shows_what_is_on_disk(library):
    (library.folder / "perfil.md").write_text("Só fundo branco.\n", encoding="utf-8")
    async with open_home(library) as user:
        user.find(kind=ui.button, content="Perfil do professor").click()
        assert profile_field(user) == "Só fundo branco.\n"


async def test_the_profile_comes_along_to_a_new_lessons_folder(library, tmp_path):
    (library.folder / "perfil.md").write_text("Só fundo branco.\n", encoding="utf-8")
    async with open_home(library) as user:
        change_folder(user, tmp_path / "Drive")
        await user.should_see(f"Pasta das aulas: {tmp_path / 'Drive'}")

        user.find(kind=ui.button, content="Perfil do professor").click()
        assert profile_field(user) == "Só fundo branco.\n"
    assert (tmp_path / "Drive" / "perfil.md").read_text(encoding="utf-8") == "Só fundo branco.\n"


async def test_a_new_lesson_renders_and_its_physics_test_passes(library, manimflow):
    async with open_home(library) as user:
        create_lesson(user, "Aula 1")
        await user.should_see(marker="message")
    lesson = library.folder / "Aula 1"

    assert manimflow("preview", str(lesson), "S0_Inicio").returncode == 0
    physics = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_fisica.py"],
        cwd=lesson,
        capture_output=True,
        text=True,
    )
    assert physics.returncode == 0, physics.stdout


async def test_an_empty_folder_says_where_to_start(library):
    async with open_home(library) as user:
        assert labels(user, "lessons") == ['Nenhuma aula nesta pasta ainda. Comece por "+ Nova aula".']


async def test_a_lesson_with_a_percent_sign_in_its_name_opens(library):
    async with open_home(library) as user:
        create_lesson(user, "100%eficiente")
        await user.should_see(marker="message")
        await user.should_see("100%eficiente")
