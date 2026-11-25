from contextlib import asynccontextmanager

import pygit2
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AssistantText
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, Produce, ScriptedAgent
from manimflow.versioning import History
from conftest import attached


def subject(commit):
    """The commit's message without the turn id that ends an agent turn's version."""
    return commit.message.partition("\n\nTurno: ")[0]


@asynccontextmanager
async def open_lesson(lesson, scenario=()):
    agent = ScriptedAgent(list(scenario))
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


async def send(user, text, last):
    """Sends `text` to the agent and waits until its turn has ended, `last` being the
    turn's last text."""
    user.find(marker="message").type(text)
    user.find(marker="send").click()
    # Each turn commits a version, which takes seconds on Windows.
    await user.should_see(last, retries=100)
    await user.should_not_see(marker="progress", retries=100)


def history_of(lesson):
    """Every commit in the lesson's own repository, newest first.

    Read with pygit2 directly, the way any git tool would see the folder.
    """
    repo = pygit2.Repository(str(lesson / ".git"))
    if repo.head_is_unborn:
        return []
    return list(repo.walk(repo.head.target))


def files_in(commit):
    """The path and content of every file the commit holds, with LF line endings
    (files written on Windows have CRLF)."""
    found = {}

    def walk(tree, prefix):
        for entry in tree:
            if entry.type_str == "tree":
                walk(entry, f"{prefix}{entry.name}/")
            else:
                found[f"{prefix}{entry.name}"] = entry.data.decode("utf-8").replace("\r\n", "\n")

    walk(commit.tree, "")
    return found


async def test_opening_a_lesson_without_history_commits_its_current_files(tmp_path):
    lesson = tmp_path / "Aula 01"
    lesson.mkdir()
    (lesson / "cenas.py").write_text("COR = AZUL\n", encoding="utf-8")
    (lesson / "CONTEXTO.md").write_text("# Contexto\n", encoding="utf-8")

    async with open_lesson(lesson, [[AssistantText("Oi.")]]):
        (first,) = history_of(lesson)

    assert subject(first) == "Primeira versão da aula"
    assert files_in(first) == {"cenas.py": "COR = AZUL\n", "CONTEXTO.md": "# Contexto\n"}


async def test_an_agent_turn_that_changes_a_file_makes_exactly_one_commit(tmp_path):
    (tmp_path / "cenas.py").write_text("COR_LUZ = BRANCO\n", encoding="utf-8")
    scenario = [
        [
            AssistantText("Vou trocar a cor da luz."),
            EditFile("cenas.py", "COR_LUZ = AMARELO\n"),
            EditFile("CONTEXTO.md", "A luz é amarela.\n"),
            AssistantText("Pronto."),
        ]
    ]
    async with open_lesson(tmp_path, scenario) as user:
        await send(user, "muda a cor da luz", last="Pronto.")
        latest, first = history_of(tmp_path)

    assert subject(latest) == "Pedido: muda a cor da luz"
    assert latest.parents == [first]
    assert files_in(latest) == {"cenas.py": "COR_LUZ = AMARELO\n", "CONTEXTO.md": "A luz é amarela.\n"}


async def test_a_turn_that_changes_no_file_makes_no_commit(tmp_path):
    (tmp_path / "cenas.py").write_text("COR_LUZ = BRANCO\n", encoding="utf-8")
    scenario = [[AssistantText("A luz já é branca."), EditFile("cenas.py", "COR_LUZ = BRANCO\n")]]
    async with open_lesson(tmp_path, scenario) as user:
        await send(user, "a luz é branca?", last="A luz já é branca.")

        assert [subject(commit) for commit in history_of(tmp_path)] == ["Primeira versão da aula"]


async def test_reopening_a_lesson_keeps_its_history(tmp_path):
    (tmp_path / "cenas.py").write_text("COR_LUZ = BRANCO\n", encoding="utf-8")
    async with open_lesson(tmp_path, [[EditFile("cenas.py", "COR_LUZ = AZUL\n"), AssistantText("Feito.")]]) as user:
        await send(user, "luz azul", last="Feito.")

    async with open_lesson(tmp_path):
        assert [subject(commit) for commit in history_of(tmp_path)] == ["Pedido: luz azul", "Primeira versão da aula"]


