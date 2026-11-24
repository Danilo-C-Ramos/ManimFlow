import asyncio
from contextlib import asynccontextmanager

import pygit2
import yaml
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AgentError, AssistantText
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, ScriptedAgent
from manimflow.lessons import Library
from manimflow.preview import REFRESH_INTERVAL

# Tries of should_see, 0.1 s apart, for what follows an agent turn: each turn
# commits a version, which takes seconds on Windows.
TURN = 100


@asynccontextmanager
async def open_lesson(lesson, agent=None):
    agent = agent or ScriptedAgent([])
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def cards(user):
    """What the plan cards show, in order: texts, and each field as "label: value"."""
    with user:
        (column,) = user.find(marker="plan").elements
        shown = []
        for element in column.descendants():
            if isinstance(element, ui.input):
                shown.append(f"{element.props['label']}: {element.value}")
            elif isinstance(element, ui.image):
                path = element.source.split("?")[0]
                shown.append(f"imagem {path[path.index('/saida/') + 1 :]}")
            elif isinstance(element, ui.label) and "plan-hint" not in element._markers:
                shown.append(element.text)
        return shown


async def test_the_cards_show_the_states_in_plan_order_with_the_transitions_between_them(lesson):
    async with open_lesson(lesson) as user:
        assert cards(user) == [
            "Plano",
            "S0",
            "Título: Quadrado",
            "O que aparece: Um quadrado azul no centro.",
            "Comentário: ",
            "~0,5 s · O quadrado anda para a direita.",
            "S1",
            "Título: Quadrado deslocado",
            "O que aparece: O mesmo quadrado, uma unidade à direita.",
            "Talvez deslocar mais.",
            "Comentário: ",
        ]


