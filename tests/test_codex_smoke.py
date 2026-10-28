"""Opt-in smoke test of the real Codex agent, run by hand and excluded from CI.

It needs ManimFlow signed in to Codex (run `manimflow` once and sign in) and it
spends some of that account's quota. Run it with:

    uv run pytest -m smoke
"""

import re
import shutil

import pytest

from manimflow.agent import AgentError, AssistantText, CommandFinished
from manimflow.codex_agent import CodexAgent, default_codex_home
from conftest import EXAMPLE

pytestmark = pytest.mark.smoke


@pytest.fixture
async def agent():
    agent = CodexAgent(default_codex_home())
    try:
        if not (await agent.account()).logged_in:
            pytest.skip("ManimFlow is not signed in to Codex; run `manimflow` and sign in first.")
        yield agent
    finally:
        await agent.close()


@pytest.fixture
def example_lesson(tmp_path):
    shutil.copy(EXAMPLE.parent / "perfil.md", tmp_path)
    return shutil.copytree(EXAMPLE, tmp_path / "Relatividade - herói e espelho")


def light_color(lesson):
    match = re.search(r"^COR_LUZ = (.+)$", (lesson / "cenas.py").read_text(encoding="utf-8"), re.M)
    return match and match.group(1).strip()


async def send(agent, lesson, text):
    session = await agent.start_session(lesson)
    events = [event async for event in session.send(text)]
    print(*events, sep="\n")
    assert not [event for event in events if isinstance(event, AgentError)]
    assert [event for event in events if isinstance(event, AssistantText)]
    return events


async def test_changing_the_light_color_edits_the_scenes_and_renders(agent, example_lesson, manimflow):
    before = light_color(example_lesson)

    events = await send(agent, example_lesson, "Muda a cor da luz para vermelho e confere a cena S2_Reflexao.")

    assert light_color(example_lesson) not in (None, before)
    assert any(
        isinstance(event, CommandFinished) and event.ok and event.command.startswith("manimflow ")
        for event in events
    )
    rendered = manimflow("preview", str(example_lesson), "S2_Reflexao")
    assert rendered.returncode == 0, rendered.stderr


async def test_the_agent_cannot_write_outside_the_lesson_or_reach_the_network(agent, example_lesson):
    await send(
        agent,
        example_lesson,
        "Rode exatamente estes dois comandos no terminal, um de cada vez, sem mudar nada, "
        "e me diga o que cada um respondeu:\n\n"
        "python -c \"open('tentou_fora.txt', 'w').write('x'); open('../fora.txt', 'w').write('x')\"\n\n"
        "python -c \"import urllib.request; open('tentou_rede.txt', 'w').write('x'); "
        "urllib.request.urlopen('https://example.com', timeout=10); open('rede.txt', 'w').write('x')\"",
    )

    # Each command first leaves a mark inside the lesson, which shows the agent
    # did run it; what comes after the mark is what the sandbox must stop.
    assert (example_lesson / "tentou_fora.txt").exists()
    assert not (example_lesson.parent / "fora.txt").exists()
    assert (example_lesson / "tentou_rede.txt").exists()
    assert not (example_lesson / "rede.txt").exists()


async def test_a_chatgpt_account_shows_its_plan_usage(agent):
    if (await agent.account()).method != "chatgpt":
        pytest.skip("ManimFlow is signed in with an API key, which has no plan quota.")

    quota = await agent.quota()

    print(quota)
    assert quota
    assert all(0 <= window.used_percent <= 100 and window.minutes for window in quota)
