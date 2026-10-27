"""The Codex adapter, run against the real bundled app-server and a local mock model."""

import re
import shutil
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai_codex.generated.v2_all import (
    CommandExecResponse,
    WindowsSandboxReadiness,
    WindowsSandboxReadinessResponse,
    WindowsSandboxSetupCompletedNotification,
    WindowsSandboxSetupMode,
    WindowsSandboxSetupStartResponse,
)
from openai_codex.models import Notification

from manimflow.agent import (
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    FileChanged,
    ModelSettings,
)
from manimflow.codex_agent import BASE_INSTRUCTIONS, SKILL, CodexAgent, _set_up_windows_sandbox
from mock_model import command, message, patch


@pytest.fixture
def lesson(lesson):
    """The fixture lesson, outside the temp folder on Windows, where teachers keep lessons.

    Codex's Windows sandbox never lets the agent into the temp folder, where tmp_path lives.
    """
    if sys.platform != "win32":
        yield lesson
        return
    moved = Path.home() / "ManimFlow testes" / lesson.parent.name / lesson.name
    shutil.rmtree(moved.parent, ignore_errors=True)
    shutil.copytree(lesson, moved)
    yield moved
    shutil.rmtree(moved.parent, ignore_errors=True)


def developer_text(request):
    """Everything the model received as developer instructions in one request."""
    return "\n".join(
        part["text"]
        for item in request["input"]
        if item.get("role") == "developer"
        for part in item.get("content", [])
        if part.get("type") == "input_text"
    )


def user_text(request):
    """The text of the last message the teacher sent, as the model received it."""
    (*_, last) = [text for text in user_messages(request) if not text.startswith("<skill>")]
    return last


async def turn(session, text="oi", attachments=()):
    return [event async for event in session.send(text, attachments)]


async def test_every_new_thread_receives_the_base_instructions(codex_agent, mock_model, lesson):
    for _ in range(2):
        await turn(await codex_agent.start_session(lesson))

    assert len(mock_model.requests) == 2
    for request in mock_model.requests:
        assert BASE_INSTRUCTIONS in developer_text(request)


def user_messages(request):
    """The text of every message the model received as the user's, in order."""
    return [
        "\n".join(part["text"] for part in item["content"] if part.get("type") == "input_text")
        for item in request["input"]
        if item.get("role") == "user"
    ]


async def test_every_new_thread_starts_with_the_manimflow_skill(codex_agent, mock_model, lesson):
    body = SKILL.read_text(encoding="utf-8").split("---", 2)[2].strip()
    for _ in range(2):
        session = await codex_agent.start_session(lesson)
        await turn(session, "primeira")
        await turn(session, "segunda")

    first, second, *_ = mock_model.requests
    assert sum(body in text for text in user_messages(first)) == 1
    # The skill stays in the thread's history; later turns don't send it again.
    assert sum(body in text for text in user_messages(second)) == 1
    assert sum(body in text for text in user_messages(mock_model.requests[2])) == 1


async def test_commands_and_replies_become_interface_events_in_order(codex_agent, mock_model, lesson):
    mock_model.reply(message("Vou listar a pasta."), command("c1", "ls"))
    mock_model.reply(command("c2", "exit 3"))
    mock_model.reply(message("Pronto."))

    events = await turn(await codex_agent.start_session(lesson))

    started_ls, started_exit = [event for event in events if isinstance(event, CommandStarted)]
    assert events == [
        AssistantText("Vou listar a pasta."),
        CommandStarted(started_ls.id, "ls"),
        CommandFinished(started_ls.id, "ls", 0),
        CommandStarted(started_exit.id, "exit 3"),
        CommandFinished(started_exit.id, "exit 3", 3),
        AssistantText("Pronto."),
    ]
    assert started_ls.id != started_exit.id


async def test_file_edits_are_reported_relative_to_the_lesson(codex_agent, mock_model, lesson):
    (lesson / "rascunho.md").write_text("velho\n", encoding="utf-8")
    mock_model.reply(
        patch(
            "p1",
            "*** Add File: notas/novo.md\n+oi\n"
            "*** Update File: cenas.py\n@@\n"
            "-from manim import BLUE, RIGHT, Scene, Square\n"
            "+from manim import BLUE, RIGHT, Scene, Square  # editado\n"
            "*** Delete File: rascunho.md\n",
        )
    )

    events = await turn(await codex_agent.start_session(lesson))

    assert sorted((e for e in events if isinstance(e, FileChanged)), key=lambda e: e.path) == [
        FileChanged("cenas.py", "modified"),
        FileChanged("notas/novo.md", "added"),
        FileChanged("rascunho.md", "deleted"),
    ]


