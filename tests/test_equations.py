import asyncio
import shutil
from contextlib import asynccontextmanager

from nicegui.testing.user_simulation import user_simulation

from manimflow import equations
from manimflow.agent import AssistantText
from manimflow.app import lesson_page
from manimflow.equations import Equation
from manimflow.fake_agent import EditFile, ScriptedAgent
from conftest import EXAMPLE


@asynccontextmanager
async def open_lesson(lesson, scenario=()):
    agent = ScriptedAgent(list(scenario))
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


async def eventually(check, seconds=10.0):
    """Waits for `check()` to hold, as the panel computes the equations in another process."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


def panel(user):
    """What the equations panel shows, in order: texts, and the LaTeX of each rendered formula."""
    with user:
        (column,) = user.find(marker="equations").elements
        shown = []
        for element in column.descendants():
            if isinstance(element, Equation):
                shown.append(f"fórmula {element.props['latex']}")
            elif hasattr(element, "text") and element.text:
                shown.append(element.text)
        return shown


def entries(user):
    """The panel's entries as (name, formula, value) triples, without its title."""
    shown = panel(user)[1:]
    return [tuple(shown[i : i + 3]) for i in range(0, len(shown), 3)]


async def test_the_example_shows_its_equations_in_order_with_a_decimal_comma(tmp_path):
    lesson = tmp_path / EXAMPLE.name
    shutil.copytree(EXAMPLE, lesson)
    shutil.copy(EXAMPLE.parent / "perfil.md", tmp_path)

    async with open_lesson(lesson) as user:
        await eventually(lambda: len(panel(user)) > 2)

        shown = entries(user)
        assert len(shown) == 24
        assert shown[:3] == [
            ("Velocidade do herói", "fórmula v", "= 0,6 c"),
            ("Distância até a Terra, medida na Terra", "fórmula d", "= 8 min-luz"),
            ("Fator de Lorentz", r"fórmula \gamma = \frac{1}{\sqrt{1 - v^2}}", "= 1,25"),
        ]
        assert shown[-1] == ("Chegada da Terra ao herói", r"fórmula t_H = \frac{L}{v}", "= 10,67 min")


def physics(lesson, code):
    """Writes the lesson's physics file, as the teacher or the agent would."""
    (lesson / "fisica.py").write_text(code, encoding="utf-8")


def send(user, text):
    user.find(marker="message").type(text)
    user.find("Enviar").click()


async def test_lesson_code_that_raises_shows_where_and_why_and_the_chat_keeps_working(lesson):
    physics(lesson, "def equacoes():\n    v = 0\n    return [('Razão', 'r', 1 / v, '')]\n")
    scenario = [[AssistantText("Estou aqui.")]]
    async with open_lesson(lesson, scenario) as user:
        await eventually(lambda: len(panel(user)) > 2)
        assert panel(user) == [
            "Equações",
            "Não foi possível calcular as equações.",
            "O código da aula deu erro em fisica.py, linha 3: ZeroDivisionError: division by zero",
        ]

        send(user, "oi")
        await user.should_see("Estou aqui.")


async def test_lesson_code_that_hangs_is_stopped_after_the_timeout_without_freezing_the_app(lesson, monkeypatch):
    monkeypatch.setattr(equations, "TIMEOUT", 1.5)
    physics(lesson, "def equacoes():\n    while True:\n        pass\n")
    scenario = [[AssistantText("Estou aqui.")]]
    async with open_lesson(lesson, scenario) as user:
        send(user, "oi")
        await user.should_see("Estou aqui.")
        assert panel(user) == ["Equações", "Calculando as equações…"]

        await eventually(lambda: len(panel(user)) > 2)
        assert panel(user) == [
            "Equações",
            "O cálculo das equações passou de 1,5 s e foi interrompido.",
            "Confira se o código da aula não fica preso em um laço sem fim.",
        ]


async def test_a_lesson_without_physics_says_so(lesson):
    async with open_lesson(lesson) as user:
        await eventually(lambda: len(panel(user)) > 1 and panel(user)[1] != "Calculando as equações…")
        assert panel(user) == ["Equações", "Não foi possível calcular as equações.", "Esta aula ainda não tem fisica.py."]


