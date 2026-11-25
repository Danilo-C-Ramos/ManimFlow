"""The Codex adapter, run against the real bundled app-server and a local mock model."""

import asyncio
import re
import shutil
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
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
    ImageViewed,
    ModelSettings,
    Working,
)
from manimflow.codex_agent import BASE_INSTRUCTIONS, SKILL, CodexAgent, _set_up_windows_sandbox
from manimflow.model_presets import CAREFUL, EFFORTS, LIMITED_MODELS, MODELS, QUICK
from mock_model import command, message, patch, view_image


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


async def turn(session, text="oi", attachments=(), output_schema=None):
    """The turn's events, without what only shows in the progress bar."""
    return [event async for event in session.send(text, attachments, output_schema) if not isinstance(event, Working)]


async def test_the_progress_bar_hears_the_agent_writing(codex_agent, mock_model, lesson):
    mock_model.reply(message("Pronto."))
    session = await codex_agent.session(lesson)

    events = [event async for event in session.send("oi")]

    assert events == [Working("Escrevendo a resposta"), AssistantText("Pronto.")]


async def test_the_lessons_conversation_continues_in_its_thread_with_the_base_instructions(
    codex_agent, mock_model, lesson
):
    mock_model.reply(message("Desenhei o espelho."))
    await turn(await codex_agent.session(lesson), "desenha o espelho")
    # As when the teacher comes back to the lesson, or opens ManimFlow again.
    await turn(await codex_agent.session(lesson), "aumenta a fonte")

    assert len(mock_model.requests) == 2
    for request in mock_model.requests:
        assert BASE_INSTRUCTIONS in developer_text(request)
    later = mock_model.requests[1]
    assert any("desenha o espelho" in text for text in user_messages(later))
    assert any(
        part.get("text") == "Desenhei o espelho."
        for item in later["input"]
        if item.get("role") == "assistant"
        for part in item.get("content", [])
    )


def user_messages(request):
    """The text of every message the model received as the user's, in order."""
    return [
        "\n".join(part["text"] for part in item["content"] if part.get("type") == "input_text")
        for item in request["input"]
        if item.get("role") == "user"
    ]


async def test_the_conversation_starts_with_the_manimflow_skill_once(codex_agent, mock_model, lesson):
    body = SKILL.read_text(encoding="utf-8").split("---", 2)[2].strip()
    session = await codex_agent.session(lesson)
    await turn(session, "primeira")
    await turn(session, "segunda")
    await turn(await codex_agent.session(lesson), "terceira")

    def skills_sent(request):
        # Codex sends the file as written, and on Windows the installed copy has CRLF.
        return sum(body in text.replace("\r\n", "\n") for text in user_messages(request))

    # The skill stays in the thread's history; later turns, resumed ones too, don't send it again.
    assert [skills_sent(request) for request in mock_model.requests] == [1, 1, 1]


async def test_commands_and_replies_become_interface_events_in_order(codex_agent, mock_model, lesson):
    mock_model.reply(message("Vou listar a pasta."), command("c1", "ls"))
    mock_model.reply(command("c2", "exit 3"))
    mock_model.reply(message("Pronto."))

    events = await turn(await codex_agent.session(lesson))

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

    events = await turn(await codex_agent.session(lesson))

    assert sorted((e for e in events if isinstance(e, FileChanged)), key=lambda e: e.path) == [
        FileChanged("cenas.py", "modified"),
        FileChanged("notas/novo.md", "added"),
        FileChanged("rascunho.md", "deleted"),
    ]


async def test_the_lessons_history_holds_every_turn_as_the_chat_showed_it(codex_agent, mock_model, lesson):
    other = lesson.parent / "Outra aula"
    other.mkdir()
    mock_model.reply(message("Vou ler o plano."), command("c1", "cat plano.yaml"))
    mock_model.reply(patch("p1", "*** Add File: notas.md\n+oi\n"))
    mock_model.reply(message("Pronto."))
    mock_model.reply(message("Desenhei a onda."))
    mock_model.reply(message("Fonte maior."))
    session = await codex_agent.session(lesson)
    await turn(session, "lê o plano")
    await turn(await codex_agent.session(other), "desenha a onda")
    await turn(await codex_agent.session(lesson), "aumenta a fonte")

    history = await codex_agent.lesson_history(lesson)

    assert [past.request for past in history] == ["lê o plano", "aumenta a fonte"]
    first, second = history
    started = next(event for event in first.events if isinstance(event, CommandStarted))
    assert first.events == [
        AssistantText("Vou ler o plano."),
        CommandStarted(started.id, "cat plano.yaml"),
        CommandFinished(started.id, "cat plano.yaml", 0),
        FileChanged("notas.md", "added"),
        AssistantText("Pronto."),
    ]
    if sys.platform != "win32":
        assert started.reads == ("plano.yaml",)
    assert second.events == [AssistantText("Fonte maior.")]
    # One conversation: the second turn continued the first one's thread.
    assert first.session == second.session
    assert first.id == session.last_turn
    assert first.started_at is not None and first.started_at.tzinfo is not None