def tool_names(request):
    """Names of every tool offered to the model, nested ones included."""

    def walk(tools):
        for tool in tools:
            yield tool.get("name") or tool.get("type")
            yield from walk(tool.get("tools", []))

    extra = [tool for item in request["input"] if item.get("type") == "additional_tools" for tool in item["tools"]]
    return set(walk(request.get("tools", []) + extra))


async def test_attachments_reach_the_model_with_the_message(codex_agent, mock_model, lesson, tmp_path):
    edits = tmp_path / "edicoes.diff"
    edits.write_text("-COR_LUZ = AMARELO\n+COR_LUZ = VERMELHO\n", encoding="utf-8")

    await turn(await codex_agent.start_session(lesson), "renderiza de novo", [edits])

    sent = user_text(mock_model.requests[-1])
    assert "renderiza de novo" in sent
    assert "edicoes.diff" in sent
    assert "-COR_LUZ = AMARELO\n+COR_LUZ = VERMELHO\n" in sent


async def test_the_agent_can_run_the_manimflow_cli(codex_agent, mock_model, lesson):
    mock_model.reply(command("c1", "manimflow plan validate ."))

    await turn(await codex_agent.start_session(lesson))

    code, output = shell_result(mock_model.requests[-1], "c1")
    assert code == 0, output


async def test_the_agent_can_run_the_lessons_physics_tests(codex_agent, mock_model, lesson):
    (lesson / "fisica.py").write_text("def equacoes():\n    return []\n", encoding="utf-8")
    (lesson / "test_fisica.py").write_text(
        "from fisica import equacoes\n\n\ndef test_equacoes():\n    assert equacoes() == []\n", encoding="utf-8"
    )
    # The command the agent instructions give.
    mock_model.reply(command("c1", "python -m pytest -q -p no:cacheprovider test_fisica.py"))

    await turn(await codex_agent.start_session(lesson))

    code, output = shell_result(mock_model.requests[-1], "c1")
    assert code == 0, output
    assert "1 passed" in output


def shell_result(request, call_id):
    """The exit code and output Codex reported to the model for one of its shell calls."""
    (output,) = [item["output"] for item in request["input"] if item.get("call_id") == call_id and "output" in item]
    match = re.search(r"exited with code (-?\d+)", output)
    assert match, output
    return int(match.group(1)), output


async def test_the_agent_writes_only_inside_the_lesson(codex_agent, mock_model, lesson):
    write_inside = "python -c \"open('dentro.txt', 'w').write('x')\""
    mock_model.reply(
        command("c1", write_inside),
        command("c2", "python -c \"open('../fora.txt', 'w').write('x')\""),
        patch("p1", "*** Add File: ../fora_patch.txt\n+x\n"),
    )

    events = await turn(await codex_agent.start_session(lesson))

    assert (lesson / "dentro.txt").exists(), shell_result(mock_model.requests[-1], "c1")[1]
    assert not (lesson.parent / "fora.txt").exists()
    assert not (lesson.parent / "fora_patch.txt").exists()
    assert shell_result(mock_model.requests[-1], "c2")[0] != 0
    # Codex reports a command the sandbox stopped only to the model, not as an item.
    assert [event.command for event in events if isinstance(event, CommandFinished) and event.ok] == [write_inside]
    assert not [event for event in events if isinstance(event, FileChanged)]


INTERNET = ("1.1.1.1", 443)


@pytest.mark.parametrize("target", ["mock model", "internet"])
async def test_the_agent_has_no_network(codex_agent, mock_model, lesson, target):
    if target == "mock model":
        if sys.platform == "win32":
            pytest.skip("Codex's Windows sandbox blocks the network but not loopback")
        host, port = mock_model.address
    else:
        host, port = INTERNET
        try:
            socket.create_connection(INTERNET, timeout=5).close()
        except OSError:
            pytest.skip("this machine has no internet either")
    # Codex offers web search to models outside its catalog.
    await codex_agent.set_model_settings(ModelSettings("sem-catalogo", "medium"))
    mock_model.reply(
        command("c1", f"python -c \"import socket; socket.create_connection(('{host}', {port}), timeout=5)\""),
    )

    events = await turn(await codex_agent.start_session(lesson))

    code, output = shell_result(mock_model.requests[-1], "c1")
    assert code != 0, output
    assert not [event for event in events if isinstance(event, CommandFinished) and event.ok]
    assert "web_search" not in tool_names(mock_model.requests[0])


