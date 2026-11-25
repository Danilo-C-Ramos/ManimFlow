"""Until the teacher first approves a plan, a message asks the agent for the plan in a fixed
format, and ManimFlow writes plano.yaml itself, so a model that only describes the plan
in the chat still leaves cards to approve."""

import json
import shutil
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

import yaml
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow import plan_turn
from manimflow.agent import AssistantText
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, ScriptedAgent
from manimflow.plan import load_plan, validate_plan
from manimflow.versioning import History, plan_approved

SCAFFOLD = Path(str(files("manimflow"))) / "modelo"
TURN = 100

PLAN = {
    "estados": [
        {"id": "S0", "titulo": "Eixos", "visivel": "Os eixos x e y.", "cena": "S0_Eixos"},
        {"id": "S1", "titulo": "Reta", "visivel": "A reta f(x) = 2x + 1.", "cena": "S1_Reta"},
    ],
    "transicoes": [{"de": "S0", "para": "S1", "descricao": "A reta é traçada.", "duracao": 3, "cena": "S1_Reta"}],
}


def reply(message, plan=None, approved=False):
    """The agent's last text in a plan turn."""
    return AssistantText(json.dumps({"mensagem": message, "plano": plan, "aprovado": approved}, ensure_ascii=False))


def new_lesson(tmp_path):
    lesson = tmp_path / "Função afim"
    shutil.copytree(SCAFFOLD, lesson)
    History.open(lesson)
    return lesson


def test_a_new_lesson_waits_for_its_plan_until_the_first_approval(tmp_path):
    lesson = new_lesson(tmp_path)
    assert plan_turn.pending(lesson)

    assert plan_turn.apply(lesson, plan_turn.PlanReply("", PLAN, False)) == []
    # The agent's plan waits for the teacher.
    assert plan_turn.pending(lesson)

    History.open(lesson).approve_plan()
    assert not plan_turn.pending(lesson)


def test_a_folder_without_a_plan_is_no_plan_turn(tmp_path):
    assert not plan_turn.pending(tmp_path)


def test_the_plan_is_written_with_an_empty_scene_for_each_scene_it_names(tmp_path):
    lesson = new_lesson(tmp_path)

    assert plan_turn.apply(lesson, plan_turn.PlanReply("Plano.", PLAN, False)) == []

    assert validate_plan(lesson).ok
    plan, _ = load_plan(lesson)
    assert [(state.id, state.scene) for state in plan.states] == [("S0", "S0_Eixos"), ("S1", "S1_Reta")]
    scenes = (lesson / "cenas.py").read_text(encoding="utf-8")
    assert "class S0_Eixos(manim.Scene):" in scenes
    assert "class S1_Reta(manim.Scene):" in scenes
    # The untouched scaffold starts over: the placeholder's scene goes with the placeholder.
    assert "S0_Inicio" not in scenes


def test_scenes_the_agent_already_drew_are_kept(tmp_path):
    lesson = new_lesson(tmp_path)
    drawn = "from manim import MovingCameraScene\n\n\nclass S1_Reta(MovingCameraScene):\n    def construct(self):\n        self.wait()\n"
    (lesson / "cenas.py").write_text(drawn, encoding="utf-8")

    assert plan_turn.apply(lesson, plan_turn.PlanReply("Plano.", PLAN, False)) == []

    scenes = (lesson / "cenas.py").read_text(encoding="utf-8")
    assert scenes.startswith(drawn)
    # The new scene brings its own base, since the file never imported Scene.
    assert "import manim\n" in scenes
    assert "class S0_Eixos(manim.Scene):" in scenes
    namespace: dict = {}
    exec(compile(scenes, "cenas.py", "exec"), namespace)
    assert issubclass(namespace["S0_Eixos"], namespace["manim"].Scene)


def test_an_aliased_manim_import_still_gets_the_name_the_new_scenes_use(tmp_path):
    lesson = new_lesson(tmp_path)
    (lesson / "cenas.py").write_text("import manim as mn\n\n\nclass S1_Reta(mn.Scene):\n    pass\n", encoding="utf-8")

    assert plan_turn.apply(lesson, plan_turn.PlanReply("Plano.", PLAN, False)) == []

    namespace: dict = {}
    exec(compile((lesson / "cenas.py").read_text(encoding="utf-8"), "cenas.py", "exec"), namespace)
    assert "S0_Eixos" in namespace


