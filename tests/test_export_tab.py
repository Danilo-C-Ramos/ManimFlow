from contextlib import asynccontextmanager

import av
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation
from PIL import Image

from manimflow import export_tab
from manimflow.app import lesson_page
from manimflow.fake_agent import ScriptedAgent


@asynccontextmanager
async def open_export_tab(lesson):
    async with user_simulation(root=lesson_page(ScriptedAgent([]), lesson)) as user:
        await user.open("/")
        user.find(kind=ui.tab, content="Exportar").click()
        yield user


def fields(user):
    """The export settings as the tab shows them."""
    with user:
        return {
            name: user.find(marker=name).elements.pop().value
            for name in ("resolution", "fps", "aspect-ratio", "background")
        }


def choose(user, preset):
    user.find(preset).click()


async def test_offers_the_four_presets_with_their_defaults(lesson):
    async with open_export_tab(lesson) as user:
        with user:
            (presets,) = user.find(marker="preset").elements
        assert list(presets.options.values()) == [
            "PowerPoint",
            "PowerPoint web / Google Slides",
            "Beamer / PDF",
            "Vídeo da aula inteira",
        ]
        await user.should_see("Uma imagem PNG por estado e um vídeo MP4 por transição")
        assert fields(user) == {"resolution": 1080, "fps": 60, "aspect-ratio": "16:9", "background": ""}

        choose(user, "PowerPoint web / Google Slides")

        await user.should_see("Um GIF por transição e um GIF parado por estado")
        assert fields(user) == {"resolution": 720, "fps": 25, "aspect-ratio": "16:9", "background": ""}


def set_field(user, name, value):
    """Types into a field, or picks a value where there is nothing to type into."""
    with user:
        (field,) = user.find(marker=name).elements
    if isinstance(field, (ui.number, ui.input)):
        user.find(marker=name).clear().type(str(value))
    else:
        field.value = value


def exported(user):
    """The files the tab lists after an export, in order."""
    with user:
        (listing,) = user.find(marker="exported-files").elements
        return [element.text for element in listing.descendants() if isinstance(element, ui.label)]


async def test_runs_the_cli_with_the_chosen_preset_and_settings_and_lists_the_files(lesson):
    async with open_export_tab(lesson) as user:
        choose(user, "PowerPoint")
        set_field(user, "resolution", 144)
        set_field(user, "fps", 10)
        set_field(user, "aspect-ratio", "4:3")
        set_field(user, "background", "#ffcc00")

        user.find(marker="run-export").click()

        await user.should_see("Exportando…")
        await user.should_see("Arquivos exportados", retries=600)
        assert exported(user) == ["01_S0.png", "02_S0-S1.mp4", "03_S1.png"]

    folder = lesson / "saida" / "powerpoint"
    for name in ("01_S0.png", "03_S1.png"):
        with Image.open(folder / name) as image:
            # 4:3 at 144 pixels high, on the chosen background.
            assert image.size == (192, 144), name
            assert image.convert("RGB").getpixel((2, 2)) == (255, 204, 0), name
    with av.open(str(folder / "02_S0-S1.mp4")) as video:
        # The fixture transition lasts 0.5 s, at 10 frames per second.
        assert len(list(video.decode(video=0))) == 5


async def test_a_scene_that_fails_is_reported_in_portuguese_and_the_tab_recovers(lesson):
    scenes = lesson / "cenas.py"
    scenes.write_text(scenes.read_text(encoding="utf-8") + "\nraise ValueError('quebrada')\n", encoding="utf-8")

    async with open_export_tab(lesson) as user:
        choose(user, "Beamer / PDF")
        user.find(marker="run-export").click()

        await user.should_see("A exportação falhou", retries=600)
        await user.should_see("Uma cena deu erro ao renderizar. Peça ao agente para corrigir.")
        await user.should_see("quebrada")
        await user.should_not_see("Arquivos exportados")
        with user:
            assert user.find(marker="run-export").elements.pop().enabled

    assert not (lesson / "saida" / "beamer").exists()


async def test_plan_problems_are_listed(lesson):
    (lesson / "plano.yaml").write_text("estados: []\ntransicoes: []\n", encoding="utf-8")

    async with open_export_tab(lesson) as user:
        user.find(marker="run-export").click()

        await user.should_see("A exportação falhou", retries=600)
        await user.should_see('A lista "estados" precisa ter pelo menos um item.')


async def test_settings_out_of_range_are_explained_and_block_the_export(lesson):
    async with open_export_tab(lesson) as user:
        choose(user, "PowerPoint web / Google Slides")
        set_field(user, "fps", 60)
        set_field(user, "resolution", 1081)
        set_field(user, "background", "azul-piscina")

        await user.should_see("Os GIFs tocam no máximo 50 quadros por segundo.")
        await user.should_see("A resolução precisa ser um número par de 16 a 1440.")
        await user.should_see("Use uma cor como #ffffff ou white, ou deixe vazio.")
        user.find(marker="run-export").click()

        set_field(user, "fps", 25)
        set_field(user, "resolution", 720)
        set_field(user, "background", "")
        await user.should_not_see("quadros por segundo.")
        await user.should_not_see("A resolução precisa")
        await user.should_not_see("Use uma cor")
        with user:
            assert user.find(marker="run-export").elements.pop().enabled

    assert not (lesson / "saida").exists()


async def test_a_button_opens_the_folder_of_the_exported_files(lesson, monkeypatch):
    opened = []
    monkeypatch.setattr(export_tab, "open_in_file_manager", opened.append)

    async with open_export_tab(lesson) as user:
        choose(user, "Beamer / PDF")
        set_field(user, "resolution", 144)
        user.find(marker="run-export").click()
        await user.should_see("Arquivos exportados", retries=600)

        user.find("Abrir pasta").click()

    assert opened == [lesson / "saida" / "beamer"]