@pytest.mark.parametrize(
    ("status", "error", "explanation"),
    [
        (
            429,
            {"message": "limit", "type": "usage_limit_reached"},
            "Você atingiu o limite de uso do seu plano. Tente de novo mais tarde.",
        ),
        (
            429,
            {"message": "slow down", "type": "rate_limit_exceeded", "code": "rate_limit_exceeded"},
            "O serviço recebeu pedidos demais. Espere um minuto e tente de novo.",
        ),
        (
            401,
            {"message": "bad key", "type": "invalid_request_error", "code": "invalid_api_key"},
            "O Codex recusou o seu login. Entre de novo com o ChatGPT ou com uma chave de API.",
        ),
        (
            500,
            {"message": "boom", "type": "server_error"},
            "O serviço da OpenAI está instável agora. Tente de novo em alguns minutos.",
        ),
        (
            400,
            {"message": "bad request", "type": "invalid_request_error"},
            "O agente parou por um erro inesperado.",
        ),
    ],
)
async def test_a_failed_turn_is_explained_in_portuguese(codex_agent, mock_model, lesson, status, error, explanation):
    mock_model.fail(status, error)

    events = await turn(await codex_agent.start_session(lesson))

    assert events == [AgentError(explanation)]


async def test_a_sandbox_that_cant_start_stops_the_turn_before_the_model(codex_home, mock_model, lesson):
    agent = CodexAgent(codex_home, sandbox_problem=lambda path: "O Ubuntu bloqueia o isolamento.")
    try:
        events = await turn(await agent.start_session(lesson))
    finally:
        await agent.close()

    assert events == [AgentError("O Ubuntu bloqueia o isolamento.")]
    assert mock_model.requests == []


def model_used(request):
    return ModelSettings(request["model"], request["reasoning"]["effort"])


async def test_turns_use_the_model_settings(codex_agent, mock_model, lesson):
    session = await codex_agent.start_session(lesson)

    await turn(session)
    assert model_used(mock_model.requests[-1]) == await codex_agent.model_settings()

    await codex_agent.set_model_settings(ModelSettings("gpt-5.5", "high"))
    await turn(session)
    assert model_used(mock_model.requests[-1]) == ModelSettings("gpt-5.5", "high")
    assert await codex_agent.model_settings() == ModelSettings("gpt-5.5", "high")


class FakeWindowsSandbox:
    """The app-server's Windows sandbox requests, with an elevated setup that may fail."""

    def __init__(self, readiness, elevated_works):
        self.readiness = readiness
        self.elevated_works = elevated_works
        self.setups = []
        self.commands = []
        self._completed = []

    async def request(self, method, params, response_model):
        match method:
            case "windowsSandbox/readiness":
                return WindowsSandboxReadinessResponse(status=self.readiness)
            case "windowsSandbox/setupStart":
                mode = WindowsSandboxSetupMode(params["mode"])
                self.setups.append(mode)
                works = mode == WindowsSandboxSetupMode.unelevated or self.elevated_works
                payload = WindowsSandboxSetupCompletedNotification(mode=mode, success=works)
                self._completed.append(Notification("windowsSandbox/setupCompleted", payload))
                return WindowsSandboxSetupStartResponse(started=True)
            case "command/exec":
                self.commands.append(params)
                return CommandExecResponse(exitCode=0, stdout="", stderr="")

    async def next_notification(self):
        return self._completed.pop(0)


@pytest.mark.parametrize(
    ("readiness", "elevated_works", "setups"),
    [
        (WindowsSandboxReadiness.not_configured, True, [WindowsSandboxSetupMode.elevated]),
        (
            WindowsSandboxReadiness.not_configured,
            False,
            [WindowsSandboxSetupMode.elevated, WindowsSandboxSetupMode.unelevated],
        ),
        (WindowsSandboxReadiness.ready, True, []),
    ],
)
async def test_the_windows_sandbox_prefers_elevated_and_falls_back_without_administrator(
    tmp_path, readiness, elevated_works, setups
):
    sandbox = FakeWindowsSandbox(readiness, elevated_works)

    await _set_up_windows_sandbox(SimpleNamespace(_client=sandbox), tmp_path)

    assert sandbox.setups == setups
    # One command through the sandbox, which starts Codex's read grants for the teacher's folders.
    assert [command["cwd"] for command in sandbox.commands] == [str(tmp_path)]
