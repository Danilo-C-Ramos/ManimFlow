import asyncio
import os
from contextlib import asynccontextmanager

from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.app import lesson_page
from manimflow.agent import AssistantText, CommandFinished, CommandStarted
from manimflow.fake_agent import Produce, ScriptedAgent


@asynccontextmanager
async def open_lesson(lesson, scenario=()):
    agent = ScriptedAgent(list(scenario))
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find("Enviar").click()


async def eventually(check, seconds=3.0):
    """Waits for `check()` to hold, as the panel refreshes on its own schedule."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


def panel(user):
    """What the preview panel shows, in order: texts, and the lesson file behind each image and video."""
    with user:
        (column,) = user.find(marker="preview").elements
        shown = []
        for element in column.descendants():
            if isinstance(element, ui.label):
                shown.append(element.text)
            elif isinstance(element, (ui.image, ui.video)):
                kind = "imagem" if isinstance(element, ui.image) else "vídeo"
                shown.append(f"{kind} {_lesson_file(element.source)}")
        return shown


def sources(user):
    """The URL of every image and video in the preview panel."""
    with user:
        (column,) = user.find(marker="preview").elements
        return [element.source for element in column.descendants() if isinstance(element, (ui.image, ui.video))]


def render(lesson, path, content, age=0):
    """Writes a render output, as `manimflow preview` or `render` would; `age` makes it older, in seconds."""
    target = lesson / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    if age:
        stat = target.stat()
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns - age * 10**9))


def _lesson_file(url):
    path = url.split("?")[0]
    return path[path.index("/saida/") + 1 :]


async def test_a_lesson_without_renders_shows_its_states_in_plan_order_with_placeholders(lesson):
    async with open_lesson(lesson) as user:
        assert panel(user) == [
            "Prévia",
            "S0 · Quadrado",
            "Ainda não renderizado",
            "S0 → S1",
            "Ainda não renderizado",
            "S1 · Quadrado deslocado",
            "Ainda não renderizado",
        ]


async def test_a_lesson_without_a_plan_says_so(tmp_path):
    async with open_lesson(tmp_path) as user:
        assert panel(user) == ["Prévia", "Esta aula ainda não tem plano."]


async def test_an_invalid_plan_shows_its_errors(lesson):
    (lesson / "plano.yaml").write_text("estados: []\n", encoding="utf-8")
    async with open_lesson(lesson) as user:
        assert panel(user) == [
            "Prévia",
            "O plano tem problemas, então a prévia não pode ser montada:",
            'A lista "estados" precisa ter pelo menos um item.',
        ]


async def test_each_state_shows_its_latest_image_and_each_transition_its_video(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 previa")
    render(lesson, "saida/previa/png/T01.png", b"T01 previa", age=60)
    render(lesson, "saida/png/T01.png", b"T01 final")
    render(lesson, "saida/previa/mp4/T01.mp4", b"T01 video previa")
    async with open_lesson(lesson) as user:
        assert panel(user) == [
            "Prévia",
            "S0 · Quadrado",
            "imagem saida/previa/png/S0.png",
            "S0 → S1",
            "vídeo saida/previa/mp4/T01.mp4",
            "S1 · Quadrado deslocado",
            "imagem saida/png/T01.png",
        ]
        served = [(await user.http_client.get(url)).content for url in sources(user)]
        assert served == [b"S0 previa", b"T01 video previa", b"T01 final"]


async def test_the_panel_shows_what_the_agent_renders_without_a_page_reload(lesson):
    scenario = [
        [
            CommandStarted("1", "manimflow preview . S0"),
            Produce("saida/previa/png/S0.png", b"S0"),
            CommandFinished("1", "manimflow preview . S0", 0),
            CommandStarted("2", "manimflow preview . T01"),
            Produce("saida/previa/png/T01.png", b"T01"),
            Produce("saida/previa/mp4/T01.mp4", b"T01 video"),
            CommandFinished("2", "manimflow preview . T01", 0),
            AssistantText("Renderizei as prévias."),
        ]
    ]
    async with open_lesson(lesson, scenario) as user:
        send(user, "renderiza tudo")
        await user.should_see("Renderizei as prévias.")

        await eventually(
            lambda: panel(user)
            == [
                "Prévia",
                "S0 · Quadrado",
                "imagem saida/previa/png/S0.png",
                "S0 → S1",
                "vídeo saida/previa/mp4/T01.mp4",
                "S1 · Quadrado deslocado",
                "imagem saida/previa/png/T01.png",
            ]
        )


async def test_a_render_from_outside_the_chat_replaces_the_old_image(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 antes", age=60)
    async with open_lesson(lesson) as user:
        (before,) = sources(user)

        render(lesson, "saida/previa/png/S0.png", b"S0 depois")

        await eventually(lambda: sources(user) != [before])
        (after,) = sources(user)
        assert (await user.http_client.get(after)).content == b"S0 depois"


async def test_a_new_image_does_not_restart_a_video_the_teacher_is_watching(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 antes", age=60)
    render(lesson, "saida/previa/mp4/T01.mp4", b"T01 video")
    async with open_lesson(lesson) as user:
        with user:
            (video,) = user.find(ui.video).elements

        render(lesson, "saida/previa/png/S0.png", b"S0 depois")

        new_image = f"?v={(lesson / 'saida/previa/png/S0.png').stat().st_mtime_ns}"
        await eventually(lambda: sources(user)[0].endswith(new_image))
        with user:
            assert user.find(ui.video).elements == {video}
