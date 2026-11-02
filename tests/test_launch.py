from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.cli import main
from conftest import EXAMPLE


def launch(monkeypatch, tmp_path, *args):
    """Runs `manimflow` without starting a server and returns what it passed to ui.run.

    ManimFlow's own folder is `tmp_path / "dados" / "ManimFlow"`.
    """
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "dados"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados"))
    with monkeypatch.context() as patch:
        patch.setattr(ui, "run", lambda root, **options: calls.append((root, options)))
        assert main(list(args)) == 0
    (call,) = calls
    return call


def test_serves_only_on_localhost_and_opens_the_browser(monkeypatch, tmp_path):
    _, options = launch(monkeypatch, tmp_path)

    assert options["host"] == "127.0.0.1"
    assert options["show"] is True
    assert isinstance(options["port"], int)


async def test_the_app_opens_on_the_home(monkeypatch, tmp_path):
    root, _ = launch(monkeypatch, tmp_path)

    async with user_simulation(root=root) as user:
        await user.open("/")
        await user.should_see("Minhas aulas")


async def test_the_app_runs_codex_in_its_own_home_and_asks_to_sign_in(monkeypatch, tmp_path):
    root, _ = launch(monkeypatch, tmp_path)

    async with user_simulation(root=root) as user:
        await user.open("/exemplo")
        await user.should_see("Entrar com o ChatGPT")

    assert (tmp_path / "dados" / "ManimFlow" / "codex").is_dir()


async def test_the_example_opens_from_manimflows_folder_and_keeps_the_teachers_changes(monkeypatch, tmp_path):
    # Codex's Windows sandbox never lets the agent into the temp folder.
    example = tmp_path / "dados" / "ManimFlow" / "exemplo" / "Relatividade - herói e espelho"
    launch(monkeypatch, tmp_path, "--demo")
    assert sorted(path.name for path in example.iterdir()) == sorted(path.name for path in EXAMPLE.iterdir())
    (example / "rascunho.md").write_text("da última vez", encoding="utf-8")

    launch(monkeypatch, tmp_path, "--demo")

    assert (example / "rascunho.md").read_text(encoding="utf-8") == "da última vez"


async def test_demo_opens_a_copy_of_the_bundled_example_with_the_scripted_agent(monkeypatch, tmp_path):
    bundled = sorted(path.name for path in EXAMPLE.iterdir())
    root, _ = launch(monkeypatch, tmp_path, "--demo")

    async with user_simulation(root=root) as user:
        await user.open("/")
        user.find("Abrir o exemplo").click()
        await user.should_see(marker="message")
        await user.should_see("Relatividade - herói e espelho")

        user.find(marker="message").type("muda a cor da luz")
        user.find("Enviar").click()
        await user.should_see("Arquivo criado: rascunho.md", retries=50)

    assert sorted(path.name for path in EXAMPLE.iterdir()) == bundled