async def eventually(check, seconds=10.0):
    """Waits for `check()` to hold, as the cards refresh on their own schedule."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


def messages(agent):
    """The text of every message the fake agent received, in order."""
    return [message.text for message in agent.received]


def plan(lesson):
    return yaml.safe_load((lesson / "plano.yaml").read_text(encoding="utf-8"))


def edit(user, marker, text):
    user.find(marker=marker).clear().type(text)


async def test_an_inline_edit_is_written_back_and_keeps_the_rest_of_the_file(manimflow, example):
    before = (example / "plano.yaml").read_text(encoding="utf-8")
    async with open_lesson(example) as user:
        edit(user, "titulo-S2", "Luz até o espelho")
        edit(user, "visivel-S0", "Só os eixos da Terra.")

    after = (example / "plano.yaml").read_text(encoding="utf-8")
    assert after == before.replace("titulo: Reflexão\n", "titulo: Luz até o espelho\n").replace(
        "visivel: Eixos da Terra, a linha da Terra em x = 8 e o herói na origem.\n",
        "visivel: Só os eixos da Terra.\n",
    )
    assert manimflow("plan", "validate", str(example)).returncode == 0


async def test_a_field_left_empty_is_not_written(lesson):
    async with open_lesson(lesson) as user:
        edit(user, "titulo-S0", "  ")

        await user.should_see("Preencha este campo.", retries=TURN)
    assert plan(lesson)["estados"][0]["titulo"] == "Quadrado"


async def test_a_comment_is_attached_to_its_card_and_written_to_the_plan(manimflow, lesson):
    async with open_lesson(lesson) as user:
        user.find(marker="comentario-S0").type("O azul está escuro demais.")
        user.find(marker="comentar-S0").click()

        assert cards(user)[1:6] == [
            "S0",
            "Título: Quadrado",
            "O que aparece: Um quadrado azul no centro.",
            "O azul está escuro demais.",
            "Comentário: ",
        ]
    assert [state.get("comentarios") for state in plan(lesson)["estados"]] == [
        ["O azul está escuro demais."],
        ["Talvez deslocar mais."],
    ]
    assert manimflow("plan", "validate", str(lesson)).returncode == 0


async def test_a_comment_can_be_removed(lesson):
    async with open_lesson(lesson) as user:
        user.find(marker="remover-comentario-S1").click()

        assert "Talvez deslocar mais." not in cards(user)
    assert "comentarios" not in plan(lesson)["estados"][1]


async def test_a_new_state_goes_at_the_end_and_keeps_the_plan_valid(manimflow, lesson):
    async with open_lesson(lesson) as user:
        user.find("+ estado").click()
        edit(user, "titulo-S2", "Quadrado girado")
        edit(user, "visivel-S2", "O quadrado girado de 45°.")

        assert cards(user)[-4:] == [
            "S2",
            "Título: Quadrado girado",
            "O que aparece: O quadrado girado de 45°.",
            "Comentário: ",
        ]
    # Until the agent draws it, the new state shows the image of the state before it.
    assert plan(lesson)["estados"][-1] == {
        "id": "S2",
        "titulo": "Quadrado girado",
        "visivel": "O quadrado girado de 45°.",
        "cena": "T01",
    }
    assert manimflow("plan", "validate", str(lesson)).returncode == 0


async def test_a_new_state_gets_an_id_no_other_state_has(lesson):
    text = (lesson / "plano.yaml").read_text(encoding="utf-8")
    (lesson / "plano.yaml").write_text(text.replace("id: S0", "id: S2").replace("de: S0", "de: S2"), encoding="utf-8")
    async with open_lesson(lesson) as user:
        user.find("+ estado").click()

    assert [state["id"] for state in plan(lesson)["estados"]] == ["S2", "S1", "S3"]


async def test_approving_sends_one_message_with_the_plan_changes_and_every_comment(lesson):
    agent = ScriptedAgent([[AssistantText("Vou seguir o plano.")]])
    async with open_lesson(lesson, agent) as user:
        edit(user, "titulo-S1", "Quadrado na direita")
        user.find(marker="comentario-S0").type("O azul está escuro demais.")
        user.find(marker="comentar-S0").click()

        user.find(marker="approve-plan").click()

        await user.should_see("Vou seguir o plano.", retries=TURN)
        assert messages(agent) == [
            "Aprovei o plano.\n"
            "\n"
            "Mudei o plano.yaml assim:\n"
            "\n"
            "```diff\n"
            "--- plano.yaml antes\n"
            "+++ plano.yaml aprovado\n"
            "@@ -4,7 +4,7 @@\n"
            "     visivel: Um quadrado azul no centro.\n"
            "     cena: S0\n"
            "   - id: S1\n"
            "-    titulo: Quadrado deslocado\n"
            "+    titulo: Quadrado na direita\n"
            "     visivel: O mesmo quadrado, uma unidade à direita.\n"
            "     cena: T01\n"
            " \n"
            "```\n"
            "\n"
            "Comentários:\n"
            "- S0 (Quadrado): O azul está escuro demais.\n"
            "- S1 (Quadrado na direita): Talvez deslocar mais."
        ]
        # The comments went to the agent, so they leave the cards and the plan.
        assert "Talvez deslocar mais." not in cards(user)
        assert "O azul está escuro demais." not in cards(user)
    assert [state.get("comentarios") for state in plan(lesson)["estados"]] == [None, None]
    assert plan(lesson)["estados"][1]["titulo"] == "Quadrado na direita"


async def test_approving_an_untouched_plan_says_so(lesson):
    (lesson / "plano.yaml").write_text(
        (lesson / "plano.yaml").read_text(encoding="utf-8").replace("    comentarios:\n      - Talvez deslocar mais.\n", ""),
        encoding="utf-8",
    )
    agent = ScriptedAgent([[AssistantText("Vou seguir o plano.")]])
    async with open_lesson(lesson, agent) as user:
        user.find(marker="approve-plan").click()

        await user.should_see("Vou seguir o plano.", retries=TURN)
    assert messages(agent) == ["Aprovei o plano como está, sem mudanças nem comentários."]


async def test_approving_keeps_the_rest_of_the_plan_file_as_it_was(example):
    before = (example / "plano.yaml").read_text(encoding="utf-8")
    agent = ScriptedAgent([[AssistantText("Vou seguir o plano.")]])
    async with open_lesson(example, agent) as user:
        user.find(marker="comentario-S5").type("Mais devagar.")
        user.find(marker="comentar-S5").click()
        user.find(marker="approve-plan").click()

        await user.should_see("Vou seguir o plano.", retries=TURN)
    assert (example / "plano.yaml").read_text(encoding="utf-8") == before.replace(
        '    comentarios:\n      - O rótulo "Colisão" está perto da borda de cima do quadro.\n', ""
    ).replace("    comentarios:\n      - Confirmar com o grupo que os eixos oblíquos vêm antes deste diagrama.\n", "")


async def test_approving_while_the_agent_works_sends_nothing_and_keeps_the_comments(lesson):
    agent = ScriptedAgent([[AssistantText("Pronto.")]], delay=0.3)
    async with open_lesson(lesson, agent) as user:
        user.find(marker="message").type("oi")
        user.find(marker="send").click()

        user.find(marker="approve-plan").click()

        await user.should_see("Espere o agente terminar para aprovar o plano.", retries=TURN)
        await user.should_see("Pronto.", retries=TURN)
        assert messages(agent) == ["oi"]
        assert "Talvez deslocar mais." in cards(user)
    assert plan(lesson)["estados"][1]["comentarios"] == ["Talvez deslocar mais."]


TWO_STATES = """\
estados:
  - id: A
    titulo: Antes
    visivel: Um quadrado.
    cena: S0
  - id: B
    titulo: Depois
    visivel: Um quadrado deslocado.
    cena: T01
