"""The `Agent` interface on top of Codex, through the official `openai-codex` SDK.

The SDK starts the bundled Codex app-server once and keeps it for the app's
lifetime. A lesson's conversation is a Codex thread rooted in the lesson folder,
with the ManimFlow base instructions and skill, a sandbox that only writes inside
the lesson, no network and no approval prompts. Every message continues the
lesson's newest thread (see docs/adr/0005-a-lesson-has-one-conversation.md).
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

from openai_codex import (
    ApprovalMode,
    AsyncCodex,
    AsyncThread,
    CodexConfig,
    CodexError,
    InputItem,
    Sandbox,
    SkillInput,
    TextInput,
)
from openai_codex.api import AsyncTurnHandle
from openai_codex.async_client import AsyncCodexClient
from openai_codex.generated.v2_all import (
    AddPatchChangeKind,
    AgentMessageThreadItem,
    ContextCompactionThreadItem,
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
    ImageViewThreadItem,
    ItemCompletedNotification,
    ItemStartedNotification,
    ListFilesCommandAction,
    PatchApplyStatus,
    RateLimitWindow,
    ReadCommandAction,
    ReasoningEffort,
    ReasoningThreadItem,
    SearchCommandAction,
    SortDirection,
    TextUserInput,
    ThreadListCwdFilter,
    ThreadSortKey,
    Turn,
    TurnCompletedNotification,
    TurnPlanUpdatedNotification,
    TurnStatus,
    UserMessageThreadItem,
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
    Checklist,
    ChecklistStep,
    CommandFinished,
    CommandStarted,
    Event,
    FileChanged,
    ImageViewed,
    LoginFailed,
    ModelOption,
    ModelSettings,
    PastTurn,
    QuotaWindow,
    Working,
    teachers_words,
    with_attachments,
)
from manimflow.model_presets import QUICK, choose_model, presets

logger = logging.getLogger(__name__)

BASE_INSTRUCTIONS = (files("manimflow") / "agent_instructions.md").read_text(encoding="utf-8")
# How to use the manimflow CLI and the self-check loop, as a Codex skill.
SKILL_NAME = "manimflow"
SKILL = files("manimflow") / "skills" / SKILL_NAME / "SKILL.md"

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
        sessions: bool = True,
    ) -> None:
        """`home` is the Codex home that holds ManimFlow's login, config and threads.

        `sandbox_problem` says, given the agent's PATH, why the Linux sandbox can't start.
        Without `sessions`, the agent only reads the account and its models, and never
        readies the sandbox, which on Windows may ask for administrator.
        """
        self.home = home.absolute()
        self._open_browser = open_browser
        self._check_sandbox = sandbox_problem
        self._sessions = sessions
        self._codex: AsyncCodex | None = None
        # Readies the sandbox in the background, so the first page doesn't wait for it.
        self._sandbox: asyncio.Task[str | None] | None = None
        # The switch's position, read on the account's model at each turn.
        self._preset = QUICK
        # A pick in "Avançado", which takes over from the switch until the next sign-in.
        self._settings: ModelSettings | None = None
        # Counts sign-ins and sign-outs, so a read that spans one is read again.
        self._account_changes = 0

    async def _client(self) -> AsyncCodex:
        if self._codex is None:
            # The app-server refuses to start when its home is missing.
            self.home.mkdir(parents=True, exist_ok=True)
            if self._sessions:
                self._install_skill()
            # `uvx manimflow` doesn't put its environment on PATH, and the agent
            # renders through the `manimflow` script that lives there.
            scripts = sysconfig.get_path("scripts")
            path = os.pathsep.join([scripts, os.environ.get("PATH", "")])
            env = {"CODEX_HOME": str(self.home), "PATH": path}
            codex = AsyncCodex(CodexConfig(env=env))
            await codex._ensure_initialized()
            self._codex = codex
            if self._sessions:
                self._sandbox = asyncio.create_task(self._prepare_sandbox(codex, path))
        return self._codex

    @property
    def skill(self) -> Path:
        """Where the skill lives in the Codex home; Codex only loads skills from its skill folders."""
        return self.home / "skills" / SKILL_NAME / "SKILL.md"

    def _install_skill(self) -> None:
        # Rewritten on every start, so an upgraded ManimFlow brings its skill along.
        self.skill.parent.mkdir(parents=True, exist_ok=True)
        self.skill.write_text(SKILL.read_text(encoding="utf-8"), encoding="utf-8")

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
        assert self._sandbox is not None, "an agent started without sessions has no sandbox"
        return await self._sandbox

    async def session(self, lesson: Path) -> "CodexSession":
        """Continues the lesson's newest thread in which the teacher wrote; the first
        message starts one when the lesson has none."""
        threads = await self._threads(lesson)
        return CodexSession(lesson, self, threads[0] if threads else None)

    async def _thread(self, lesson: Path, thread_id: str | None) -> AsyncThread:
        """The thread `thread_id`, resumed, or a new one when None; each with this
        ManimFlow's instructions and sandbox."""
        codex = await self._client()
        # A thread takes the sandbox config at its start; until setup ends, Codex
        # blocks every command in it.
        await self.sandbox_problem()
        cwd = str(lesson.absolute())
        if thread_id is None:
            return await codex.thread_start(
                cwd=cwd,
                sandbox=Sandbox.workspace_write,
                approval_mode=ApprovalMode.deny_all,
                developer_instructions=BASE_INSTRUCTIONS,
                config=THREAD_CONFIG,
            )
        # The instructions are given again, so an upgraded ManimFlow brings its own.
        return await codex.thread_resume(
            thread_id,
            cwd=cwd,
            sandbox=Sandbox.workspace_write,
            approval_mode=ApprovalMode.deny_all,
            developer_instructions=BASE_INSTRUCTIONS,
            config=THREAD_CONFIG,
        )

    async def _threads(self, lesson: Path) -> list[str]:
        """The lesson's threads, found by the folder they started in, in which the
        teacher wrote; newest first."""
        codex = await self._client()
        threads: list[str] = []
        cursor: str | None = None
        while True:
            page = await codex.thread_list(
                cwd=ThreadListCwdFilter(str(lesson.absolute())),
                cursor=cursor,
                sort_key=ThreadSortKey.created_at,
                sort_direction=SortDirection.desc,
            )
            # A thread's preview is its first message; a thread without one never got a request.
            threads += [thread.id for thread in page.data if thread.preview]
            if page.next_cursor is None:
                return threads
            cursor = page.next_cursor

    async def lesson_history(self, lesson: Path) -> list[PastTurn]:
        codex = await self._client()
        turns: list[PastTurn] = []
        for thread in reversed(await self._threads(lesson)):
            read = (await AsyncThread(codex, thread).read(include_turns=True)).thread
            turns += [_past_turn(thread, turn, lesson) for turn in read.turns]
        return turns

    async def archive(self, lesson: Path) -> None:
        """Puts away the lesson's threads, so its conversation starts over; used when the
        lesson's files start over, as the example's do."""
        codex = await self._client()
        for thread in await self._threads(lesson):
            await codex.thread_archive(thread)

    async def models(self) -> list[ModelOption]:
        codex = await self._client()
        return [
            ModelOption(
                model.model,
                model.display_name,
                tuple(option.reasoning_effort.value for option in model.supported_reasoning_efforts),
                model.default_reasoning_effort.value,
                model.is_default,
            )
            for model in (await codex.models()).data
        ]

    async def presets(self) -> dict[str, ModelSettings]:
        """On the model `choose_model` picks from the account's plan and from the
        catalog the app-server fetches with the account's sign-in.

        Read fresh each time, since another tab may sign in with another plan.
        """
        account = await self.account()
        return presets(choose_model(account.plan, await self.models()))

    async def model_settings(self) -> ModelSettings:
        while True:
            changes = self._account_changes
            settings = self._settings or (await self.presets())[self._preset]
            if changes == self._account_changes:
                return settings

    async def set_model_settings(self, settings: ModelSettings) -> None:
        """Applies from the next turn on, in every session."""
        self._settings = settings

    async def use_preset(self, name: str) -> None:
        self._preset = name
        self._settings = None

    def _forget_model_choice(self) -> None:
        """For another account, whose plan may not include the model picked before."""
        self._settings = None
        self._account_changes += 1

    async def account(self) -> Account:
        codex = await self._client()
        state = await codex.account()
        match state.account.root if state.account else None:
            case ApiKeyAccount():
                return Account(logged_in=True, method="api_key")
            case ChatgptAccount(email=email, plan_type=plan):
                return Account(logged_in=True, method="chatgpt", email=email, plan=plan.value)
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
            return await self._signed_in()

        # Codex listens on a 127.0.0.1 loopback port for the browser's redirect.
        attempt = await codex.login_chatgpt()
        await asyncio.to_thread(self._open_browser, attempt.auth_url)
        outcome = await attempt.wait()
        if not outcome.success:
            logger.warning("ChatGPT login failed: %s", outcome.error)
            raise LoginFailed("O login com o ChatGPT não foi concluído. Tente de novo.")
        return await self._signed_in()

    async def _signed_in(self) -> Account:
        # Once the login ends: a choice made while it waited belongs to the account before.
        self._forget_model_choice()
        return await self.account()

    async def logout(self) -> None:
        codex = await self._client()
        await codex.logout()
        self._forget_model_choice()

    async def quota(self) -> list[QuotaWindow] | None:
        if (await self.account()).method != "chatgpt":
            return None
        codex = await self._client()
        try:
            usage = await _rpc(codex).request(
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


def _rpc(codex: AsyncCodex) -> AsyncCodexClient:
    """The SDK's JSON-RPC client, for the app-server requests the SDK has no wrapper for."""
    return codex._client


def _quota_window(window: RateLimitWindow) -> QuotaWindow:
    resets_at = datetime.fromtimestamp(window.resets_at, UTC) if window.resets_at is not None else None
    return QuotaWindow(window.used_percent, window.window_duration_mins, resets_at)


async def _set_up_windows_sandbox(codex: AsyncCodex, home: Path) -> None:
    """Prepares Codex's Windows sandbox, and waits until it can enter the teacher's folders.

    See docs/adr/0003-windows-sandbox-runs-elevated.md.
    """
    client = _rpc(codex)
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
    def __init__(self, lesson: Path, agent: CodexAgent, thread_id: str | None) -> None:
        self.lesson = lesson
        self._agent = agent
        # None until the first message starts the lesson's first thread.
        self._thread_id = thread_id
        self._thread: AsyncThread | None = None
        # A thread that already ran turns has the skill in its history.
        self._has_skill = thread_id is not None
        self._turn: AsyncTurnHandle | None = None
        self._last_turn: str | None = None
        # "Parar" may come before the turn exists, while the thread starts or resumes.
        self._stopping = False

    @property
    def last_turn(self) -> str | None:
        return self._last_turn

    async def send(
        self, text: str, attachments: Sequence[Path] = (), output_schema: dict | None = None
    ) -> AsyncIterator[Event]:
        # Every command would fail inside a sandbox that can't start, so the turn
        # would only spend quota.
        self._last_turn = None
        self._stopping = False
        if problem := await self._agent.sandbox_problem():
            yield AgentError(problem, delivered=False)
            return
        settings = await self._agent.model_settings()
        if self._thread is None:
            self._thread = await self._agent._thread(self.lesson, self._thread_id)
            self._thread_id = self._thread.id
        message: list[InputItem] = [TextInput(with_attachments(text, attachments))]
        if not self._has_skill:
            # Codex puts the skill's text into the thread itself, so the agent has it
            # without reading the file, and later turns keep it in the history.
            message.insert(0, SkillInput(SKILL_NAME, str(self._agent.skill)))
        if self._stopping:
            yield AgentError(_INTERRUPTED, delivered=False)
            return
        handle = await self._thread.turn(
            message, model=settings.model, effort=ReasoningEffort(settings.effort), output_schema=output_schema
        )
        self._has_skill = True
        self._turn = handle
        self._last_turn = handle.id
        try:
            if self._stopping:
                await self.stop()
            async for notification in handle.stream():
                for event in _events(notification, self.lesson):
                    if isinstance(event, AgentError) and event.message == _TOO_LONG:
                        # Codex couldn't shrink the conversation; the next message starts
                        # a new thread, and CONTEXTO.md carries the lesson over.
                        self._thread = self._thread_id = None
                        self._has_skill = False
                    yield event
        finally:
            self._turn = None

    async def stop(self) -> None:
        self._stopping = True
        if self._turn is not None:
            try:
                await self._turn.interrupt()
            except Exception:
                # The turn may have just ended; it reports how it ends either way.
                logger.warning("Codex couldn't interrupt the turn", exc_info=True)


def _past_turn(thread: str, turn: Turn, lesson: Path) -> PastTurn:
    """A turn of an earlier conversation, with the events the chat showed when it ran."""
    request = ""
    events: list[Event] = []
    for item in turn.items:
        match item.root:
            case UserMessageThreadItem(content=content):
                text = "\n\n".join(part.root.text for part in content if isinstance(part.root, TextUserInput))
                request = teachers_words(text)
            case AgentMessageThreadItem(text=text):
                events.append(AssistantText(text))
            case CommandExecutionThreadItem() as run:
                started = _command_started(run, lesson)
                exit_code = run.exit_code if run.exit_code is not None else -1
                events += [started, CommandFinished(run.id, started.command, exit_code)]
            case FileChangeThreadItem(status=PatchApplyStatus.completed, changes=changes):
                events += [_file_changed(change, lesson) for change in changes]
            case ImageViewThreadItem(path=path):
                events.append(ImageViewed(_shown(path.root, lesson)))
    if turn.status not in (TurnStatus.completed, TurnStatus.in_progress):
        events.append(_turn_failed(turn))
    started_at = datetime.fromtimestamp(turn.started_at, UTC) if turn.started_at is not None else None
    seconds = turn.duration_ms / 1000 if turn.duration_ms is not None else None
    if seconds is None and turn.started_at is not None and turn.completed_at is not None:
        seconds = turn.completed_at - turn.started_at
    return PastTurn(turn.id, thread, started_at, request, events, seconds)


def _events(notification: Notification, lesson: Path) -> list[Event]:
    """Translates one app-server notification into the interface's events."""
    match notification.payload:
        case ItemStartedNotification(item=item):
            match item.root:
                case CommandExecutionThreadItem() as run:
                    return [_command_started(run, lesson)]
                case ReasoningThreadItem():
                    return [Working("Pensando")]
                case AgentMessageThreadItem():
                    return [Working("Escrevendo a resposta")]
                case ContextCompactionThreadItem():
                    return [Working("Resumindo a conversa para continuar")]
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
                case ImageViewThreadItem(path=path):
                    return [ImageViewed(_shown(path.root, lesson))]
        case TurnPlanUpdatedNotification(plan=plan):
            return [Checklist(tuple(ChecklistStep(step.step, step.status.value) for step in plan))]
        case TurnCompletedNotification(turn=turn) if turn.status != TurnStatus.completed:
            return [_turn_failed(turn)]
    return []


def _command_started(run: CommandExecutionThreadItem, lesson: Path) -> CommandStarted:
    """The command, with the files it only reads when Codex could tell."""
    actions = [action.root for action in run.command_actions]
    reads: tuple[str, ...] = ()
    if actions and all(isinstance(action, ReadCommandAction) for action in actions):
        reads = tuple(_shown(action.path.root, lesson) for action in actions if isinstance(action, ReadCommandAction))
    elif actions and all(isinstance(action, (ListFilesCommandAction, SearchCommandAction)) for action in actions):
        reads = (".",)
    return CommandStarted(run.id, _command(run), reads)


def _command(run: CommandExecutionThreadItem) -> str:
    """The command as the agent wrote it, without the shell that Codex wraps it in."""
    if len(run.command_actions) == 1:
        return run.command_actions[0].root.command
    return run.command


def _shown(path: str, lesson: Path) -> str:
    """A path as the teacher reads it: relative to the lesson when inside it."""
    resolved = Path(path).resolve()
    if resolved.is_relative_to(lesson.resolve()):
        return resolved.relative_to(lesson.resolve()).as_posix()
    return str(resolved)


def _file_changed(change: FileUpdateChange, lesson: Path) -> FileChanged:
    shown = _shown(change.path, lesson)
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
_INTERRUPTED = "A resposta foi interrompida antes de terminar."
_TOO_LONG = (
    "A conversa ficou longa demais para o agente. Mande o pedido de novo: ele continua numa "
    "conversa nova, com o que está registrado no CONTEXTO.md."
)

_EXPLANATIONS = {
    CodexErrorInfoValue.usage_limit_exceeded: "Você atingiu o limite de uso do seu plano. Tente de novo mais tarde.",
    CodexErrorInfoValue.rate_limit_exceeded: _TOO_MANY_REQUESTS,
    CodexErrorInfoValue.unauthorized: _LOGIN_REFUSED,
    CodexErrorInfoValue.context_window_exceeded: _TOO_LONG,
    CodexErrorInfoValue.internal_server_error: _SERVICE_UNSTABLE,
    CodexErrorInfoValue.server_overloaded: _SERVICE_UNSTABLE,
    # Such as a model picked in "Avançado" that the plan doesn't include.
    CodexErrorInfoValue.model_not_found: (
        'O seu plano não inclui esse modelo. Escolha outro em Configurações, na parte "Avançado".'
    ),
}


def _turn_failed(turn: Turn) -> AgentError:
    """Explains a failed or interrupted turn to the teacher; Codex's own message is in English."""
    if turn.status == TurnStatus.interrupted:
        return AgentError(_INTERRUPTED)
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
