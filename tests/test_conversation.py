"""A lesson has one conversation, which the server keeps: it survives leaving the page,
a turn runs to its end whoever watches it, and the page says what the agent is doing."""

import asyncio
import shutil
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

import pygit2
from nicegui import ElementFilter, ui
from nicegui.testing.user_simulation import user_simulation

from manimflow import conversation
from manimflow.agent import AssistantText, Checklist, ChecklistStep, CommandFinished, CommandStarted, Working
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, ScriptedAgent
from manimflow.versioning import History

SCAFFOLD = Path(str(files("manimflow"))) / "modelo"


@asynccontextmanager
async def lesson_screen(agent, lesson):
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find(marker="send").click()


def chat(user):
    """The text of every label and markdown in the conversation, in page order."""
    with user:
        (column,) = user.find(marker="conversation").elements
        return [
            element.text if isinstance(element, ui.label) else element.content
            for element in column.descendants()
            if isinstance(element, (ui.label, ui.markdown))
        ]


def buttons(user):
    with user:
        return [button.text for button in ElementFilter(kind=ui.button) if button.text]


async def test_coming_back_to_the_lesson_shows_the_conversation_and_continues_it(tmp_path):
    agent = ScriptedAgent([[AssistantText("A luz agora é amarela.")], [AssistantText("E o fundo, branco.")]])
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "muda a cor da luz para amarelo")
        await user.should_see("A luz agora é amarela.")
        await user.should_not_see(marker="progress")

        await user.open("/")

        await user.should_see("A luz agora é amarela.")
        assert chat(user) == ["muda a cor da luz para amarelo", "A luz agora é amarela."]
        # One conversation per lesson: nothing to list or start over.
        assert "Anteriores" not in buttons(user)
        assert "Nova" not in buttons(user)

        send(user, "agora o fundo branco")
        await user.should_see("E o fundo, branco.")
    assert [message.text for message in agent.received] == ["muda a cor da luz para amarelo", "agora o fundo branco"]


async def test_after_a_restart_the_conversation_is_read_back_with_its_versions(tmp_path):
    agent = ScriptedAgent([[EditFile("cenas.py", "COR_LUZ = AMARELO\n"), AssistantText("Pronto.")]])
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "luz amarela")
        await user.should_see(marker="checkpoint", retries=100)

    # A new launch of ManimFlow keeps nothing of the conversation in memory.
    conversation.forget(agent, tmp_path)
    async with lesson_screen(agent, tmp_path) as user:
        await user.should_see("Pronto.")
        assert chat(user)[:2] == ["luz amarela", "Arquivo criado: cenas.py"]
        await user.should_see(marker="result-code")
        # The version the turn saved, found again by the turn's id.
        await user.should_see(marker="restore")


async def test_a_turn_goes_on_when_the_page_is_left_and_the_page_joins_it_again(tmp_path):
    agent = ScriptedAgent(
        [[AssistantText("Começando."), EditFile("cenas.py", "x = 1\n"), AssistantText("Terminei.")]], delay=0.4
    )
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "faz a animação")
        await user.should_see("Começando.", retries=20)

        await user.open("/")

        # The running turn, with what it showed so far, and the bar of what it is doing.
        await user.should_see("Começando.")
        await user.should_see(marker="progress")
        await user.should_see("Terminei.", retries=40)
        await user.should_see(marker="checkpoint", retries=100)
        await user.should_not_see(marker="progress", retries=20)
    repo = pygit2.Repository(str(tmp_path / ".git"))
    assert repo[repo.head.target].message.startswith("Pedido: faz a animação")


async def test_the_progress_bar_says_what_the_agent_is_doing_and_its_steps(tmp_path):
    steps = Checklist(
        (
            ChecklistStep("Ler o plano", "completed"),
            ChecklistStep("Desenhar a cena", "inProgress"),
            ChecklistStep("Renderizar a prévia", "pending"),
        )
    )
    scenario = [
        [
            CommandStarted("1", "cat plano.yaml; cat cenas.py", reads=("plano.yaml", "cenas.py")),
            CommandFinished("1", "cat plano.yaml; cat cenas.py", 0),
            steps,
            # Thinking between two steps leaves the bar on the last step.
            Working("Pensando"),
            Working("Escrevendo a resposta"),
            AssistantText("Pronto."),
        ]
    ]
    agent = ScriptedAgent(scenario, delay=0.5)
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "desenha")

        await user.should_see("Lendo o plano e as cenas…", retries=30)
        await user.should_see("Etapa 2 de 3: Desenhar a cena", retries=30)
        await user.should_see("Lendo o plano e as cenas…")
        await user.should_not_see("Pensando…")
        await user.should_see("Escrevendo a resposta…", retries=30)
        await user.should_see("Pronto.", retries=30)
        await user.should_not_see(marker="progress")
        # The bar's labels never land in the conversation.
        assert "Escrevendo a resposta…" not in chat(user)


