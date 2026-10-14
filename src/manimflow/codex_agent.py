"""The `Agent` interface on top of Codex, through the official `openai-codex` SDK.

The SDK starts the bundled Codex app-server once and keeps it for the app's
lifetime. Every session is a new Codex thread rooted in the lesson folder, with
the ManimFlow base instructions, a sandbox that only writes inside the lesson,
no network and no approval prompts.
"""

import asyncio
import logging
import os
import sysconfig
import webbrowser
from collections.abc import AsyncIterator, Callable, Sequence
from importlib.resources import files
from pathlib import Path

from openai_codex import ApprovalMode, AsyncCodex, AsyncThread, CodexConfig, CodexError, Sandbox
from openai_codex.generated.v2_all import (
    AddPatchChangeKind,
    AgentMessageThreadItem,
    ApiKeyAccount,
    ChatgptAccount,
    CodexErrorInfoValue,
    CommandExecutionThreadItem,
    DeletePatchChangeKind,
    FileChangeThreadItem,
    FileUpdateChange,
    ItemCompletedNotification,
    ItemStartedNotification,
    PatchApplyStatus,
    ReasoningEffort,
    Turn,
    TurnCompletedNotification,
    TurnStatus,
)
from openai_codex.models import JsonObject, Notification
from pydantic import BaseModel

from manimflow.agent import (
    Account,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    LoginFailed,
    ModelSettings,
)

logger = logging.getLogger(__name__)

BASE_INSTRUCTIONS = (files("manimflow") / "agent_instructions.md").read_text(encoding="utf-8")

# Codex config for every thread. By default workspace_write also lets the agent
# write to the temp folders, and the model may search the web; the lesson
# folder is the only place it may touch.
THREAD_CONFIG: JsonObject = {
    "sandbox_workspace_write": {
        "network_access": False,
        "exclude_slash_tmp": True,
        "exclude_tmpdir_env_var": True,
    },
    "web_search": "disabled",
}


class CodexAgent:
    def __init__(self, home: Path, open_browser: Callable[[str], object] = webbrowser.open) -> None:
        """`home` is the Codex home that holds ManimFlow's login, config and threads."""
        self.home = home.absolute()
        self._open_browser = open_browser
        self._codex: AsyncCodex | None = None
        self._settings: ModelSettings | None = None

    async def _client(self) -> AsyncCodex:
        if self._codex is None:
            # The app-server refuses to start when its home is missing.
            self.home.mkdir(parents=True, exist_ok=True)
            # `uvx manimflow` doesn't put its environment on PATH, and the agent
            # renders through the `manimflow` script that lives there.
            scripts = sysconfig.get_path("scripts")
            path = os.pathsep.join([scripts, os.environ.get("PATH", "")])
            env = {"CODEX_HOME": str(self.home), "PATH": path}
            self._codex = AsyncCodex(CodexConfig(env=env))
        return self._codex

    async def start_session(self, lesson: Path) -> "CodexSession":
        codex = await self._client()
        thread = await codex.thread_start(
            cwd=str(lesson.absolute()),
            sandbox=Sandbox.workspace_write,
            approval_mode=ApprovalMode.deny_all,
            developer_instructions=BASE_INSTRUCTIONS,
            config=THREAD_CONFIG,
        )
        return CodexSession(lesson, thread, self)

    async def model_settings(self) -> ModelSettings:
        if self._settings is None:
            codex = await self._client()
            catalog = (await codex.models()).data
            default = next(model for model in catalog if model.is_default)
            self._settings = ModelSettings(default.model, default.default_reasoning_effort.value)
        return self._settings

    async def set_model_settings(self, settings: ModelSettings) -> None:
        """Applies from the next turn on, in every session."""
        self._settings = settings

    async def account(self) -> Account:
        codex = await self._client()
        state = await codex.account()
        match state.account.root if state.account else None:
            case ApiKeyAccount():
                return Account(logged_in=True, method="api_key")
            case ChatgptAccount(email=email):
                return Account(logged_in=True, method="chatgpt", email=email)
        # A provider configured without OpenAI auth, such as a local model, needs no login.
        return Account(logged_in=state.account is not None or not state.requires_openai_auth)

    async def login(self, api_key: str | None = None) -> Account:
        codex = await self._client()
        if api_key is not None:
            if not api_key.strip():
                raise LoginFailed("Cole a sua chave de API da OpenAI para entrar.")
            try:
                await codex.login_api_key(api_key.strip())
            except CodexError as error:
                logger.warning("Codex refused the API key: %s", error)
                raise LoginFailed("O Codex não aceitou essa chave de API. Confira se ela está completa.") from error
            return await self.account()

        # Codex listens on a 127.0.0.1 loopback port for the browser's redirect.
        attempt = await codex.login_chatgpt()
        await asyncio.to_thread(self._open_browser, attempt.auth_url)
        outcome = await attempt.wait()
        if not outcome.success:
            logger.warning("ChatGPT login failed: %s", outcome.error)
            raise LoginFailed("O login com o ChatGPT não foi concluído. Tente de novo.")
        return await self.account()

    async def close(self) -> None:
        if self._codex is not None:
            await self._codex.close()


