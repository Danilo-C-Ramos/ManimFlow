"""The "Rápido / Caprichado" switch: the account's model at two reasoning efforts.

Which model each ChatGPT plan gets, and why: docs/models.md.
"""

from collections.abc import Sequence

from manimflow.agent import ModelOption, ModelSettings

# The switch's labels, which the teacher reads.
QUICK = "Rápido"
CAREFUL = "Caprichado"
EFFORTS = {QUICK: "low", CAREFUL: "high"}

# Tried in order: the switch uses the first one the account's catalog lists.
MODELS = ("gpt-6.2-sol", "gpt-6.1-sol")
# ChatGPT Free and Go only get GPT-6 Luna in Codex.
LIMITED_PLANS = frozenset({"free", "go"})
LIMITED_MODELS = ("gpt-6-luna",)


def choose_model(plan: str | None, catalog: Sequence[ModelOption]) -> ModelOption:
    """The model for the switch, given the ChatGPT plan (None with an API key) and the account's catalog.

    A catalog without any of the plan's models gets its own default, as Codex would pick.
    """
    wanted = LIMITED_MODELS if plan in LIMITED_PLANS else MODELS
    listed = {option.model: option for option in catalog}
    for model in wanted:
        if model in listed:
            return listed[model]
    fallback = next((option for option in catalog if option.default), catalog[0] if catalog else None)
    # Without a catalog, the efforts are unknown and the switch asks for its own.
    return fallback or ModelOption(wanted[0], wanted[0], (), EFFORTS[QUICK])


def presets(option: ModelOption) -> dict[str, ModelSettings]:
    """The switch's positions on `option`; an effort the model lacks becomes its default."""

    def accepted(effort: str) -> str:
        return effort if effort in option.efforts or not option.efforts else option.default_effort

    return {name: ModelSettings(option.model, accepted(effort)) for name, effort in EFFORTS.items()}


def preset_name(presets: dict[str, ModelSettings], settings: ModelSettings) -> str | None:
    """The switch position for `settings`; None when they were picked in "Avançado"."""
    return next((name for name, preset in presets.items() if preset == settings), None)