async def test_parar_stops_the_turn(tmp_path):
    scenario = [[AssistantText("Começando."), AssistantText("Ainda trabalhando."), AssistantText("Terminei.")]]
    agent = ScriptedAgent(scenario, delay=0.5)
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "faz tudo")
        await user.should_see("Começando.", retries=20)

        user.find(marker="stop").click()

        await user.should_see("Erro do agente: A resposta foi interrompida antes de terminar.", retries=30)
        await user.should_not_see(marker="progress")
        assert "Terminei." not in chat(user)


def stage(user):
    """The step the lesson is at, and the steps it went through."""
    with user:
        found = {}
        for state in ("done", "now", "wait"):
            found[state] = [
                label.text
                for element in ElementFilter(marker=f"stage-{state}")
                for label in element.descendants()
                if isinstance(label, ui.label)
            ]
        return found


async def test_the_lesson_shows_where_it_is_in_its_making(tmp_path):
    lesson = tmp_path / "Aula"
    shutil.copytree(SCAFFOLD, lesson)
    History.open(lesson)
    async with lesson_screen(ScriptedAgent([]), lesson) as user:
        await user.should_see(marker="lesson-stage")
        assert stage(user) == {"done": [], "now": ["Plano"], "wait": []}


async def test_a_plan_that_waits_for_the_teacher_marks_the_approval_step(lesson):
    async with lesson_screen(ScriptedAgent([]), lesson) as user:
        await user.should_see(marker="lesson-stage")
        assert stage(user) == {"done": ["Plano"], "now": [], "wait": ["Sua aprovação"]}


def test_the_agent_hears_which_lesson_and_turma_the_teacher_has_open(lesson):
    turma = lesson.parent
    (turma / "turma.md").write_text("# Física II\n", encoding="utf-8")

    context = conversation.lesson_context(lesson)

    assert f"- Aula: {lesson.name}" in context
    assert f"- Turma: {turma.name}" in context
    assert "- Situação: Plano para aprovar" in context
    assert "- Estados do plano: S0 · Quadrado; S1 · Quadrado deslocado" in context
    assert "exemplo" not in context


async def test_a_page_that_joins_a_turn_leaves_the_agents_plan_edits_to_the_agent(lesson):
    History.open(lesson).approve_plan()
    changed = (lesson / "plano.yaml").read_text(encoding="utf-8").replace("Quadrado deslocado", "Quadrado bem longe")
    agent = ScriptedAgent([[EditFile("plano.yaml", changed), AssistantText("Mudei o plano."), AssistantText("Pronto.")]], delay=0.6)
    async with lesson_screen(agent, lesson) as user:
        send(user, "desloca mais o quadrado")
        await user.should_see("Mudei o plano.", retries=30)

        # Coming back while the agent works.
        await user.open("/")
        await user.should_see("Pronto.", retries=40)
        await user.should_not_see(marker="progress", retries=40)

    repo = pygit2.Repository(str(lesson / ".git"))
    messages = [commit.message.partition("\n\nTurno: ")[0] for commit in repo.walk(repo.head.target)]
    assert messages[0] == "Pedido: desloca mais o quadrado"
    assert "Edição manual em plano.yaml" not in messages


class SlowToStart(ScriptedAgent):
    """An agent whose conversation takes a while to start, as Codex resuming a thread."""

    async def session(self, lesson):
        await asyncio.sleep(1.0)
        return await super().session(lesson)


async def test_parar_before_the_turn_reaches_the_agent_keeps_it_from_starting(tmp_path):
    agent = SlowToStart([[AssistantText("Comecei mesmo assim.")]])
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "faz tudo")
        await user.should_see(marker="progress")

        user.find(marker="stop").click()

        await user.should_see("Erro do agente: A resposta foi interrompida antes de terminar.", retries=40)
        await user.should_not_see(marker="progress")
    assert agent.received == []


async def test_turns_drawn_again_show_small_cards_since_the_plan_may_have_changed(lesson):
    History.open(lesson).approve_plan()
    changed = (lesson / "plano.yaml").read_text(encoding="utf-8").replace("Quadrado deslocado", "Quadrado bem longe")
    agent = ScriptedAgent([[EditFile("plano.yaml", changed), AssistantText("Mudei o plano.")]])
    async with lesson_screen(agent, lesson) as user:
        send(user, "desloca mais o quadrado")
        await user.should_see("Plano · 2 estados, 1 transição", retries=100)
        await user.should_not_see(marker="progress", retries=100)

        await user.open("/")

        await user.should_see("Plano atualizado")
        await user.should_not_see("Plano · 2 estados, 1 transição")


