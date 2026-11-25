"""Starts ManimFlow the way a teacher does and goes through it in a real browser, saving a
screenshot of each step.

CI runs it on a clean Windows runner, in Edge, from a copy of the repository without git
(see .github/workflows/package.yml). It needs Playwright, and nothing from ManimFlow:

    uv run --no-project --with playwright==1.64.1 python .github/try_the_app.py SHOTS uv run manimflow

`SHOTS` is the folder for the screenshots; the rest is the command that starts ManimFlow.
With the demo agent it renders the example's previews through that same command, opens the
example and talks to the agent; with Codex it stops at the sign-in, which needs an account.
Exits with 1 at the first step that doesn't show what it should.
"""

import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

READY = re.compile(r"ready to go on (http://\S+)")
# Codex starts in seconds, but the first start on Windows also sets up its sandbox.
SLOW = 180_000
# Where Codex waits for ChatGPT's redirect after the sign-in.
LOGIN_PORT = 1455


def main(shots: Path, command: list[str]) -> int:
    # The logs it prints are ManimFlow's, in Portuguese, whatever the console's code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        if sys.platform == "win32":
            browser = playwright.chromium.launch(channel="msedge")
        else:
            browser = playwright.chromium.launch(executable_path=os.environ.get("CHROMIUM"))
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="pt-BR")
        page.set_default_timeout(60_000)
        steps = Steps(page, shots)
        with Server([*command, "--demo"], shots / "demo.log") as url:
            lesson = example()
            for scene in scenes(lesson):
                render(command, lesson, scene)
            with steps.step("1-inicio"):
                page.goto(url)
                page.get_by_text("O que vamos animar hoje?").wait_for()
            with steps.step("2-exemplo"):
                page.get_by_role("button", name="Abrir o exemplo").click()
                page.get_by_placeholder("Peça uma mudança…").wait_for()
                page.locator(".mf-stage img, .mf-stage video").first.wait_for()
            with steps.step("3-conversa"):
                page.get_by_placeholder("Peça uma mudança…").fill("muda a cor da luz")
                page.get_by_placeholder("Peça uma mudança…").press("Enter")
                page.get_by_text("Renderizei a prévia de S2 e conferi o último quadro.").wait_for()
            for tab, shot in (("Plano", "4-plano"), ("Código", "5-codigo"), ("Equações", "6-equacoes")):
                with steps.step(shot):
                    page.get_by_role("tab", name=tab).click()
                    page.wait_for_timeout(2_000)
            with steps.step("7-exportar"):
                page.get_by_role("button", name="Exportar", exact=True).first.click()
                page.get_by_role("dialog").wait_for()
                page.wait_for_timeout(1_000)
        with Server(command, shots / "codex.log") as url:
            with steps.step("8-entrar"):
                page.goto(url + "/exemplo")
                page.get_by_role("button", name="Entrar com o ChatGPT").wait_for(timeout=SLOW)
            with steps.step("9-login-aberto"):
                page.get_by_role("button", name="Entrar com o ChatGPT").click()
                page.get_by_text("Termine o login na aba do navegador").wait_for(timeout=SLOW)
                wait_for_port(LOGIN_PORT)
        browser.close()
    return 0


class Steps:
    """Saves a screenshot after each step, and stops at the first step that fails."""

    def __init__(self, page: Page, shots: Path) -> None:
        self.page = page
        self.shots = shots
        self.name = ""

    def step(self, name: str) -> "Steps":
        self.name = name
        return self

    def __enter__(self) -> None:
        print(f"--- {self.name}", flush=True)

    def __exit__(self, kind, error, trace) -> bool:
        suffix = "" if error is None else "-falhou"
        self.page.screenshot(path=str(self.shots / f"{self.name}{suffix}.png"))
        if error is not None:
            raise SystemExit(f"{self.name} failed: {error}")
        return False


class Server:
    """Runs ManimFlow until the block ends; the block gets the address it serves on."""

    def __init__(self, command: list[str], log: Path) -> None:
        self.command = command
        self.log = log

    def __enter__(self) -> str:
        print(f"--- starting {' '.join(self.command)}", flush=True)
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        options: dict = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        )
        self.output = self.log.open("w", encoding="utf-8")
        self.process = subprocess.Popen(self.command, stdout=self.output, stderr=subprocess.STDOUT, env=env, **options)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if found := READY.search(self.log.read_text(encoding="utf-8", errors="replace")):
                return found.group(1)
            if self.process.poll() is not None:
                break
            time.sleep(0.5)
        self.__exit__(None, None, None)
        raise SystemExit(f"ManimFlow didn't start:\n{self.log.read_text(encoding='utf-8', errors='replace')}")

    def __exit__(self, kind, error, trace) -> bool:
        # `uv run` starts Python, which starts Codex: stop them all.
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], capture_output=True)
        else:
            os.killpg(self.process.pid, signal.SIGTERM)
        self.process.wait(timeout=60)
        self.output.close()
        print(self.log.read_text(encoding="utf-8", errors="replace"), flush=True)
        return False


def wait_for_port(port: int) -> None:
    """Waits until something listens on the port on localhost."""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(f"Nothing listens on port {port}.")


def example() -> Path:
    """The copy of the example that ManimFlow made in its own folder when it started."""
    if sys.platform == "win32":
        data = Path(os.environ["LOCALAPPDATA"])
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    (lesson,) = [path for path in (data / "ManimFlow" / "exemplo").iterdir() if path.is_dir()]
    return lesson


def scenes(lesson: Path) -> list[str]:
    """The scenes the example's plan names, each once."""
    names = re.findall(r"^\s*cena:\s*(\S+)", (lesson / "plano.yaml").read_text(encoding="utf-8"), re.MULTILINE)
    return list(dict.fromkeys(names))


def render(command: list[str], lesson: Path, scene: str) -> None:
    print(f"--- rendering the preview of {scene}", flush=True)
    started = time.monotonic()
    run = subprocess.run([*command, "preview", str(lesson), scene], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(run.stdout + run.stderr if run.returncode else f"{time.monotonic() - started:.0f} s", flush=True)
    if run.returncode:
        raise SystemExit(f"The preview of {scene} didn't render.")


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2:]))
