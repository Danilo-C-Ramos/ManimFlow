import asyncio
import shutil
from contextlib import asynccontextmanager

import pygit2
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AgentError, AssistantText
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, ScriptedAgent

from conftest import FIXTURES


@asynccontextmanager
async def open_lesson(lesson, scenario=(), delay=0.0):
    """Opens the lesson's page with a scripted agent, yielding the simulated user and the agent."""
    agent = ScriptedAgent(list(scenario), delay=delay)
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user, agent


def minimal_lesson(tmp_path):
    lesson = tmp_path / "Aula Mínima"
    shutil.copytree(FIXTURES / "aula_minima", lesson)
    # LF on every platform, as the agent writes it.
    (lesson / "fisica.py").write_text("VELOCIDADE = 1.0\n", encoding="utf-8", newline="\n")
    return lesson


def editor(user):
    with user:
        (element,) = user.find(marker="code").elements
        assert isinstance(element, ui.codemirror)
        return element


async def test_the_editor_shows_the_physics_file_and_switches_to_the_scenes_file(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()

        assert editor(user).language == "Python"
        assert editor(user).value == "VELOCIDADE = 1.0\n"

        user.find("cenas.py").click()
        assert editor(user).value == (lesson / "cenas.py").read_text(encoding="utf-8")


def history_of(lesson):
    """Every commit in the lesson's own repository, newest first, read the way any git tool would."""
    repo = pygit2.Repository(str(lesson / ".git"))
    return list(repo.walk(repo.head.target))


async def test_renderizar_saves_the_edit_and_commits_it_as_a_manual_edit(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find(marker="code").type("ACELERACAO = 9.8\n")
        user.find("Renderizar").click()

        await user.should_see("Prévia atualizada.", retries=600)
        assert (lesson / "fisica.py").read_text(encoding="utf-8") == "VELOCIDADE = 1.0\nACELERACAO = 9.8\n"
        newest = history_of(lesson)[0]
        assert newest.message == "Edição manual em fisica.py"
        assert newest.tree["fisica.py"].data == b"VELOCIDADE = 1.0\nACELERACAO = 9.8\n"


async def test_renderizar_keeps_the_files_line_endings(tmp_path):
    lesson = minimal_lesson(tmp_path)
    # As an editor on Windows would have left it.
    (lesson / "fisica.py").write_bytes(b"VELOCIDADE = 1.0\r\n")
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find(marker="code").type("ACELERACAO = 9.8\n")
        user.find("Renderizar").click()

        await user.should_see("Prévia atualizada.", retries=600)
        assert (lesson / "fisica.py").read_bytes() == b"VELOCIDADE = 1.0\r\nACELERACAO = 9.8\r\n"


async def send(user, text, last):
    """Sends `text` to the agent and waits until its turn has ended, `last` being the turn's last text."""
    user.find(marker="message").type(text)
    user.find("Enviar").click()
    # Each turn commits a version, which takes seconds on Windows.
    await user.should_see(last, retries=100)
    await user.should_not_see("O agente está trabalhando…", retries=100)


async def test_the_next_message_carries_the_manual_edit_diff_only_once(tmp_path):
    lesson = minimal_lesson(tmp_path)
    scenario = [[AssistantText("Vi a sua correção.")], [AssistantText("Feito.")]]
    async with open_lesson(lesson, scenario) as (user, agent):
        user.find("Código").click()
        user.find(marker="code").type("ACELERACAO = 9.8\n")
        user.find("Renderizar").click()
        await user.should_see("Prévia atualizada.", retries=600)

        await send(user, "use a minha aceleração", "Vi a sua correção.")
        await send(user, "agora deixe azul", "Feito.")

        first, second = agent.received
        assert first.text == "use a minha aceleração"
        (diff,) = first.attachments.values()
        assert "+ACELERACAO = 9.8" in diff
        assert "a/fisica.py" in diff
        assert second.text == "agora deixe azul"
        assert second.attachments == {}


def status(user):
    """The texts the code tab shows about the last "Renderizar"."""
    with user:
        (column,) = user.find(marker="render-status").elements
        return [element.text for element in column.descendants() if isinstance(element, ui.label)]


async def test_a_scene_that_fails_to_render_is_reported_in_portuguese(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find("cenas.py").click()
        user.find(marker="code").type("\nraise ValueError('sinal trocado')\n")
        user.find("Renderizar").click()

        await user.should_see("A cena S0 não renderizou:", retries=600)
        assert status(user) == ["A cena S0 não renderizou:", "ValueError: sinal trocado"]
        assert history_of(lesson)[0].message == "Edição manual em cenas.py"


async def eventually(check, seconds=3.0):
    """Waits for `check()` to hold, as the editor looks at the lesson on its own schedule."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


async def test_the_editor_reloads_a_file_the_agent_changed(tmp_path):
    lesson = minimal_lesson(tmp_path)
    scenario = [[EditFile("fisica.py", "VELOCIDADE = 2.0\n"), AssistantText("Dobrei a velocidade.")]]
    async with open_lesson(lesson, scenario) as (user, _):
        user.find("Código").click()

        await send(user, "dobre a velocidade", "Dobrei a velocidade.")

        await eventually(lambda: editor(user).value == "VELOCIDADE = 2.0\n")
        await user.should_not_see("Manter as minhas edições")


async def test_unsaved_edits_are_kept_and_the_teacher_is_warned_when_the_agent_changes_the_file(tmp_path):
    lesson = minimal_lesson(tmp_path)
    scenario = [
        [EditFile("fisica.py", "VELOCIDADE = 2.0\n"), AssistantText("Dobrei a velocidade.")],
        [EditFile("fisica.py", "VELOCIDADE = 3.0\n"), AssistantText("Triplicada.")],
    ]
    async with open_lesson(lesson, scenario) as (user, _):
        user.find("Código").click()
        user.find(marker="code").type("# minha nota\n")

        await send(user, "dobre a velocidade", "Dobrei a velocidade.")
        await user.should_see("fisica.py foi alterado fora do editor enquanto você o editava.", retries=20)
        assert editor(user).value == "VELOCIDADE = 1.0\n# minha nota\n"

        user.find("Manter as minhas edições").click()
        await user.should_not_see("fisica.py foi alterado fora do editor enquanto você o editava.")
        assert editor(user).value == "VELOCIDADE = 1.0\n# minha nota\n"

        await send(user, "triplique", "Triplicada.")
        await user.should_see("fisica.py foi alterado fora do editor enquanto você o editava.", retries=20)
        user.find("Carregar a versão nova").click()
        assert editor(user).value == "VELOCIDADE = 3.0\n"
        await user.should_not_see("fisica.py foi alterado fora do editor enquanto você o editava.")


def render_enabled(user):
    with user:
        (button,) = user.find("Renderizar").elements
        return button.enabled


async def test_renderizar_waits_for_the_agent_to_finish_its_turn(tmp_path):
    lesson = minimal_lesson(tmp_path)
    scenario = [[AssistantText("Começando."), AssistantText("Terminei.")]]
    async with open_lesson(lesson, scenario, delay=0.5) as (user, _):
        user.find("Código").click()
        user.find(marker="message").type("faça a animação")
        user.find("Enviar").click()

        await user.should_see("Começando.", retries=20)
        assert not render_enabled(user)

        await user.should_see("Terminei.", retries=20)
        await user.should_not_see("O agente está trabalhando…")
        assert render_enabled(user)


async def test_a_diff_that_cannot_be_read_is_reported_and_the_message_still_goes(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson, [[AssistantText("Feito.")]]) as (user, agent):
        # Left behind by a crash: git can't read the lesson until it is gone.
        (lesson / ".git" / "index.lock").touch()
        (lesson / "fisica.py").write_text("VELOCIDADE = 5.0\n", encoding="utf-8")

        await send(user, "use a minha velocidade", "Feito.")

        await user.should_see("Não foi possível mandar ao agente as suas edições no código.")
        (received,) = agent.received
        assert received.text == "use a minha velocidade"


async def test_a_failed_commit_is_reported_and_the_preview_still_renders(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        # Left behind by a crash: no commit can be written until it is gone.
        (lesson / ".git" / "index.lock").touch()
        user.find("Código").click()
        user.find(marker="code").type("ACELERACAO = 9.8\n")
        user.find("Renderizar").click()

        await user.should_see("Prévia atualizada.", retries=600)
        await user.should_see("Não foi possível salvar uma versão desta mudança.")
        assert (lesson / "fisica.py").read_text(encoding="utf-8") == "VELOCIDADE = 1.0\nACELERACAO = 9.8\n"


async def test_renderizar_warns_instead_of_saving_over_a_change_the_editor_has_not_seen_yet(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find(marker="code").type("# minha nota\n")

        # Clicked before the editor's next look at the lesson.
        (lesson / "fisica.py").write_text("VELOCIDADE = 2.0\n", encoding="utf-8")
        user.find("Renderizar").click()

        await user.should_see("fisica.py foi alterado fora do editor enquanto você o editava.")
        assert (lesson / "fisica.py").read_text(encoding="utf-8") == "VELOCIDADE = 2.0\n"
        assert editor(user).value == "VELOCIDADE = 1.0\n# minha nota\n"


def previewed(lesson):
    """The scenes that have a preview image."""
    return sorted(path.stem for path in (lesson / "saida" / "previa" / "png").glob("*.png"))


async def test_renderizar_previews_only_the_scenes_an_edit_to_the_scenes_file_affects(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find("cenas.py").click()
        scenes = editor(user).value
        user.find(marker="code").clear().type(scenes.replace("run_time=0.5", "run_time=0.4"))
        user.find("Renderizar").click()

        await user.should_see("Prévia atualizada.", retries=600)
    assert previewed(lesson) == ["T01"]


async def test_renderizar_previews_every_scene_after_an_edit_to_the_physics(tmp_path):
    lesson = minimal_lesson(tmp_path)
    async with open_lesson(lesson) as (user, _):
        user.find("Código").click()
        user.find(marker="code").type("ACELERACAO = 9.8\n")
        user.find("Renderizar").click()

        await user.should_see("Prévia atualizada.", retries=600)
    assert previewed(lesson) == ["S0", "T01"]


async def test_the_diff_goes_again_when_the_agent_never_got_the_message(tmp_path):
    lesson = minimal_lesson(tmp_path)
    scenario = [
        # As Codex does when its sandbox can't start.
        [AgentError("O agente não consegue rodar comandos.", delivered=False)],
        [AssistantText("Vi a sua correção.")],
    ]
    async with open_lesson(lesson, scenario) as (user, agent):
        (lesson / "fisica.py").write_text("VELOCIDADE = 5.0\n", encoding="utf-8", newline="\n")

        await send(user, "use a minha velocidade", "O agente não consegue rodar comandos.")
        await send(user, "tente de novo", "Vi a sua correção.")

        _, retry = agent.received
        (diff,) = retry.attachments.values()
        assert "+VELOCIDADE = 5.0" in diff
