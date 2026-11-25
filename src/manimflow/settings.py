"""The agent's settings: the "Rápido / Caprichado" switch on the lesson screen, and the
settings dialog one click away with "Avançado". Every UI string is in Portuguese."""

import logging
from collections.abc import Callable
from datetime import datetime

from nicegui import events, ui

from manimflow.agent import Account, Agent, ModelOption, ModelSettings, QuotaWindow
from manimflow.model_presets import CAREFUL, QUICK, preset_name

logger = logging.getLogger(__name__)

EFFORTS = {
    "none": "Nenhum",
    "minimal": "Mínimo",
    "low": "Baixo",
    "medium": "Médio",
    "high": "Alto",
    "xhigh": "Muito alto",
    "max": "Máximo",
    "ultra": "Ultra",
}


class ModelSwitch:
    """Switches the agent between the two presets, on the account's model; from the next turn on.

    `position` is the preset the agent runs on, or None for a pick in "Avançado".
    """

    def __init__(self, agent: Agent, position: str | None) -> None:
        self.agent = agent
        self.toggle = ui.toggle([QUICK, CAREFUL], value=position, on_change=self._changed)
        self.toggle.props("dense no-caps").mark("preset")

    def show(self, presets: dict[str, ModelSettings], settings: ModelSettings) -> None:
        """Moves the switch to `settings` among `presets`, or to neither when they match none."""
        self.toggle.set_value(preset_name(presets, settings))

    async def _changed(self, event: events.ValueChangeEventArguments) -> None:
        # None when the teacher picked a model in "Avançado". The agent reads the
        # position on the account's model when the turn starts, so nothing waits here.
        if event.value is not None:
            await self.agent.use_preset(event.value)


async def model_switch(agent: Agent) -> ModelSwitch:
    return ModelSwitch(agent, preset_name(await agent.presets(), await agent.model_settings()))


class SettingsDialog:
    """The settings, read fresh from the agent each time they open; with `button`, a gear
    button that opens them. `switch` follows a model picked in "Avançado"."""

    def __init__(
        self, agent: Agent, switch: ModelSwitch | None, on_signed_out: Callable[[], None], button: bool = True
    ) -> None:
        self.agent = agent
        self.switch = switch
        self.on_signed_out = on_signed_out
        self.dialog = ui.dialog()
        if button:
            ui.button(icon="settings", on_click=self.open).props("flat round dense color=grey-7").tooltip("Configurações").mark(
                "open-settings"
            )

    async def open(self) -> None:
        account = await self.agent.account()
        settings = await self.agent.model_settings()
        models = await self.agent.models()
        presets = await self.agent.presets()
        quota = await self.agent.quota()
        self.dialog.clear()
        with self.dialog, ui.card().classes("w-full max-w-lg items-stretch gap-4"):
            ui.label("Configurações").classes("text-lg")
            with ui.row().classes("items-center no-wrap"):
                with ui.column().classes("grow gap-0"):
                    ui.label(_signed_in_as(account))
                    ui.label(_presets_use(presets, models)).classes("text-caption text-grey-7")
                ui.button("Sair", on_click=self._sign_out).props("outline")
            if quota:
                with ui.column().classes("w-full gap-2").mark("quota"):
                    ui.label("Uso do plano do ChatGPT").classes("text-subtitle1")
                    for window in quota:
                        _quota_row(window)
            with ui.expansion("Avançado", icon="tune").classes("text-grey-8"):
                AdvancedSettings(self.agent, models, presets, settings, self.switch)
            ui.button("Fechar", on_click=self.dialog.close).props("flat").classes("self-end")
        self.dialog.open()

    async def _sign_out(self) -> None:
        try:
            await self.agent.logout()
        except Exception:
            logger.exception("Logout failed")
            ui.notify("Não foi possível sair agora. Tente de novo.", type="negative")
            return
        self.dialog.close()
        self.on_signed_out()


