"""The `Agent` interface on top of Codex, through the official `openai-codex` SDK.

The SDK starts the bundled Codex app-server once and keeps it for the app's
lifetime. Every session is a new Codex thread rooted in the lesson folder, with
the ManimFlow base instructions, a sandbox that only writes inside the lesson,
no network and no approval prompts.
"""

import asyncio
import ctypes
import logging
import os
import sys
import sysconfig
import webbrowser
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from openai_codex import ApprovalMode, AsyncCodex, AsyncThread, CodexConfig, CodexError, Sandbox
from openai_codex.async_client import AsyncCodexClient
from openai_codex.generated.v2_all import (
    AddPatchChangeKind,
    AgentMessageThreadItem,
    ApiKeyAccount,
    ChatgptAccount,
    CodexErrorInfoValue,
    CommandExecParams,
    CommandExecResponse,
    CommandExecutionThreadItem,
    DeletePatchChangeKind,
    FileChangeThreadItem,
    FileUpdateChange,
    GetAccountRateLimitsResponse,
    ItemCompletedNotification,
    ItemStartedNotification,
    PatchApplyStatus,
    RateLimitWindow,
    ReasoningEffort,
    Turn,
    TurnCompletedNotification,
    TurnStatus,
    WindowsSandboxReadiness,
    WindowsSandboxReadinessResponse,
    WindowsSandboxSetupCompletedNotification,
    WindowsSandboxSetupMode,
    WindowsSandboxSetupStartParams,
    WindowsSandboxSetupStartResponse,
)
from openai_codex.models import JsonObject, Notification
from pydantic import BaseModel

from manimflow import linux_sandbox, paths
from manimflow.agent import (
    Account,
    AgentError,
    AssistantText,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    LoginFailed,
    ModelOption,
    ModelSettings,
    QuotaWindow,
)
from manimflow.model_presets import DEFAULT

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


def default_codex_home() -> Path:
    """ManimFlow's own Codex home, kept apart from any Codex the teacher installed.

    See docs/adr/0001-manimflow-has-its-own-codex-home.md.
    """
    return paths.data_dir() / "codex"


class CodexAgent:
    def __init__(
        self,
        home: Path,
        open_browser: Callable[[str], object] = webbrowser.open,
        sandbox_problem: Callable[[str], str | None] = linux_sandbox.problem,
    ) -> None:
        """`home` is the Codex home that holds ManimFlow's login, config and threads.

        `sandbox_problem` says, given the agent's PATH, why the Linux sandbox can't start.
        """
        self.home = home.absolute()
        self._open_browser = open_browser
        self._check_sandbox = sandbox_problem
        self._codex: AsyncCodex | None = None
        # Readies the sandbox in the background, so the first page doesn't wait for it.
        self._sandbox: asyncio.Task[str | None] | None = None
        self._settings = DEFAULT

    async def _client(self) -> AsyncCodex:
        if self._codex is None:
            # The app-server refuses to start when its home is missing.
            self.home.mkdir(parents=True, exist_ok=True)
            # `uvx manimflow` doesn't put its environment on PATH, and the agent
            # renders through the `manimflow` script that lives there.
            scripts = sysconfig.get_path("scripts")
            path = os.pathsep.join([scripts, os.environ.get("PATH", "")])
            env = {"CODEX_HOME": str(self.home), "PATH": path}
            codex = AsyncCodex(CodexConfig(env=env))
            await codex._ensure_initialized()
            self._codex = codex
            self._sandbox = asyncio.create_task(self._prepare_sandbox(codex, path))
        return self._codex

    async def _prepare_sandbox(self, codex: AsyncCodex, path: str) -> str | None:
        if sys.platform == "win32":
            await _set_up_windows_sandbox(codex, self.home)
        problem = await asyncio.to_thread(self._check_sandbox, path)
        if problem:
            logger.warning("Codex sandbox can't start: %s", problem)
        return problem

    async def sandbox_problem(self) -> str | None:
        """Why the agent can't run commands, for the teacher; None when it can.

        Waits until the sandbox is ready, which on Windows can take minutes the first time.
        """
        await self._client()
        assert self._sandbox is not None
        return await self._sandbox

    async def start_session(self, lesson: Path) -> "CodexSession":
        codex = await self._client()
        # A thread takes the sandbox config at its start; until setup ends, Codex
        # blocks every command in it.
        await self.sandbox_problem()
        thread = await codex.thread_start(
            cwd=str(lesson.absolute()),
            sandbox=Sandbox.workspace_write,
            approval_mode=ApprovalMode.deny_all,
            developer_instructions=BASE_INSTRUCTIONS,
            config=THREAD_CONFIG,
        )
        return CodexSession(lesson, thread, self)

    async def models(self) -> list[ModelOption]:
        codex = await self._client()
        return [
            ModelOption(
                model.model,
                model.display_name,
                tuple(option.reasoning_effort.value for option in model.supported_reasoning_efforts),
                model.default_reasoning_effort.value,
            )
            for model in (await codex.models()).data
        ]

    async def model_settings(self) -> ModelSettings:
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

    async def logout(self) -> None:
        codex = await self._client()
        await codex.logout()

    async def quota(self) -> list[QuotaWindow] | None:
        if (await self.account()).method != "chatgpt":
            return None
        codex = await self._client()
        # The SDK has no wrapper for this request.
        try:
            usage = await codex._client.request(
                "account/rateLimits/read", None, response_model=GetAccountRateLimitsResponse
            )
        except CodexError as error:
            logger.warning("Codex can't read the plan's usage: %s", error)
            return None
        limits = usage.rate_limits
        return [_quota_window(window) for window in (limits.primary, limits.secondary) if window is not None]

    async def close(self) -> None:
        if self._sandbox is not None:
            self._sandbox.cancel()
            self._sandbox = None
        if self._codex is not None:
            await self._codex.close()
            self._codex = None