async def test_render_outputs_and_caches_are_not_versioned(tmp_path):
    (tmp_path / "cenas.py").write_text("COR_LUZ = BRANCO\n", encoding="utf-8")
    (tmp_path / "saida" / "png").mkdir(parents=True)
    (tmp_path / "saida" / "png" / "S0.png").write_bytes(b"png antigo")
    scenario = [
        [
            EditFile("cenas.py", "COR_LUZ = AZUL\n"),
            Produce("saida/previa/S0.png", b"png"),
            Produce("saida/previa/S0-S1.mp4", b"mp4"),
            Produce(".manimflow/media/videos/cenas/480p15/S0.mp4", b"mp4"),
            Produce("__pycache__/cenas.cpython-312.pyc", b"pyc"),
            Produce(".pytest_cache/v/cache/lastfailed", b"{}"),
            Produce("media/images/cenas/S0.png", b"png"),
            AssistantText("Renderizei."),
        ],
        [Produce("saida/previa/S1.png", b"png"), AssistantText("Só renderizei.")],
    ]
    async with open_lesson(tmp_path, scenario) as user:
        await send(user, "luz azul", last="Renderizei.")
        await send(user, "renderiza S1", last="Só renderizei.")
        latest, first = history_of(tmp_path)

    assert files_in(first) == {"cenas.py": "COR_LUZ = BRANCO\n"}
    assert files_in(latest) == {"cenas.py": "COR_LUZ = AZUL\n"}


async def test_it_works_in_folders_with_spaces_and_accents(tmp_path):
    lesson = tmp_path / "Documentos" / "Aulas Manim" / "Aula 09 - Minkowski"
    lesson.mkdir(parents=True)
    (lesson / "anotações.md").write_text("Contração\n", encoding="utf-8")
    scenario = [[EditFile("anotações.md", "Contração do comprimento\n"), AssistantText("Anotei.")]]
    async with open_lesson(lesson, scenario) as user:
        await send(user, "anota a contração", last="Anotei.")
        latest, first = history_of(lesson)

    assert files_in(first) == {"anotações.md": "Contração\n"}
    assert subject(latest) == "Pedido: anota a contração"
    assert files_in(latest) == {"anotações.md": "Contração do comprimento\n"}


async def test_a_lesson_inside_another_repository_gets_its_own_history(tmp_path):
    pygit2.init_repository(str(tmp_path))
    lesson = tmp_path / "Aula 01"
    lesson.mkdir()
    (lesson / "cenas.py").write_text("x = 1\n", encoding="utf-8")

    async with open_lesson(lesson):
        (first,) = history_of(lesson)

    assert files_in(first) == {"cenas.py": "x = 1\n"}
    assert history_of(tmp_path) == []


async def test_edits_made_outside_manimflow_are_committed_apart_from_the_agents_turn(tmp_path):
    (tmp_path / "fisica.py").write_text("g = 9.8\n", encoding="utf-8")
    (tmp_path / "cenas.py").write_text("COR = AZUL\n", encoding="utf-8")
    scenario = [[EditFile("cenas.py", "COR = VERDE\n"), AssistantText("Verde.")]]
    async with open_lesson(tmp_path, scenario) as user:
        # The teacher fixes the physics in their own editor, then asks for a change.
        (tmp_path / "fisica.py").write_text("g = 9.81\n", encoding="utf-8")
        await send(user, "luz verde", last="Verde.")
        agent, outside, first = history_of(tmp_path)

    assert subject(outside) == "Edições feitas fora do ManimFlow"
    assert files_in(outside) == {"fisica.py": "g = 9.81\n", "cenas.py": "COR = AZUL\n"}
    assert subject(agent) == "Pedido: luz verde"
    assert files_in(agent) == {"fisica.py": "g = 9.81\n", "cenas.py": "COR = VERDE\n"}