async def test_a_conversation_that_starts_over_reloads_its_pages(tmp_path):
    agent = ScriptedAgent([[AssistantText("Oi.")]])
    talk = conversation.conversation(agent, tmp_path)
    closed = []

    class Page:
        def conversation_closed(self):
            closed.append(True)

    talk.listen(Page())

    conversation.forget(agent, tmp_path)

    assert closed == [True]
    assert talk.closed
    assert conversation.conversation(agent, tmp_path) is not talk


async def test_a_history_that_couldnt_be_read_is_read_again_by_the_next_page(tmp_path):
    class Flaky(ScriptedAgent):
        tries = 0

        async def lesson_history(self, lesson):
            self.tries += 1
            if self.tries == 1:
                raise ConnectionError("app-server still starting")
            return await super().lesson_history(lesson)

    agent = Flaky([])
    talk = conversation.conversation(agent, tmp_path)

    await talk.load()
    assert not talk.loaded
    await talk.load()
    assert talk.loaded


async def test_without_the_earlier_messages_the_chat_still_works(tmp_path):
    class NoHistory(ScriptedAgent):
        async def lesson_history(self, lesson):
            raise ConnectionError("app-server still starting")

    agent = NoHistory([[AssistantText("Recebi.")]])
    async with lesson_screen(agent, tmp_path) as user:
        await user.should_see("Não foi possível mostrar as mensagens anteriores agora.")

        send(user, "oi")

        await user.should_see("Recebi.", retries=30)
    assert [message.text for message in agent.received] == ["oi"]


async def test_a_turn_sent_after_a_failed_read_shows_once_when_the_read_works_again(tmp_path):
    class Flaky(ScriptedAgent):
        tries = 0

        async def lesson_history(self, lesson):
            self.tries += 1
            if self.tries == 1:
                raise ConnectionError("app-server still starting")
            return await super().lesson_history(lesson)

    agent = Flaky([[AssistantText("Começando."), AssistantText("Recebi.")]], delay=0.5)
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "oi")
        await user.should_see("Começando.", retries=30)
        # Back during the turn, then again once it ended.
        await user.open("/")
        await user.should_see("Recebi.", retries=30)
        await user.should_not_see(marker="progress", retries=30)

        await user.open("/")

        await user.should_see("Recebi.")
        assert chat(user).count("Recebi.") == 1
        assert chat(user).count("oi") == 1


async def test_a_page_that_opens_while_the_conversation_starts_over_shows_the_new_one(tmp_path):
    agent = ScriptedAgent([[AssistantText("Antiga.")]])
    async with lesson_screen(agent, tmp_path) as user:
        send(user, "oi")
        await user.should_see("Antiga.", retries=30)
        await user.should_not_see(marker="progress", retries=30)
        # As "Restaurar exemplo" in another tab: closed, its threads being put away.
        conversation.conversation(agent, tmp_path).closed = True

        async def restored():
            await asyncio.sleep(0.5)
            await agent.archive(tmp_path)
            conversation.forget(agent, tmp_path)

        restoring = asyncio.create_task(restored())
        await user.open("/")
        await restoring

        await user.should_see(marker="message", retries=50)
        await user.should_not_see("Antiga.", retries=50)


async def test_a_read_that_a_turn_overlapped_is_not_kept(tmp_path):
    class SlowAfterAFailure(ScriptedAgent):
        tries = 0

        async def lesson_history(self, lesson):
            self.tries += 1
            if self.tries == 1:
                raise ConnectionError("app-server still starting")
            await asyncio.sleep(0.5)
            return await super().lesson_history(lesson)

    agent = SlowAfterAFailure([[AssistantText("Começando."), AssistantText("Recebi.")]], delay=0.3)
    async with lesson_screen(agent, tmp_path) as user:
        talk = conversation.conversation(agent, tmp_path)
        # Another tab reads the history again while this one sends a message.
        reading = asyncio.create_task(talk.load())
        await asyncio.sleep(0.1)
        send(user, "oi")
        await reading

        assert not talk.loaded
        await user.should_see("Recebi.", retries=30)
        await user.should_not_see(marker="progress", retries=30)
        await user.open("/")
        await user.should_see("Recebi.", retries=30)
        assert chat(user).count("oi") == 1