async def test_an_entry_that_breaks_the_contract_says_which_one(lesson):
    physics(lesson, "def equacoes():\n    return [('Velocidade', 'v', 0.6, 'c'), ('Sem unidade', 'x', 1)]\n")
    async with open_lesson(lesson) as user:
        await eventually(lambda: len(panel(user)) > 2)
        assert panel(user) == [
            "Equações",
            "Não foi possível calcular as equações.",
            "A equação 2 de equacoes() precisa ter nome, LaTeX, valor e unidade.",
        ]


async def test_values_use_a_decimal_point_unless_the_profile_asks_for_a_comma(lesson):
    physics(
        lesson,
        "def equacoes():\n"
        "    return [\n"
        "        ('Velocidade da luz', 'c', 299792458, 'm/s'),\n"
        "        ('Carga do elétron', 'e', -1.602176634e-19, 'C'),\n"
        "        ('Razão', r'\\frac{1}{3}', 1 / 3, ''),\n"
        "        ('Tempo', 't', 123456.7, 's'),\n"
        "    ]\n",
    )
    async with open_lesson(lesson) as user:
        await eventually(lambda: len(panel(user)) > 2)
        assert entries(user) == [
            ("Velocidade da luz", "fórmula c", "= 2.998 × 10⁸ m/s"),
            ("Carga do elétron", "fórmula e", "= −1.602 × 10⁻¹⁹ C"),
            ("Razão", r"fórmula \frac{1}{3}", "= 0.3333"),
            ("Tempo", "fórmula t", "= 123457 s"),
        ]

        (lesson.parent / "perfil.md").write_text("- Números com vírgula decimal, como 4,8.\n", encoding="utf-8")

        await eventually(lambda: entries(user)[0] == ("Velocidade da luz", "fórmula c", "= 2,998 × 10⁸ m/s"))
        assert entries(user)[2] == ("Razão", r"fórmula \frac{1}{3}", "= 0,3333")


async def test_the_panel_refreshes_after_an_agent_turn_and_after_a_manual_edit(lesson):
    physics(lesson, "def equacoes():\n    return [('Velocidade', 'v', 0.5, 'c')]\n")
    scenario = [
        [
            EditFile("fisica.py", "def equacoes():\n    return [('Velocidade', 'v', 0.6, 'c')]\n"),
            AssistantText("Mudei a velocidade."),
        ]
    ]
    async with open_lesson(lesson, scenario) as user:
        await eventually(lambda: entries(user) == [("Velocidade", "fórmula v", "= 0.5 c")])

        send(user, "muda a velocidade para 0,6")
        await user.should_see("Mudei a velocidade.")
        await eventually(lambda: entries(user) == [("Velocidade", "fórmula v", "= 0.6 c")])

        # What the code tab's "Renderizar" saves before it renders.
        physics(lesson, "def equacoes():\n    return [('Velocidade', 'v', 0.8, 'c'), ('Fator', r'\\gamma', 5 / 3, '')]\n")
        await eventually(
            lambda: entries(user) == [("Velocidade", "fórmula v", "= 0.8 c"), ("Fator", r"fórmula \gamma", "= 1.667")]
        )


async def test_physics_written_with_dataclasses_works(lesson):
    physics(
        lesson,
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n\n"
        "@dataclass\n"
        "class Equacao:\n"
        "    nome: str\n"
        "    latex: str\n"
        "    valor: float\n"
        "    unidade: str\n\n"
        "    def __iter__(self):\n"
        "        return iter((self.nome, self.latex, self.valor, self.unidade))\n\n"
        "def equacoes():\n"
        "    return [Equacao('Velocidade', 'v', 0.6, 'c')]\n",
    )
    async with open_lesson(lesson) as user:
        await eventually(lambda: len(panel(user)) > 2)
        assert entries(user) == [("Velocidade", "fórmula v", "= 0.6 c")]
