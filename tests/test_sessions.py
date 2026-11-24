"""Session history: every opening of a lesson starts a new conversation, and the old ones stay readable."""

from contextlib import asynccontextmanager
from datetime import datetime

from nicegui import ElementFilter, ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.agent import AssistantText, CommandFinished, CommandStarted
from manimflow.app import lesson_page
from manimflow.fake_agent import ScriptedAgent

MORNING = datetime(2026, 10, 27, 9, 5)
AFTERNOON = datetime(2026, 10, 27, 14, 30)


@asynccontextmanager
async def lesson_screen(agent, lesson):
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find(marker="send").click()


def texts(user, marker):
    """The text of every label and markdown inside the element marked `marker`, in page order."""
    with user:
        (column,) = user.find(marker=marker).elements
        return [
            element.text if isinstance(element, ui.label) else element.content
            for element in column.descendants()
            if isinstance(element, (ui.label, ui.markdown))
        ]


async def past_sessions(user):
    """What the past-sessions list shows: the texts of each session's entry, in order."""
    user.find("Anteriores").click()
    await user.should_see(marker="past-sessions")
    with user:
        return [
            [element.text for element in entry.descendants() if isinstance(element, ui.label)]
            for entry in ElementFilter(marker="past-session")
        ]


async def test_reopening_a_lesson_starts_a_fresh_conversation_and_lists_the_old_one(tmp_path):
    agent = ScriptedAgent([[AssistantText("A luz agora é amarela.")]], clock=iter([MORNING, AFTERNOON]).__next__)
    async with lesson_screen(agent, tmp_path) as user:
        await user.open("/")
        send(user, "muda a cor da luz para amarelo")
        await user.should_see("A luz agora é amarela.")

        await user.open("/")

        assert texts(user, "conversation") == []
        assert await past_sessions(user) == [["27/10/2026 09:05", "muda a cor da luz para amarelo"]]


async def test_past_sessions_are_listed_newest_first_without_the_current_one(tmp_path):
    clock = iter([MORNING, AFTERNOON, datetime(2026, 10, 28, 8, 0)]).__next__
    agent = ScriptedAgent([[AssistantText("Feito.")]], clock=clock)
    async with lesson_screen(agent, tmp_path) as user:
        for request in ["desenha o espelho", "aumenta a fonte"]:
            await user.open("/")
            send(user, request)
            await user.should_see("Feito.")

        await user.open("/")
        send(user, "troca o fundo")
        await user.should_see("Feito.")

        assert await past_sessions(user) == [
            ["27/10/2026 14:30", "aumenta a fonte"],
            ["27/10/2026 09:05", "desenha o espelho"],
        ]


async def test_opening_a_lesson_without_sending_anything_leaves_no_past_session(tmp_path):
    agent = ScriptedAgent([])
    async with lesson_screen(agent, tmp_path) as user:
        await user.open("/")
        await user.open("/")

        assert await past_sessions(user) == []
        await user.should_see("Esta aula ainda não tem conversas anteriores.")


async def test_a_past_session_shows_its_messages_read_only(tmp_path):
    scenario = [
        [
            AssistantText("Vou desenhar o espelho."),
            CommandStarted("1", "manimflow preview . S1"),
            CommandFinished("1", "manimflow preview . S1", 0),
            AssistantText("Pronto, o espelho está **à direita**."),
        ],
        [AssistantText("Deixei a fonte maior.")],
    ]
    agent = ScriptedAgent(scenario, clock=iter([MORNING, AFTERNOON]).__next__)
    async with lesson_screen(agent, tmp_path) as user:
        await user.open("/")
        send(user, "desenha o espelho")
        await user.should_see("Pronto, o espelho está **à direita**.")
        send(user, "aumenta a fonte")
        await user.should_see("Deixei a fonte maior.")

        await user.open("/")
        await past_sessions(user)
        user.find(marker="past-session").click()

        await user.should_see(marker="past-messages")
        assert texts(user, "past-messages") == [
            "desenha o espelho",
            "Vou desenhar o espelho.",
            "Pronto, o espelho está **à direita**.",
            "aumenta a fonte",
            "Deixei a fonte maior.",
        ]
        with user:
            (shown,) = user.find(marker="past-messages").elements
            (dialog,) = [ancestor for ancestor in shown.ancestors() if isinstance(ancestor, ui.dialog)]
            assert not [element for element in dialog.descendants() if isinstance(element, (ui.input, ui.textarea))]
        # The new session's chat is still empty: reading an old session doesn't resume it.
        assert texts(user, "conversation") == []


async def test_sessions_belong_to_their_lesson(tmp_path):
    optics, waves = tmp_path / "Óptica", tmp_path / "Ondas"
    optics.mkdir()
    waves.mkdir()
    agent = ScriptedAgent([[AssistantText("Feito.")]], clock=iter([MORNING, AFTERNOON, AFTERNOON]).__next__)
    async with lesson_screen(agent, optics) as user:
        await user.open("/")
        send(user, "desenha o espelho")
        await user.should_see("Feito.")

    async with lesson_screen(agent, waves) as user:
        await user.open("/")
        send(user, "desenha a onda")
        await user.should_see("Feito.")
        await user.open("/")

        assert await past_sessions(user) == [["27/10/2026 14:30", "desenha a onda"]]


async def test_a_past_session_shows_the_teachers_words_without_the_manual_edits(tmp_path):
    (tmp_path / "fisica.py").write_text("g = 9.8\n", encoding="utf-8")
    agent = ScriptedAgent([[AssistantText("Usei o seu g.")]])
    async with lesson_screen(agent, tmp_path) as user:
        await user.open("/")
        (tmp_path / "fisica.py").write_text("g = 9.81\n", encoding="utf-8")
        send(user, "use o meu g")
        await user.should_see("Usei o seu g.", retries=100)
        assert agent.received[0].attachments

        await user.open("/")
        (entry,) = await past_sessions(user)
        assert entry[1] == "use o meu g"

        user.find(marker="past-session").click()
        await user.should_see(marker="past-messages")
        assert texts(user, "past-messages") == ["use o meu g", "Usei o seu g."]
