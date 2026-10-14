"""The Codex adapter, run against the real bundled app-server and a local mock model."""

import re

import pytest

from manimflow.agent import (
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    FileChanged,
    ModelSettings,
)
from manimflow.codex_agent import BASE_INSTRUCTIONS
from mock_model import command, message, patch


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
    (*_, last) = [item for item in request["input"] if item.get("role") == "user"]
    return "\n".join(part["text"] for part in last["content"] if part.get("type") == "input_text")


async def turn(session, text="oi", attachments=()):
    return [event async for event in session.send(text, attachments)]


async def test_every_new_thread_receives_the_base_instructions(codex_agent, mock_model, lesson):
    for _ in range(2):
        await turn(await codex_agent.start_session(lesson))

    assert len(mock_model.requests) == 2
    for request in mock_model.requests:
        assert BASE_INSTRUCTIONS in developer_text(request)


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

    assert exit_code(mock_model.requests[-1], "c1") == 0


def exit_code(request, call_id):
    """The exit code Codex reported to the model for one of its shell calls."""
    (output,) = [item["output"] for item in request["input"] if item.get("call_id") == call_id and "output" in item]
    return int(re.search(r"exited with code (-?\d+)", output).group(1))


async def test_the_agent_writes_only_inside_the_lesson(codex_agent, mock_model, lesson):
    write_inside = "python -c \"open('dentro.txt', 'w').write('x')\""
    mock_model.reply(
        command("c1", write_inside),
        command("c2", "python -c \"open('../fora.txt', 'w').write('x')\""),
        patch("p1", "*** Add File: ../fora_patch.txt\n+x\n"),
    )

    events = await turn(await codex_agent.start_session(lesson))

    assert (lesson / "dentro.txt").exists()
    assert not (lesson.parent / "fora.txt").exists()
    assert not (lesson.parent / "fora_patch.txt").exists()
    assert exit_code(mock_model.requests[-1], "c2") != 0
    # Codex reports a command the sandbox stopped only to the model, not as an item.
    assert [event.command for event in events if isinstance(event, CommandFinished) and event.ok] == [write_inside]
    assert not [event for event in events if isinstance(event, FileChanged)]


async def test_the_agent_has_no_network(codex_agent, mock_model, lesson):
    # Codex offers web search to models outside its catalog.
    await codex_agent.set_model_settings(ModelSettings("sem-catalogo", "medium"))
    host, port = mock_model.address
    mock_model.reply(
        command("c1", f"python -c \"import socket; socket.create_connection(('{host}', {port}), timeout=5)\""),
    )

    events = await turn(await codex_agent.start_session(lesson))

    assert exit_code(mock_model.requests[-1], "c1") != 0
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