@pytest.mark.skipif(
    sys.platform == "win32", reason="Codex names the files a command reads only for POSIX shells, not PowerShell"
)
async def test_a_command_that_only_reads_names_the_files(codex_agent, mock_model, lesson):
    mock_model.reply(command("c1", "cat plano.yaml; cat cenas.py"))

    events = await turn(await codex_agent.session(lesson))

    (started,) = [event for event in events if isinstance(event, CommandStarted)]
    assert started.reads == ("plano.yaml", "cenas.py")


async def test_the_answer_format_reaches_the_model(codex_agent, mock_model, lesson):
    schema = {"type": "object", "properties": {"mensagem": {"type": "string"}}, "required": ["mensagem"], "additionalProperties": False}
    mock_model.reply(message('{"mensagem": "Plano pronto."}'))

    events = await turn(await codex_agent.session(lesson), "faz o plano", output_schema=schema)

    assert events == [AssistantText('{"mensagem": "Plano pronto."}')]
    assert mock_model.requests[-1]["text"]["format"]["schema"] == schema


async def test_stop_interrupts_the_running_turn(codex_agent, mock_model, lesson):
    mock_model.reply(command("c1", "sleep 30"))
    session = await codex_agent.session(lesson)
    events = []

    async def run():
        async for event in session.send("demora"):
            events.append(event)
            if isinstance(event, CommandStarted):
                await session.stop()

    await asyncio.wait_for(run(), timeout=20)

    assert events[-1] == AgentError("A resposta foi interrompida antes de terminar.")


async def test_stop_before_the_turn_starts_keeps_it_from_reaching_the_model(codex_agent, mock_model, lesson):
    session = await codex_agent.session(lesson)
    settings = codex_agent.model_settings

    async def stopped_meanwhile():
        # As "Parar" pressed while the thread starts or resumes.
        await session.stop()
        return await settings()

    codex_agent.model_settings = stopped_meanwhile

    events = await turn(session, "demora")

    assert events == [AgentError("A resposta foi interrompida antes de terminar.", delivered=False)]
    assert mock_model.requests == []
    # The next message is the thread's first, so it still brings the skill.
    codex_agent.model_settings = settings
    await turn(session, "agora vai")
    body = SKILL.read_text(encoding="utf-8").split("---", 2)[2].strip()
    assert any(body in text.replace("\r\n", "\n") for text in user_messages(mock_model.requests[0]))


async def test_archiving_starts_the_lessons_conversation_over(codex_agent, mock_model, lesson):
    await turn(await codex_agent.session(lesson), "primeira")

    await codex_agent.archive(lesson)

    assert await codex_agent.lesson_history(lesson) == []
    await turn(await codex_agent.session(lesson), "de novo")
    assert [past.request for past in await codex_agent.lesson_history(lesson)] == ["de novo"]


async def test_the_frames_the_agent_looks_at_become_events(codex_agent, mock_model, lesson):
    frame = lesson / "saida" / "previa" / "quadros" / "S0-S1_fim.png"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(frame)
    mock_model.reply(view_image("v1", "saida/previa/quadros/S0-S1_fim.png"))
    mock_model.reply(message("O quadro final está certo."))

    events = await turn(await codex_agent.session(lesson))

    assert events == [ImageViewed("saida/previa/quadros/S0-S1_fim.png"), AssistantText("O quadro final está certo.")]
    assert any(
        part.get("type") == "input_image"
        for item in mock_model.requests[-1]["input"]
        if item.get("call_id") == "v1" and "output" in item
        for part in item["output"]
    )


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

    await turn(await codex_agent.session(lesson), "renderiza de novo", [edits])

    sent = user_text(mock_model.requests[-1])
    assert "renderiza de novo" in sent
    assert "edicoes.diff" in sent
    assert "-COR_LUZ = AMARELO\n+COR_LUZ = VERMELHO\n" in sent