def test_the_teachers_edits_to_the_placeholder_scene_are_kept(tmp_path):
    lesson = new_lesson(tmp_path)
    edited = (lesson / "cenas.py").read_text(encoding="utf-8").replace("pass", "self.wait(2)  # minha pausa")
    (lesson / "cenas.py").write_text(edited, encoding="utf-8")

    assert plan_turn.apply(lesson, plan_turn.PlanReply("Plano.", PLAN, False)) == []

    assert (lesson / "cenas.py").read_text(encoding="utf-8").startswith(edited)


def test_a_plan_that_breaks_the_rules_is_reported_and_leaves_the_files_alone(tmp_path):
    lesson = new_lesson(tmp_path)
    before = {name: (lesson / name).read_text(encoding="utf-8") for name in ("plano.yaml", "cenas.py")}
    broken = {**PLAN, "transicoes": [{**PLAN["transicoes"][0], "de": "S7"}]}

    errors = plan_turn.apply(lesson, plan_turn.PlanReply("Plano.", broken, False))

    assert any("S7" in error for error in errors)
    assert {name: (lesson / name).read_text(encoding="utf-8") for name in before} == before


def test_only_a_plan_turns_answer_is_read_as_one():
    assert plan_turn.parse('{"mensagem": "Oi.", "plano": null, "aprovado": true}') == plan_turn.PlanReply(
        "Oi.", None, True
    )
    assert plan_turn.parse("Vou seguir a etapa de planejamento.") is None
    assert plan_turn.parse('{"outra": 1}') is None


@asynccontextmanager
async def lesson_screen(agent, lesson):
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find(marker="send").click()


