import asyncio
import os
from contextlib import asynccontextmanager

from nicegui import ui
from nicegui.testing.user_simulation import user_simulation
from PIL import Image

from manimflow.agent import AssistantText, CommandFinished, CommandStarted
from manimflow.app import lesson_page
from manimflow.fake_agent import Produce, ScriptedAgent


@asynccontextmanager
async def open_lesson(lesson, scenario=(), agent=None):
    agent = agent or ScriptedAgent(list(scenario))
    async with user_simulation(root=lesson_page(agent, lesson)) as user:
        await user.open("/")
        yield user


def send(user, text):
    user.find(marker="message").type(text)
    user.find(marker="send").click()


async def eventually(check, seconds=3.0):
    """Waits for `check()` to hold, as the panel refreshes on its own schedule."""
    for _ in range(int(seconds / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


MEDIA = (ui.image, ui.interactive_image, ui.video)


def _texts(container):
    """The visible labels, images and videos inside `container`, in page order."""
    shown = []
    for element in container.descendants():
        if not all(each.visible for each in (element, *element.ancestors())):
            continue
        if isinstance(element, ui.label) and element.text:
            shown.append(element.text)
        elif isinstance(element, MEDIA):
            kind = "vídeo" if isinstance(element, ui.video) else "imagem"
            shown.append(f"{kind} {_lesson_file(element.source)}")
    return shown


def _one(user, marker):
    (element,) = user.find(marker=marker).elements
    return element


def filmstrip(user):
    """What each state and transition under the stage shows, in plan order."""
    with user:
        return [_texts(frame) for frame in _one(user, "filmstrip").default_slot.children]


def stage(user):
    """The stage's caption, then what it shows: the image, the video or the placeholder."""
    with user:
        return _texts(_one(user, "stage-caption")) + _texts(_one(user, "stage"))


def panel(user):
    """Everything the panel shows, for a lesson whose plan can't be drawn."""
    with user:
        return _texts(_one(user, "preview"))


def select(user, id):
    user.find(marker=f"frame-{id}").click()


def sources(user, marker="preview"):
    """The URL of every image and video in the preview panel, or in its part marked `marker`."""
    with user:
        return [element.source for element in _one(user, marker).descendants() if isinstance(element, MEDIA)]


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
        assert filmstrip(user) == [
            ["Ainda não renderizado", "S0", "Quadrado"],
            ["·", "0,5 s"],
            ["Ainda não renderizado", "S1", "Quadrado deslocado"],
        ]
        assert stage(user) == ["S0 · Quadrado", "Ainda não renderizado"]


async def test_a_lesson_without_a_plan_says_so(tmp_path):
    async with open_lesson(tmp_path) as user:
        assert panel(user) == ["Esta aula ainda não tem plano."]


async def test_an_invalid_plan_shows_its_errors(lesson):
    (lesson / "plano.yaml").write_text("estados: []\n", encoding="utf-8")
    async with open_lesson(lesson) as user:
        assert panel(user) == [
            "O plano tem problemas, então a prévia não pode ser montada:",
            'A lista "estados" precisa ter pelo menos um item.',
        ]


async def test_each_state_shows_its_latest_image_and_each_transition_its_video(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 previa")
    render(lesson, "saida/previa/png/T01.png", b"T01 previa", age=60)
    render(lesson, "saida/png/T01.png", b"T01 final")
    render(lesson, "saida/previa/mp4/T01.mp4", b"T01 video previa")
    async with open_lesson(lesson) as user:
        assert filmstrip(user) == [
            ["imagem saida/previa/png/S0.png", "S0", "Quadrado"],
            ["▶", "0,5 s"],
            ["imagem saida/png/T01.png", "S1", "Quadrado deslocado"],
        ]
        assert stage(user) == ["S0 · Quadrado", "imagem saida/previa/png/S0.png"]

        select(user, "S0 → S1")
        await eventually(
            lambda: stage(user) == ["S0 → S1 · O quadrado anda para a direita.", "vídeo saida/previa/mp4/T01.mp4"]
        )
        served = [(await user.http_client.get(url)).content for url in sources(user, "filmstrip") + sources(user, "stage")]
        assert served == [b"S0 previa", b"T01 final", b"T01 video previa"]


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
            lambda: filmstrip(user)
            == [
                ["imagem saida/previa/png/S0.png", "S0", "Quadrado"],
                ["▶", "0,5 s"],
                ["imagem saida/previa/png/T01.png", "S1", "Quadrado deslocado"],
            ]
        )
        await eventually(lambda: stage(user) == ["S0 · Quadrado", "imagem saida/previa/png/S0.png"])


async def test_a_render_from_outside_the_chat_replaces_the_old_image(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 antes", age=60)
    async with open_lesson(lesson) as user:
        before = sources(user)

        render(lesson, "saida/previa/png/S0.png", b"S0 depois")

        await eventually(lambda: sources(user) != before)
        for url in sources(user):
            assert (await user.http_client.get(url)).content == b"S0 depois"


async def test_a_new_image_does_not_restart_a_video_the_teacher_is_watching(lesson):
    render(lesson, "saida/previa/png/S0.png", b"S0 antes", age=60)
    render(lesson, "saida/previa/mp4/T01.mp4", b"T01 video")
    async with open_lesson(lesson) as user:
        select(user, "S0 → S1")
        await eventually(lambda: "vídeo saida/previa/mp4/T01.mp4" in stage(user))
        with user:
            (video,) = user.find(ui.video).elements

        render(lesson, "saida/previa/png/S0.png", b"S0 depois")

        new_image = f"?v={(lesson / 'saida/previa/png/S0.png').stat().st_mtime_ns}"
        await eventually(lambda: sources(user, "filmstrip")[0].endswith(new_image))
        with user:
            assert user.find(ui.video).elements == {video}


def frame(lesson, path, size=(320, 180)):
    """Writes a real image as a render, so a pin can be drawn on it."""
    target = lesson / path
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "black").save(target)


async def test_a_comment_pinned_on_the_image_goes_with_the_next_message_and_turns_done(lesson):
    frame(lesson, "saida/previa/png/S0.png")
    agent = ScriptedAgent([[AssistantText("Aumentei o quadrado.")]])
    async with open_lesson(lesson, agent=agent) as user:
        user.find(marker="pin-mode").click()
        user.find(ui.interactive_image).trigger("mouse", {"mouse_event_type": "click", "image_x": 80, "image_y": 45})
        user.find(marker="pin-text").type("Deixe este quadrado maior")
        user.find(marker="save-pin").click()
        await user.should_see(marker="pin-chip", content="📍 1 · S0: Deixe este quadrado maior")

        send(user, "pode ajustar?")
        await user.should_see("Aumentei o quadrado.")
        await user.should_not_see(marker="pin-chip")

    (received,) = agent.received
    assert received.text == "pode ajustar?"
    assert received.attachments["comentarios-na-imagem.md"] == (
        "# Comentários na imagem\n\n"
        "1. Estado S0 (Quadrado), em x = 0,25 e y = 0,25 do quadro: Deixe este quadrado maior\n"
        "   Imagem com o marcador: .manimflow/comentarios/1-S0.png\n"
    )
    with Image.open(lesson / ".manimflow" / "comentarios" / "1-S0.png") as marked:
        # The pin is drawn where the teacher clicked.
        assert marked.getpixel((80, 45)) != (0, 0, 0)
        assert marked.getpixel((300, 170)) == (0, 0, 0)