async def test_the_agent_can_run_the_manimflow_cli(codex_agent, mock_model, lesson):
    mock_model.reply(command("c1", "manimflow plan validate ."))

    await turn(await codex_agent.session(lesson))

    code, output = shell_result(mock_model.requests[-1], "c1")
    assert code == 0, output


async def test_the_agent_can_run_the_lessons_physics_tests(codex_agent, mock_model, lesson):
    (lesson / "fisica.py").write_text("def equacoes():\n    return []\n", encoding="utf-8")
    (lesson / "test_fisica.py").write_text(
        "from fisica import equacoes\n\n\ndef test_equacoes():\n    assert equacoes() == []\n", encoding="utf-8"
    )
    # The command the agent instructions give.
    mock_model.reply(command("c1", "python -m pytest -q -p no:cacheprovider test_fisica.py"))

    await turn(await codex_agent.session(lesson))

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

    events = await turn(await codex_agent.session(lesson))

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

    events = await turn(await codex_agent.session(lesson))

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
        (
            # What a ChatGPT Free account got when asked for GPT-6.1-Sol.
            400,
            {
                "type": "invalid_request_error",
                "message": "The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.",
                "code": "model_not_found",
                "subreason": "model_not_in_accessible_catalog",
            },
            'O seu plano não inclui esse modelo. Escolha outro em Configurações, na parte "Avançado".',
        ),
    ],
)
async def test_a_failed_turn_is_explained_in_portuguese(codex_agent, mock_model, lesson, status, error, explanation):
    mock_model.fail(status, error)

    events = await turn(await codex_agent.session(lesson))

    assert events == [AgentError(explanation)]


async def test_a_sandbox_that_cant_start_stops_the_turn_before_the_model(codex_home, mock_model, lesson):
    agent = CodexAgent(codex_home, sandbox_problem=lambda path: "O Ubuntu bloqueia o isolamento.")
    try:
        events = await turn(await agent.session(lesson))
    finally:
        await agent.close()

    assert events == [AgentError("O Ubuntu bloqueia o isolamento.", delivered=False)]
    assert mock_model.requests == []


def model_used(request):
    return ModelSettings(request["model"], request["reasoning"]["effort"])


async def test_turns_use_the_model_settings(codex_agent, mock_model, lesson):
    session = await codex_agent.session(lesson)

    await turn(session)
    assert model_used(mock_model.requests[-1]) == await codex_agent.model_settings()

    await codex_agent.set_model_settings(ModelSettings("gpt-5.5", "high"))
    await turn(session)
    assert model_used(mock_model.requests[-1]) == ModelSettings("gpt-5.5", "high")
    assert await codex_agent.model_settings() == ModelSettings("gpt-5.5", "high")


async def test_turns_start_on_the_rapido_preset(codex_agent, mock_model, lesson):
    await turn(await codex_agent.session(lesson))

    # Without a ChatGPT plan, as with an API key, the switch takes the newest Sol.
    assert model_used(mock_model.requests[-1]) == ModelSettings(MODELS[0], EFFORTS[QUICK])
    assert (await codex_agent.presets())[CAREFUL] == ModelSettings(MODELS[0], EFFORTS[CAREFUL])


async def test_the_catalog_offers_each_plans_model_at_both_efforts(codex_agent):
    """When OpenAI retires one of these models, update model_presets.py and docs/models.md."""
    models = {option.model: option for option in await codex_agent.models()}

    for model in (MODELS[0], LIMITED_MODELS[0]):
        assert set(EFFORTS.values()) <= set(models[model].efforts)
    assert all(option.default_effort in option.efforts for option in models.values())


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


async def test_the_history_shows_the_teachers_words_without_the_attachments(codex_agent, mock_model, lesson, tmp_path):
    edits = tmp_path / "edicoes-manuais.diff"
    edits.write_text("-COR_LUZ = AMARELO\n+COR_LUZ = VERMELHO\n", encoding="utf-8")
    mock_model.reply(message("Mantive o vermelho."))
    await turn(await codex_agent.session(lesson), "renderiza de novo", [edits])

    (past,) = await codex_agent.lesson_history(lesson)

    assert past.request == "renderiza de novo"
    assert past.events == [AssistantText("Mantive o vermelho.")]
