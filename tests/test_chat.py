from contextlib import asynccontextmanager

import pygit2
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AgentError, AssistantText, CommandFinished, CommandStarted, ImageViewed
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, Produce, ScriptedAgent


@asynccontextmanager
async def open_lesson(lesson, scenario, delay=0.0):
    agent = ScriptedAgent(scenario, delay=delay)
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find(marker="send").click()


# What closes a turn: the cards of what it produced and the saved version.
AFTER_TURN = {"checkpoint", "result-plan", "result-preview", "result-code"}


def conversation(user):
    """The text of every chat entry, in the order the page shows them, without what closes
    each turn (see `after_turn`)."""
    with user:
        (column,) = user.find(marker="conversation").elements
        return [
            element.text if isinstance(element, ui.label) else element.content
            for element in column.descendants()
            if isinstance(element, (ui.label, ui.markdown))
            and not any(AFTER_TURN & set(ancestor._markers) for ancestor in element.ancestors())
        ]


def after_turn(user):
    """The marker of each card and saved version that closes a turn, in page order."""
    with user:
        (column,) = user.find(marker="conversation").elements
        return [marker for element in column.descendants() for marker in element._markers if marker in AFTER_TURN]


def input_enabled(user):
    with user:
        (field,) = user.find(marker="message").elements
        (button,) = user.find(marker="send").elements
        return field.enabled and button.enabled


async def test_sending_a_message_streams_the_agent_events_in_order(tmp_path):
    scenario = [
        [
            AssistantText("Vou trocar a cor da luz."),
            CommandStarted("1", "manimflow preview . S2"),
            CommandFinished("1", "manimflow preview . S2", 0),
            EditFile("cenas.py", "COR_LUZ = AMARELO\n"),
            AssistantText("Pronto, a luz está amarela."),
        ]
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "muda a cor da luz")

        await user.should_see("Pronto, a luz está amarela.")
        assert conversation(user) == [
            "muda a cor da luz",
            "Vou trocar a cor da luz.",
            "Renderizando a prévia",
            "manimflow preview . S2",
            "Concluído: manimflow preview . S2",
            "Arquivo criado: cenas.py",
            "Pronto, a luz está amarela.",
        ]
        assert (tmp_path / "cenas.py").read_text(encoding="utf-8") == "COR_LUZ = AMARELO\n"


async def test_a_failed_command_shows_its_exit_code(tmp_path):
    (tmp_path / "cenas.py").write_text("", encoding="utf-8")
    scenario = [
        [
            CommandStarted("1", "manimflow render . S2"),
            EditFile("cenas.py", "x = 1\n"),
            CommandFinished("1", "manimflow render . S2", 2),
        ]
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "renderiza")

        await user.should_see("Falhou (código 2): manimflow render . S2")
        assert conversation(user) == [
            "renderiza",
            "Renderizando a versão final",
            "manimflow render . S2",
            "Arquivo alterado: cenas.py",
            "Falhou (código 2): manimflow render . S2",
        ]


def ran(command, exit_code=0):
    return [CommandStarted(command, command), CommandFinished(command, command, exit_code)]


async def test_each_self_check_step_shows_in_the_chat(tmp_path):
    scenario = [
        [
            EditFile("cenas.py", "x = 1\n"),
            *ran("manimflow plan validate ."),
            *ran("python -m pytest -q -p no:cacheprovider test_fisica.py"),
            *ran("manimflow preview . S1_EixosHeroi --json"),
            *ran("manimflow frames . S0-S1"),
            *ran("manimflow check-continuity . S0-S1", exit_code=1),
            ImageViewed("saida/previa/quadros/S0-S1_fim.png"),
            *ran("ls saida"),
            AssistantText("A transição S0-S1 termina fora do lugar. Vou corrigir."),
        ]
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "fecha os eixos do herói")

        await user.should_see("A transição S0-S1 termina fora do lugar. Vou corrigir.")
        assert conversation(user) == [
            "fecha os eixos do herói",
            "Arquivo criado: cenas.py",
            "Validando o plano",
            "manimflow plan validate .",
            "Concluído: manimflow plan validate .",
            "Rodando os testes de física",
            "python -m pytest -q -p no:cacheprovider test_fisica.py",
            "Concluído: python -m pytest -q -p no:cacheprovider test_fisica.py",
            "Renderizando a prévia",
            "manimflow preview . S1_EixosHeroi --json",
            "Concluído: manimflow preview . S1_EixosHeroi --json",
            "Extraindo os quadros",
            "manimflow frames . S0-S1",
            "Concluído: manimflow frames . S0-S1",
            "Conferindo a continuidade",
            "manimflow check-continuity . S0-S1",
            "Falhou (código 1): manimflow check-continuity . S0-S1",
            "Olhou a imagem S0-S1_fim.png",
            "ls saida",
            "Concluído: ls saida",
            "A transição S0-S1 termina fora do lugar. Vou corrigir.",
        ]


async def test_input_is_disabled_while_the_turn_runs(tmp_path):
    scenario = [[AssistantText("Começando."), AssistantText("Terminei.")]]
    async with open_lesson(tmp_path, scenario, delay=0.5) as user:
        assert input_enabled(user)
        send(user, "faz a animação")

        await user.should_see("Começando.", retries=20)
        assert not input_enabled(user)
        await user.should_see(marker="progress")

        await user.should_see("Terminei.", retries=20)
        assert input_enabled(user)
        await user.should_not_see(marker="progress")