async def test_a_new_lessons_first_message_brings_the_plan_as_cards_to_approve(tmp_path):
    lesson = new_lesson(tmp_path)
    agent = ScriptedAgent(
        [
            [reply("Proponho dois estados: os eixos e depois a reta.", PLAN)],
            [AssistantText("Desenhei as cenas.")],
        ]
    )
    async with lesson_screen(agent, lesson) as user:
        send(user, "Faça um gráfico de função afim")

        await user.should_see("Proponho dois estados: os eixos e depois a reta.", retries=TURN)
        await user.should_see(marker="result-plan", retries=TURN)
        # The plan shows on its tab and in the chat, with the approval at hand.
        with user:
            (tabs,) = user.find(marker="workspace-tabs").elements
            assert tabs.value == "Plano"
        await user.should_see(marker="approve-in-chat-button", retries=TURN)
        await user.should_see(marker="approve-bar")

        user.find(marker="approve-in-chat-button").click()
        await user.should_see("Desenhei as cenas.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)

    first, approval = agent.received
    assert first.output_schema == plan_turn.SCHEMA
    assert "Pedido de plano" in first.attachments[plan_turn.BRIEF]
    assert "Contexto da aula" in first.attachments[plan_turn.BRIEF]
    assert approval.text == "Aprovei o plano como está, sem mudanças nem comentários."
    assert approval.output_schema is None
    # The steps to make the whole lesson now, which GPT-6 Luna needed to do it in one turn,
    # with the lesson already in production: told the plan still waited, Luna stopped.
    assert "faça a aula inteira" in approval.attachments[plan_turn.GO_AHEAD]
    assert "- Situação: Em produção" in approval.attachments["contexto-da-aula.md"]
    assert plan_approved(lesson)
    assert [state.id for state in load_plan(lesson)[0].states] == ["S0", "S1"]


async def test_approving_the_plan_in_words_approves_it_as_the_button_does(tmp_path):
    lesson = new_lesson(tmp_path)
    agent = ScriptedAgent(
        [
            [reply("Proponho dois estados.", PLAN)],
            [reply("Ótimo, vou animar.", approved=True)],
            [AssistantText("Desenhei as cenas.")],
        ]
    )
    async with lesson_screen(agent, lesson) as user:
        send(user, "Faça um gráfico de função afim")
        await user.should_see(marker="result-plan", retries=TURN)

        send(user, "Plano aprovado, pode seguir")

        await user.should_see("Desenhei as cenas.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)
    assert [message.text for message in agent.received] == [
        "Faça um gráfico de função afim",
        "Plano aprovado, pode seguir",
        "Aprovei o plano como está, sem mudanças nem comentários.",
    ]
    assert plan_approved(lesson)


async def test_approved_in_words_the_animation_turn_follows_whatever_the_plan_turn_changed(tmp_path):
    lesson = new_lesson(tmp_path)
    agent = ScriptedAgent(
        [
            [reply("Proponho dois estados.", PLAN)],
            # A plan turn that only took note of the approval: nothing is animated yet.
            [EditFile("CONTEXTO.md", "# Contexto\n\nPlano aprovado.\n"), reply("Ótimo.", approved=True)],
            [AssistantText("Desenhei as cenas.")],
        ]
    )
    async with lesson_screen(agent, lesson) as user:
        send(user, "Faça um gráfico de função afim")
        await user.should_see(marker="result-plan", retries=TURN)
        send(user, "Plano aprovado, pode seguir")

        await user.should_see("Desenhei as cenas.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)

    assert len(agent.received) == 3
    assert plan_approved(lesson)


async def test_a_plan_shaped_answer_outside_a_plan_turn_writes_nothing(lesson):
    History.open(lesson).approve_plan()
    before = (lesson / "plano.yaml").read_text(encoding="utf-8")
    agent = ScriptedAgent([[AssistantText("Vou ver."), reply("Refiz o plano.", PLAN)]], delay=0.3)
    async with lesson_screen(agent, lesson) as user:
        send(user, "muda a cor do quadrado")
        await user.should_see("Vou ver.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)

    assert (lesson / "plano.yaml").read_text(encoding="utf-8") == before


async def test_a_plan_that_cant_be_written_is_reported_and_the_lesson_is_free_again(tmp_path, monkeypatch):
    lesson = new_lesson(tmp_path)

    def locked(lesson, reply):
        raise PermissionError("plano.yaml is open in another program")

    monkeypatch.setattr(plan_turn, "apply", locked)
    agent = ScriptedAgent([[reply("Proponho dois estados.", PLAN)]])
    async with lesson_screen(agent, lesson) as user:
        send(user, "Faça um gráfico de função afim")

        await user.should_see("Não foi possível gravar o plano na pasta da aula.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)


async def test_an_answer_without_the_plan_is_explained_and_the_plan_stays(tmp_path):
    lesson = new_lesson(tmp_path)
    before = (lesson / "plano.yaml").read_text(encoding="utf-8")
    agent = ScriptedAgent([[AssistantText("Vou seguir a etapa de planejamento.")]])
    async with lesson_screen(agent, lesson) as user:
        send(user, "Onda estacionária com 3 harmônicos")

        await user.should_see("O agente não devolveu o plano desta vez.", retries=TURN)
    assert (lesson / "plano.yaml").read_text(encoding="utf-8") == before


async def test_a_question_before_the_plan_gets_an_answer_and_no_plan(tmp_path):
    lesson = new_lesson(tmp_path)
    before = yaml.safe_load((lesson / "plano.yaml").read_text(encoding="utf-8"))
    agent = ScriptedAgent([[reply("Faço animações em Manim para os seus slides.")]])
    async with lesson_screen(agent, lesson) as user:
        send(user, "O que você sabe fazer?")

        await user.should_see("Faço animações em Manim para os seus slides.", retries=TURN)
        await user.should_not_see(marker="progress", retries=TURN)
        with user:
            assert not [element for element in user.find(kind=ui.label).elements if "não devolveu" in element.text]
    assert yaml.safe_load((lesson / "plano.yaml").read_text(encoding="utf-8")) == before


async def test_an_approved_lesson_sends_messages_as_they_are(lesson):
    History.open(lesson).approve_plan()
    agent = ScriptedAgent([[AssistantText("Pronto.")]])
    async with lesson_screen(agent, lesson) as user:
        send(user, "muda a cor do quadrado")
        await user.should_see("Pronto.", retries=TURN)

    (message,) = agent.received
    assert message.output_schema is None
    assert plan_turn.BRIEF not in message.attachments