# The ChatGPT plans as OpenAI names them to teachers; any other shows as Codex names it.
PLANS = {
    "free": "Free",
    "go": "Go",
    "plus": "Plus",
    "pro": "Pro",
    "prolite": "Pro Lite",
    "promax": "Pro Max",
    "team": "Business",
    "business": "Business",
    "enterprise": "Enterprise",
    "edu": "Edu",
}


def _signed_in_as(account: Account) -> str:
    match account.method:
        case "chatgpt":
            chatgpt = "Conectado com o ChatGPT"
            if account.plan and account.plan != "unknown":
                chatgpt += f" (plano {PLANS.get(account.plan, account.plan.replace('_', ' ').title())})"
            return f"{chatgpt}: {account.email}" if account.email else chatgpt
        case "api_key":
            return "Conectado com uma chave de API da OpenAI"
    # A provider configured without OpenAI auth, such as a local model.
    return "Conectado"


def _presets_use(presets: dict[str, ModelSettings], models: list[ModelOption]) -> str:
    """Which model the switch runs on, by the name the catalog gives it."""
    model = presets[QUICK].model
    name = next((option.name for option in models if option.model == model), model)
    return f"Rápido e Caprichado usam o {name}."


class AdvancedSettings:
    """Picks the model and the reasoning effort by hand, among those the account offers."""

    def __init__(
        self,
        agent: Agent,
        models: list[ModelOption],
        presets: dict[str, ModelSettings],
        current: ModelSettings,
        switch: ModelSwitch | None,
    ) -> None:
        self.agent = agent
        # The account's presets as the dialog opened, which the switch matches a pick against.
        self.presets = presets
        self.switch = switch
        self.models = {option.model: option for option in models}
        # Keeps the current model pickable when the account's list lacks it.
        self.models.setdefault(current.model, ModelOption(current.model, current.model, (), current.effort))
        self.model = ui.select(
            {model: option.name for model, option in self.models.items()},
            value=current.model,
            label="Modelo",
            on_change=self._model_changed,
        ).mark("model")
        self.effort = ui.select(
            self._efforts(current.model, current.effort),
            value=current.effort,
            label="Esforço de raciocínio",
            on_change=self._apply,
        ).mark("effort")

    def _efforts(self, model: str, effort: str) -> dict[str, str]:
        """The model's efforts with their labels, `effort` included."""
        efforts = list(self.models[model].efforts)
        if effort not in efforts:
            efforts.append(effort)
        return {effort: EFFORTS.get(effort, effort) for effort in efforts}

    async def _model_changed(self) -> None:
        option = self.models[self.model.value]
        effort = self.effort.value if self.effort.value in option.efforts else option.default_effort
        self.effort.set_options(self._efforts(option.model, effort), value=effort)
        await self._apply()

    async def _apply(self) -> None:
        settings = ModelSettings(self.model.value, self.effort.value)
        await self.agent.set_model_settings(settings)
        if self.switch is not None:
            self.switch.show(self.presets, settings)


def _quota_row(window: QuotaWindow) -> None:
    with ui.column().classes("w-full gap-1"):
        with ui.row().classes("w-full items-baseline justify-between"):
            ui.label(f"{_limit_name(window.minutes)}: {window.used_percent}% usado")
            if window.resets_at is not None:
                ui.label(renews(window.resets_at)).classes("text-caption text-grey-7")
        color = "negative" if window.used_percent >= 90 else "primary"
        ui.linear_progress(window.used_percent / 100, show_value=False, color=color)


def _limit_name(minutes: int | None) -> str:
    match minutes:
        case None:
            return "Limite de uso"
        case 1440:
            return "Limite diário"
        case 10080:
            return "Limite semanal"
        case _ if minutes % 1440 == 0:
            return f"Limite de {minutes // 1440} dias"
        case 60:
            return "Limite de 1 hora"
        case _ if minutes % 60 == 0:
            return f"Limite de {minutes // 60} horas"
    return f"Limite de {minutes} minutos"


def renews(when: datetime) -> str:
    """When a usage limit starts over, such as "renova às 14:30"."""
    local = when.astimezone()
    if local.date() == datetime.now().astimezone().date():
        return f"renova às {local:%H:%M}"
    return f"renova em {local:%d/%m} às {local:%H:%M}"
