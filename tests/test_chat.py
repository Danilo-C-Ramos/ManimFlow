from contextlib import asynccontextmanager

from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AgentError, AssistantText, CommandFinished, CommandStarted
from manimflow.app import lesson_page
from manimflow.fake_agent import EditFile, ScriptedAgent


@asynccontextmanager
async def open_lesson(lesson, scenario, delay=0.0):
    agent = ScriptedAgent(scenario, delay=delay)
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="mensagem").type(text)
    user.find("Enviar").click()


def conversation(user):
    """The text of every chat entry, in the order the page shows them."""
    with user:
        (column,) = user.find(marker="conversa").elements
        return [
            element.text if isinstance(element, ui.label) else element.content
            for element in column.descendants()
            if isinstance(element, (ui.label, ui.markdown))
        ]


def input_enabled(user):
    with user:
        (field,) = user.find(marker="mensagem").elements
        (button,) = user.find("Enviar").elements
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
            "manimflow preview . S2",
            "concluído",
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

        await user.should_see("falhou (código 2)")
        assert conversation(user) == [
            "renderiza",
            "manimflow render . S2",
            "falhou (código 2)",
            "Arquivo alterado: cenas.py",
        ]


async def test_input_is_disabled_while_the_turn_runs(tmp_path):
    scenario = [[AssistantText("Começando."), AssistantText("Terminei.")]]
    async with open_lesson(tmp_path, scenario, delay=0.5) as user:
        assert input_enabled(user)
        send(user, "faz a animação")

        await user.should_see("Começando.", retries=20)
        assert not input_enabled(user)
        await user.should_see("O agente está trabalhando…")

        await user.should_see("Terminei.", retries=20)
        assert input_enabled(user)
        await user.should_not_see("O agente está trabalhando…")


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

        await user.should_see("O agente parou por um erro inesperado: app-server exited")
        assert input_enabled(user)


async def test_an_empty_message_is_not_sent(tmp_path):
    async with open_lesson(tmp_path, [[AssistantText("Oi.")]]) as user:
        send(user, "   ")

        await user.should_not_see("Oi.")
        assert conversation(user) == []