class CodexSession:
    def __init__(self, lesson: Path, thread: AsyncThread, agent: CodexAgent) -> None:
        self.lesson = lesson
        self._thread = thread
        self._agent = agent

    async def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        settings = await self._agent.model_settings()
        parts = [text] + [
            f"Anexo {path.name}:\n\n{path.read_text(encoding='utf-8')}" for path in attachments
        ]
        handle = await self._thread.turn(
            "\n\n".join(parts), model=settings.model, effort=ReasoningEffort(settings.effort)
        )
        async for notification in handle.stream():
            for event in _events(notification, self.lesson):
                yield event


def _events(notification: Notification, lesson: Path) -> list[Event]:
    """Translates one app-server notification into the interface's events."""
    match notification.payload:
        case ItemStartedNotification(item=item):
            match item.root:
                case CommandExecutionThreadItem() as run:
                    return [CommandStarted(run.id, _command(run))]
        case ItemCompletedNotification(item=item):
            match item.root:
                case AgentMessageThreadItem(text=text):
                    return [AssistantText(text)]
                case CommandExecutionThreadItem() as run:
                    # A command the sandbox refused never gets an exit code.
                    exit_code = run.exit_code if run.exit_code is not None else -1
                    return [CommandFinished(run.id, _command(run), exit_code)]
                case FileChangeThreadItem(status=PatchApplyStatus.completed, changes=changes):
                    return [_file_changed(change, lesson) for change in changes]
        case TurnCompletedNotification(turn=turn) if turn.status != TurnStatus.completed:
            return [_turn_failed(turn)]
    return []


def _command(run: CommandExecutionThreadItem) -> str:
    """The command as the agent wrote it, without the shell that Codex wraps it in."""
    if len(run.command_actions) == 1:
        return run.command_actions[0].root.command
    return run.command


def _file_changed(change: FileUpdateChange, lesson: Path) -> FileChanged:
    path = Path(change.path).resolve()
    if path.is_relative_to(lesson.resolve()):
        shown = path.relative_to(lesson.resolve()).as_posix()
    else:
        shown = str(path)
    match change.kind.root:
        case AddPatchChangeKind():
            return FileChanged(shown, "added")
        case DeletePatchChangeKind():
            return FileChanged(shown, "deleted")
    return FileChanged(shown, "modified")


_LOGIN_REFUSED = "O Codex recusou o seu login. Entre de novo com o ChatGPT ou com uma chave de API."
_TOO_MANY_REQUESTS = "O serviço recebeu pedidos demais. Espere um minuto e tente de novo."
_SERVICE_UNSTABLE = "O serviço da OpenAI está instável agora. Tente de novo em alguns minutos."
_UNEXPECTED = "O agente parou por um erro inesperado."

_EXPLANATIONS = {
    CodexErrorInfoValue.usage_limit_exceeded: "Você atingiu o limite de uso do seu plano. Tente de novo mais tarde.",
    CodexErrorInfoValue.rate_limit_exceeded: _TOO_MANY_REQUESTS,
    CodexErrorInfoValue.unauthorized: _LOGIN_REFUSED,
    CodexErrorInfoValue.context_window_exceeded: (
        "A conversa ficou longa demais. Recarregue a página para começar uma sessão nova."
    ),
    CodexErrorInfoValue.internal_server_error: _SERVICE_UNSTABLE,
    CodexErrorInfoValue.server_overloaded: _SERVICE_UNSTABLE,
}


def _turn_failed(turn: Turn) -> AgentError:
    """Explains a failed or interrupted turn to the teacher; Codex's own message is in English."""
    if turn.status == TurnStatus.interrupted:
        return AgentError("A resposta foi interrompida antes de terminar.")
    error = turn.error
    logger.warning("Codex turn failed: %s", error.message if error else turn.status)
    info = error.codex_error_info.root if error and error.codex_error_info else None
    if isinstance(info, CodexErrorInfoValue):
        return AgentError(_EXPLANATIONS.get(info, _UNEXPECTED))
    if isinstance(info, BaseModel):
        # The connection variants each wrap one object with the HTTP status, if any.
        (details,) = info.model_dump().values()
        status = details.get("http_status_code") if isinstance(details, dict) else None
        if status is None:
            return AgentError("Não foi possível falar com a OpenAI. Confira a sua internet e tente de novo.")
        if status in (401, 403):
            return AgentError(_LOGIN_REFUSED)
        if status == 429:
            return AgentError(_TOO_MANY_REQUESTS)
        if status >= 500:
            return AgentError(_SERVICE_UNSTABLE)
    return AgentError(_UNEXPECTED)