def _quota_window(window: RateLimitWindow) -> QuotaWindow:
    resets_at = datetime.fromtimestamp(window.resets_at, UTC) if window.resets_at is not None else None
    return QuotaWindow(window.used_percent, window.window_duration_mins, resets_at)


async def _set_up_windows_sandbox(codex: AsyncCodex, home: Path) -> None:
    """Prepares Codex's Windows sandbox, and waits until it can enter the teacher's folders.

    See docs/adr/0003-windows-sandbox-runs-elevated.md. The SDK has no wrapper for
    these requests, so they go through its JSON-RPC client.
    """
    client = codex._client
    readiness = await client.request("windowsSandbox/readiness", None, response_model=WindowsSandboxReadinessResponse)
    if readiness.status != WindowsSandboxReadiness.ready:
        # Only the elevated mode cuts the network. It asks for administrator once;
        # without it, the unelevated mode still keeps writes inside the lesson.
        if not await _windows_sandbox_setup(client, WindowsSandboxSetupMode.elevated):
            await _windows_sandbox_setup(client, WindowsSandboxSetupMode.unelevated)
    # Codex grants the sandbox read access to the teacher's folders in a helper that
    # it starts with the first command and doesn't wait for. Until the helper ends,
    # commands start in C:\ instead of the lesson.
    params = CommandExecParams(command=["cmd", "/c", "exit"], cwd=str(home))
    await client.request(
        "command/exec", params.model_dump(mode="json", by_alias=True, exclude_none=True), response_model=CommandExecResponse
    )
    while await asyncio.to_thread(_windows_read_grants_running):
        await asyncio.sleep(1)


async def _windows_sandbox_setup(client: AsyncCodexClient, mode: WindowsSandboxSetupMode) -> bool:
    params = WindowsSandboxSetupStartParams(mode=mode)
    await client.request(
        "windowsSandbox/setupStart", params.model_dump(mode="json"), response_model=WindowsSandboxSetupStartResponse
    )
    while True:
        notification = await client.next_notification()
        if isinstance(notification.payload, WindowsSandboxSetupCompletedNotification):
            break
    if not notification.payload.success:
        # Without any mode, Codex refuses to run the agent's commands; the chat still works.
        logger.warning("Windows sandbox %s setup failed: %s", mode.value, notification.payload.error)
    return notification.payload.success


def _windows_read_grants_running() -> bool:
    """Whether Codex's helper is still granting the sandbox read access, by its mutex."""
    if sys.platform != "win32":
        return False
    synchronize = 0x00100000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenMutexW(synchronize, False, "Local\\CodexSandboxReadAcl")
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


class CodexSession:
    def __init__(self, lesson: Path, thread: AsyncThread, agent: CodexAgent) -> None:
        self.lesson = lesson
        self._thread = thread
        self._agent = agent

    async def send(self, text: str, attachments: Sequence[Path] = ()) -> AsyncIterator[Event]:
        # Every command would fail inside a sandbox that can't start, so the turn
        # would only spend quota.
        if problem := await self._agent.sandbox_problem():
            yield AgentError(problem)
            return
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
                    # A command Codex declined to run has no exit code.
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
