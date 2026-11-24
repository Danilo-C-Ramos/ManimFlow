"""The app's look: one flat blue accent over Quasar's defaults, a color per turma, and the
status dots and pills the sidebar and the cards share. See prototypes/ui-chatgpt on `main`."""

from importlib.resources import files

from nicegui import ui

from manimflow.lessons import Status, Turma

ACCENT = "#1d64d8"
_CSS = (files("manimflow") / "theme.css").read_text(encoding="utf-8")

# Text and background of each status, and the label "the agent is working" takes over.
_STATUS_COLORS = {
    Status.NEW: ("#475569", "#eef2f6"),
    Status.PLAN: ("#a35400", "#fff1d6"),
    Status.IN_PROGRESS: ("#1d64d8", "#e7effc"),
    Status.READY: ("#137a3a", "#e3f5ea"),
    Status.EXPORTED: ("#6d28d9", "#f1eafd"),
}
WORKING = "Trabalhando"


def apply_theme() -> None:
    """Gives the current page the app's look; call it first on every page."""
    ui.colors(primary=ACCENT, secondary="#475569", positive="#16a34a", negative="#dc2626", warning="#d97706")
    ui.add_css(_CSS)


def status_dot(status: Status, working: bool = False) -> None:
    """A small dot in the status's color, or a spinner while the agent works."""
    if working:
        ui.spinner(size="12px", color="primary").classes("flex-none").tooltip(WORKING)
        return
    color, _ = _STATUS_COLORS[status]
    ui.element("span").classes("mf-dot").style(f"background:{color}").tooltip(status.value)


def status_pill(status: Status, working: bool = False) -> None:
    """The status as a colored pill, such as "● Pronta"."""
    if working:
        with ui.row().classes("mf-pill items-center gap-1").style("color:#1d64d8;background:#e7effc"):
            ui.spinner(size="10px", color="primary")
            ui.label(WORKING)
        return
    color, background = _STATUS_COLORS[status]
    with ui.row().classes("mf-pill items-center gap-1").style(f"color:{color};background:{background}"):
        ui.label("●").classes("text-[9px]")
        ui.label(status.value)


def turma_badge(turma: Turma | None, size: int = 22) -> None:
    """The turma's first letter on its color, as the sidebar and the cards show it."""
    if turma is None:
        return
    initial = (turma.name[:1] or "?").upper()
    ui.label(initial).classes("mf-badge").style(
        f"background:{turma.color}1f;color:{turma.color};width:{size}px;height:{size}px"
    )