"""


async def test_the_cards_follow_a_plan_the_agent_writes(lesson):
    (lesson / "plano.yaml").unlink()
    agent = ScriptedAgent([[EditFile("plano.yaml", TWO_STATES), AssistantText("Escrevi o plano.")]])
    async with open_lesson(lesson, agent) as user:
        assert cards(user) == ["Plano", "Esta aula ainda não tem plano."]
        await user.should_not_see("Aprovar plano")

        user.find(marker="message").type("faz um plano")
        user.find(marker="send").click()

        await eventually(lambda: cards(user)[:3] == ["Plano", "A", "Título: Antes"])
        await user.should_see("Aprovar plano", retries=TURN)


async def test_an_approval_after_the_agent_rewrote_the_plan_only_reports_the_teacher_changes(lesson):
    agent = ScriptedAgent(
        [[EditFile("plano.yaml", TWO_STATES), AssistantText("Escrevi o plano.")], [AssistantText("Sigo.")]]
    )
    async with open_lesson(lesson, agent) as user:
        user.find(marker="message").type("refaz o plano")
        user.find(marker="send").click()
        await eventually(lambda: "Título: Antes" in cards(user))

        edit(user, "titulo-B", "Depois de andar")
        user.find(marker="approve-plan").click()

        await user.should_see("Sigo.", retries=TURN)
    assert messages(agent)[1] == (
        "Aprovei o plano.\n"
        "\n"
        "Mudei o plano.yaml assim:\n"
        "\n"
        "```diff\n"
        "--- plano.yaml antes\n"
        "+++ plano.yaml aprovado\n"
        "@@ -4,6 +4,6 @@\n"
        "     visivel: Um quadrado.\n"
        "     cena: S0\n"
        "   - id: B\n"
        "-    titulo: Depois\n"
        "+    titulo: Depois de andar\n"
        "     visivel: Um quadrado deslocado.\n"
        "     cena: T01\n"
        "```"
    )


async def test_typing_in_a_card_does_not_redraw_it(lesson):
    async with open_lesson(lesson) as user:
        with user:
            (field,) = user.find(marker="titulo-S0").elements

        edit(user, "titulo-S0", "Quadrado azul")
        await asyncio.sleep(3 * REFRESH_INTERVAL)

        with user:
            assert user.find(marker="titulo-S0").elements == {field}


async def test_an_invalid_plan_shows_no_cards(lesson):
    (lesson / "plano.yaml").write_text("estados: []\n", encoding="utf-8")
    async with open_lesson(lesson) as user:
        assert cards(user) == ["Plano", "O plano tem problemas. Veja os detalhes na prévia."]
        await user.should_not_see("Aprovar plano")


def render(lesson, path, content):
    """Writes a render output, as `manimflow preview` or `render` would."""
    target = lesson / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


async def test_a_rendered_state_shows_its_thumbnail_on_its_card(lesson):
    render(lesson, "saida/previa/png/T01.png", b"T01")
    async with open_lesson(lesson) as user:
        assert cards(user)[1:3] == ["S0", "Título: Quadrado"]
        assert cards(user)[6:9] == ["S1", "imagem saida/previa/png/T01.png", "Título: Quadrado deslocado"]


async def test_a_thumbnail_shows_up_when_the_state_is_rendered_without_redrawing_the_card(lesson):
    async with open_lesson(lesson) as user:
        with user:
            (field,) = user.find(marker="titulo-S0").elements

        render(lesson, "saida/previa/png/S0.png", b"S0")

        await eventually(lambda: cards(user)[1:3] == ["S0", "imagem saida/previa/png/S0.png"])
        with user:
            assert user.find(marker="titulo-S0").elements == {field}


async def test_a_deleted_plan_leaves_no_cards(lesson):
    async with open_lesson(lesson) as user:
        (lesson / "plano.yaml").unlink()

        await eventually(lambda: cards(user) == ["Plano", "Esta aula ainda não tem plano."])
        await user.should_not_see("Aprovar plano")


async def test_a_text_that_yaml_reads_as_a_number_or_yes_stays_a_text(manimflow, lesson):
    async with open_lesson(lesson) as user:
        edit(user, "titulo-S0", "1:30")
        edit(user, "visivel-S0", "yes")
        user.find(marker="comentario-S0").type("on")
        user.find(marker="comentar-S0").click()

    state = plan(lesson)["estados"][0]
    assert (state["titulo"], state["visivel"], state["comentarios"]) == ("1:30", "yes", ["on"])
    assert manimflow("plan", "validate", str(lesson)).returncode == 0


async def test_approving_a_plan_the_agent_just_rewrote_does_not_overwrite_it(lesson):
    agent = ScriptedAgent([[AssistantText("Sigo.")]])
    async with open_lesson(lesson, agent) as user:
        # The agent's new plan lands between two looks at the file.
        (lesson / "plano.yaml").write_text(TWO_STATES, encoding="utf-8")
        user.find(marker="approve-plan").click()

        await user.should_see("O plano mudou. Confira os cartões e aprove de novo.", retries=TURN)
        assert messages(agent) == []
        assert cards(user)[1:3] == ["A", "Título: Antes"]
    assert (lesson / "plano.yaml").read_text(encoding="utf-8") == TWO_STATES


async def test_an_edit_on_a_plan_the_agent_just_rewrote_is_not_written(lesson):
    async with open_lesson(lesson) as user:
        (lesson / "plano.yaml").write_text(TWO_STATES, encoding="utf-8")
        user.find(marker="comentario-S0").type("Mais azul.")
        user.find(marker="comentar-S0").click()

        assert cards(user)[1:3] == ["A", "Título: Antes"]
    assert (lesson / "plano.yaml").read_text(encoding="utf-8") == TWO_STATES


async def test_approving_again_after_the_agent_failed_resends_the_changes_and_comments(lesson):
    agent = ScriptedAgent([[AgentError("Sem conexão.")], [RuntimeError("engine crashed")], [AssistantText("Sigo.")]])
    async with open_lesson(lesson, agent) as user:
        edit(user, "titulo-S1", "Quadrado na direita")
        user.find(marker="approve-plan").click()
        await user.should_see("Erro do agente: Sem conexão.", retries=TURN)

        user.find(marker="approve-plan").click()
        await user.should_see("O agente parou por um erro inesperado.", retries=TURN)

        user.find(marker="comentario-S0").type("Mais azul.")
        user.find(marker="comentar-S0").click()
        user.find(marker="approve-plan").click()
        await user.should_see("Sigo.", retries=TURN)

    first, second, third = messages(agent)
    assert second == first
    assert first.endswith("Comentários:\n- S1 (Quadrado na direita): Talvez deslocar mais.")
    # In plan order.
    assert third == first.replace("\n- S1", "\n- S0 (Quadrado): Mais azul.\n- S1")


async def test_a_new_lesson_from_the_scaffold_shows_its_placeholder_state_and_stays_valid(manimflow, tmp_path):
    library = Library(tmp_path / "dados")
    library.set_folder(tmp_path / "Aulas Manim")
    lesson = library.create("Aula 1")
    async with open_lesson(lesson) as user:
        assert cards(user)[1:4] == [
            "S0",
            "Título: Primeiro estado",
            "O que aparece: Ainda a definir. Conte ao agente o que a aula deve mostrar.",
        ]
        # There is no plan to approve until the agent writes one.
        await user.should_not_see("Aprovar plano")
        user.find("+ estado").click()
        user.find(marker="comentario-S1").type("Começar pelos eixos.")
        user.find(marker="comentar-S1").click()

    assert [state["cena"] for state in plan(lesson)["estados"]] == ["S0_Inicio", "S0_Inicio"]
    assert manimflow("plan", "validate", str(lesson)).returncode == 0


async def test_an_edit_keeps_the_plan_file_line_endings(lesson):
    path = lesson / "plano.yaml"
    for ending in ("\r\n", "\n"):
        original = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", ending.encode())
        path.write_bytes(original)
        async with open_lesson(lesson) as user:
            edit(user, "titulo-S0", "Quadrado azul")

        assert path.read_bytes() == original.replace(b"titulo: Quadrado" + ending.encode(), b"titulo: Quadrado azul" + ending.encode())


async def test_the_comments_of_an_approval_that_failed_stay_in_the_plan(lesson):
    agent = ScriptedAgent([[AgentError("Sem conexão.")]])
    async with open_lesson(lesson, agent) as user:
        user.find(marker="approve-plan").click()
        await user.should_see("Erro do agente: Sem conexão.", retries=TURN)

        assert "Talvez deslocar mais." in cards(user)
    # So a reload, or a new launch, still has them for the next approval.
    assert plan(lesson)["estados"][1]["comentarios"] == ["Talvez deslocar mais."]


def history_of(lesson):
    """The message of every commit in the lesson's repository, newest first."""
    repo = pygit2.Repository(str(lesson / ".git"))
    return [commit.message for commit in repo.walk(repo.head.target)]