async def test_an_agent_error_is_shown_in_portuguese_and_the_chat_recovers(tmp_path):
    scenario = [
        [AssistantText("Vou renderizar."), AgentError("O limite do plano foi atingido.")],
        [AssistantText("Voltei.")],
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "renderiza")
        await user.should_see("Erro do agente: O limite do plano foi atingido.")
        assert input_enabled(user)

        send(user, "tenta de novo")
        await user.should_see("Voltei.")


async def test_a_crash_in_the_agent_is_shown_as_an_error_in_portuguese(tmp_path):
    scenario = [[AssistantText("Vou renderizar."), ConnectionError("app-server exited")]]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "renderiza")

        await user.should_see("O agente parou por um erro inesperado.")
        await user.should_not_see("app-server exited")
        assert input_enabled(user)


async def test_an_empty_message_is_not_sent(tmp_path):
    async with open_lesson(tmp_path, [[AssistantText("Oi.")]]) as user:
        send(user, "   ")

        await user.should_not_see("Oi.")
        assert conversation(user) == []


PLAN = """estados:
  - id: S0
    titulo: Partida
    visivel: As duas linhas de mundo na Terra.
    cena: S0
  - id: S1
    titulo: Ida
    visivel: A irmã até a estrela.
    cena: T01
transicoes:
  - de: S0
    para: S1
    descricao: A irmã viaja.
    duracao: 4
    cena: T01
"""

SCENES = """from manim import Scene


class S0(Scene):
    def construct(self):
        pass


class T01(Scene):
    def construct(self):
        pass
"""


def texts_in(user, marker):
    with user:
        return [
            element.text
            for found in user.find(marker=marker).elements
            for element in found.descendants()
            if isinstance(element, ui.label)
        ]


async def test_a_turn_that_writes_the_plan_shows_it_inline_and_saves_a_version(tmp_path):
    scenario = [[EditFile("cenas.py", SCENES), EditFile("plano.yaml", PLAN), AssistantText("Montei o plano.")]]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "aula sobre os gêmeos")
        await user.should_see("Montei o plano.")
        await user.should_see(marker="checkpoint")

        assert after_turn(user) == ["result-plan", "result-code", "checkpoint"]
        assert texts_in(user, "result-plan") == [
            "Plano · 2 estados, 1 transição",
            "S0",
            "Partida",
            "As duas linhas de mundo na Terra.",
            "↓ 4 s",
            "S1",
            "Ida",
            "A irmã até a estrela.",
        ]


async def test_a_turn_that_renders_shows_the_new_previews(tmp_path):
    (tmp_path / "plano.yaml").write_text(PLAN, encoding="utf-8")
    (tmp_path / "cenas.py").write_text(SCENES, encoding="utf-8")
    scenario = [
        [
            CommandStarted("1", "manimflow preview . S0"),
            Produce("saida/previa/png/S0.png", b"S0"),
            CommandFinished("1", "manimflow preview . S0", 0),
            AssistantText("Renderizei."),
        ]
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "renderiza")
        await user.should_see(marker="result-preview")

        # Renders aren't versioned, so the turn changed no versioned file.
        assert after_turn(user) == ["result-preview"]
        assert texts_in(user, "result-preview") == ["Prévia atualizada", "Abrir →"]


async def test_a_turn_that_changes_nothing_saves_no_version(tmp_path):
    async with open_lesson(tmp_path, [[AssistantText("Nada a mudar.")]]) as user:
        send(user, "está bom?")
        await user.should_see("Nada a mudar.")
        await user.should_not_see(marker="checkpoint")


async def test_restaurar_brings_the_files_back_to_that_version_as_a_new_one(tmp_path):
    scenario = [
        [EditFile("cenas.py", "# primeira\n"), AssistantText("Primeira.")],
        [EditFile("cenas.py", "# segunda\n"), EditFile("extra.py", "x = 1\n"), AssistantText("Segunda.")],
    ]
    async with open_lesson(tmp_path, scenario) as user:
        send(user, "faz a primeira")
        await user.should_see("Primeira.")
        await user.should_see(marker="checkpoint")
        send(user, "faz a segunda")
        await user.should_see("Segunda.")

        user.find(marker="restore").click()
        user.find(marker="confirm-restore").click()

        await user.should_see("A aula voltou para a versão", retries=50)
    assert (tmp_path / "cenas.py").read_text(encoding="utf-8") == "# primeira\n"
    assert not (tmp_path / "extra.py").exists()
    repo = pygit2.Repository(str(tmp_path / ".git"))
    assert repo[repo.head.target].message.startswith("Voltei para a versão de ")


async def test_enter_sends_the_message(tmp_path):
    async with open_lesson(tmp_path, [[AssistantText("Recebi.")]]) as user:
        user.find(marker="message").type("oi").trigger("keydown.enter.exact.prevent")
        await user.should_see("Recebi.")


async def test_the_preview_closes_so_the_chat_takes_the_page_and_a_card_opens_it_on_its_tab(tmp_path):
    scenario = [[EditFile("cenas.py", SCENES), EditFile("plano.yaml", PLAN), AssistantText("Montei o plano.")]]
    async with open_lesson(tmp_path, scenario) as user:
        user.find(marker="close-workspace").click()
        await user.should_see(marker="show-workspace")

        send(user, "aula sobre os gêmeos")
        await user.should_see(marker="result-plan")
        user.find(marker="result-plan").click()

        await user.should_not_see(marker="show-workspace")
        with user:
            (tabs,) = user.find(marker="workspace-tabs").elements
            assert tabs.value == "Plano"
