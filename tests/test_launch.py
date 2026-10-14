import tempfile

from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from manimflow.cli import main
from conftest import EXAMPLE


def launch(monkeypatch, tmp_path, *args):
    """Runs `manimflow` without starting a server and returns what it passed to ui.run."""
    calls = []
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
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


async def test_demo_opens_a_copy_of_the_bundled_example_with_the_scripted_agent(monkeypatch, tmp_path):
    bundled = sorted(path.name for path in EXAMPLE.iterdir())
    root, _ = launch(monkeypatch, tmp_path, "--demo")

    async with user_simulation(root=root) as user:
        await user.open("/")
        await user.should_see("Relatividade - herói e espelho")

        user.find(marker="mensagem").type("muda a cor da luz")
        user.find("Enviar").click()
        await user.should_see("Arquivo criado: rascunho.md", retries=50)

    assert sorted(path.name for path in EXAMPLE.iterdir()) == bundled