async def test_an_approval_commits_the_card_edits_apart_and_sends_the_plan_diff_only_once(lesson):
    agent = ScriptedAgent([[EditFile("CONTEXTO.md", "# Contexto\n"), AssistantText("Vou seguir o plano.")]])
    async with open_lesson(lesson, agent) as user:
        edit(user, "titulo-S1", "Quadrado na direita")
        user.find(marker="approve-plan").click()
        await user.should_see("Vou seguir o plano.", retries=TURN)

    (approval,) = agent.received
    assert "+    titulo: Quadrado na direita" in approval.text
    # The approval holds the plan diff; the manual-edit attachment would hold it again.
    assert approval.attachments == {}
    assert history_of(lesson)[:3] == [
        "Comentários do plano atendidos",
        "Pedido: Aprovei o plano",
        "Edição manual em plano.yaml",
    ]


async def test_a_message_with_card_edits_not_yet_approved_carries_no_plan_diff(lesson):
    agent = ScriptedAgent([[EditFile("CONTEXTO.md", "# Contexto\n"), AssistantText("Pronto.")]])
    async with open_lesson(lesson, agent) as user:
        user.find(marker="comentario-S0").type("Mais azul.")
        user.find(marker="comentar-S0").click()
        user.find(marker="message").type("deixe o fundo branco")
        user.find(marker="send").click()
        await user.should_see("Pronto.", retries=TURN)

    (message,) = agent.received
    assert message.attachments == {}
    assert history_of(lesson)[:2] == ["Pedido: deixe o fundo branco", "Edição manual em plano.yaml"]
