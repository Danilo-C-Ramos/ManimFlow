"""The "Rápido / Caprichado" switch: one fixed model at two reasoning efforts.

Why this model and these efforts: docs/models.md.
"""

from manimflow.agent import ModelSettings

MODEL = "gpt-6.1-sol"
QUICK = ModelSettings(MODEL, "low")
CAREFUL = ModelSettings(MODEL, "high")
DEFAULT = QUICK

# The switch's labels, which the teacher reads.
PRESETS = {"Rápido": QUICK, "Caprichado": CAREFUL}


def preset_name(settings: ModelSettings) -> str | None:
    """The switch position for `settings`; None when they were picked in "Avançado"."""
    return next((name for name, preset in PRESETS.items() if preset == settings), None)