async def test_a_failed_commit_is_reported_and_the_chat_recovers(tmp_path):
    (tmp_path / "cenas.py").write_text("COR = AZUL\n", encoding="utf-8")
    scenario = [
        [EditFile("cenas.py", "COR = VERDE\n"), AssistantText("Verde.")],
        [EditFile("cenas.py", "COR = AMARELO\n"), AssistantText("Amarelo.")],
    ]
    async with open_lesson(tmp_path, scenario) as user:
        # Left behind by a crash: no commit can be written until it is gone.
        lock = tmp_path / ".git" / "index.lock"
        lock.touch()
        await send(user, "luz verde", last="Verde.")
        await user.should_see("Não foi possível salvar uma versão desta mudança.")

        lock.unlink()
        await send(user, "luz amarela", last="Amarelo.")
        latest, *_ = history_of(tmp_path)

    assert subject(latest) == "Pedido: luz amarela"
    assert files_in(latest) == {"cenas.py": "COR = AMARELO\n"}


async def test_the_next_message_carries_the_teachers_edits_since_the_agents_last_turn(tmp_path):
    # LF on every platform, so the blob ids in the expected diff hold on Windows too.
    (tmp_path / "fisica.py").write_text("g = 9.8\nm = 2\n", encoding="utf-8", newline="\n")
    (tmp_path / "cenas.py").write_text("COR = AZUL\n", encoding="utf-8", newline="\n")
    scenario = [[EditFile("cenas.py", "COR = VERDE\n"), AssistantText("Verde.")], [AssistantText("Vi.")]]
    agent = ScriptedAgent(scenario)
    async with user_simulation(root=lesson_page(agent, tmp_path)) as user:
        await user.open("/")
        await send(user, "luz verde", last="Verde.")

        # The teacher fixes the physics and takes a note in their own editor.
        (tmp_path / "fisica.py").write_text("g = 9.81\nm = 2\n", encoding="utf-8", newline="\n")
        (tmp_path / "notas.md").write_text("Conferir g.\n", encoding="utf-8", newline="\n")
        await send(user, "confira", last="Vi.")

    first, second = agent.received
    assert attached(first) == {}
    # The agent's own change to cenas.py is not in it.
    assert attached(second) == {
        "edicoes-manuais.diff": "diff --git a/fisica.py b/fisica.py\n"
        "index 8ae8599..b21e809 100644\n"
        "--- a/fisica.py\n"
        "+++ b/fisica.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-g = 9.8\n"
        "+g = 9.81\n"
        " m = 2\n"
        "diff --git a/notas.md b/notas.md\n"
        "new file mode 100644\n"
        "index 0000000..ef76d4c\n"
        "--- /dev/null\n"
        "+++ b/notas.md\n"
        "@@ -0,0 +1 @@\n"
        "+Conferir g.\n"
    }


async def test_a_turn_that_changes_nothing_still_takes_the_edits_with_it(tmp_path):
    (tmp_path / "fisica.py").write_text("g = 9.8\n", encoding="utf-8")
    agent = ScriptedAgent([[AssistantText("Conferi.")], [AssistantText("Pronto.")]])
    async with user_simulation(root=lesson_page(agent, tmp_path)) as user:
        await user.open("/")
        (tmp_path / "fisica.py").write_text("g = 9.81\n", encoding="utf-8")
        await send(user, "confere a física", last="Conferi.")
        await send(user, "agora a cor", last="Pronto.")

    first, second = agent.received
    assert attached(first)
    assert attached(second) == {}


async def test_a_deleted_file_leaves_the_next_version(tmp_path):
    (tmp_path / "fisica.py").write_text("g = 9.8\n", encoding="utf-8")
    (tmp_path / "rascunho.py").write_text("x = 1\n", encoding="utf-8")
    async with open_lesson(tmp_path, [[AssistantText("Ok.")]]) as user:
        (tmp_path / "rascunho.py").unlink()
        await send(user, "segue", last="Ok.")
        latest, _ = history_of(tmp_path)

    assert files_in(latest) == {"fisica.py": "g = 9.8\n"}


def test_each_agent_turns_version_is_found_by_the_turns_id(tmp_path):
    history = History.open(tmp_path)
    (tmp_path / "cenas.py").write_text("x = 1\n", encoding="utf-8")
    saved = history.commit_agent_turn("luz amarela", "turno-7")
    history.commit_agent_turn("nada mudou", "turno-8")

    versions = history.turn_versions()

    assert list(versions) == ["turno-7"]
    assert versions["turno-7"].id == saved
    assert versions["turno-7"].message == "Pedido: luz amarela"
