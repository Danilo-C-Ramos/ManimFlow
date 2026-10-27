"""Checks what rendering and the agent need and explains, in Portuguese, what is missing;
on request, installs ManimFlow's own TinyTeX first."""

import importlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from manimflow import linux_sandbox, tinytex

INSTALL_HINT = (
    "Rode `manimflow doctor --install` para instalar o TinyTeX na sua pasta de usuário, "
    "sem precisar de administrador."
)
# Import name, distribution name, and what the teacher would call it.
PYTHON_STACK = [
    ("manim", "manim", "manim"),
    ("cairo", "pycairo", "pycairo"),
    ("manimpango", "manimpango", "manimpango"),
    ("av", "av", "pyav"),
]


@dataclass
class Check:
    name: str
    ok: bool
    # For the teacher, in Portuguese.
    message: str
    path: str | None = None
    missing: list[str] = field(default_factory=list)


@dataclass
class DoctorReport:
    install: bool
    tinytex: Path
    checks: list[Check] = field(default_factory=list)
    # What --install installed this time: "TinyTeX" and package names.
    installed: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    install_output: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "command": "doctor",
            "install": self.install,
            "tinytex": str(self.tinytex),
            "checks": [asdict(check) for check in self.checks],
            "installed": self.installed,
            "duration_s": round(self.duration_s, 3),
            "errors": self.errors,
            "install_output": self.install_output,
        }


def doctor(install: bool, progress: Callable[[str], None]) -> DoctorReport:
    """Checks LaTeX, dvisvgm, Manim's LaTeX packages and the Python render stack, as the
    render subprocesses would find them, and on Linux the agent's sandbox. With `install`, first installs ManimFlow's TinyTeX
    and the packages it lacks, reporting each step to `progress`."""
    started = time.perf_counter()
    report = DoctorReport(install=install, tinytex=tinytex.root())
    if install:
        try:
            report.installed = tinytex.install(progress)
        except tinytex.InstallError as error:
            report.errors.append(str(error))
            report.install_output = error.output
    path = tinytex.search_path()
    report.checks = [
        _program("latex", "LaTeX", path, "Sem ele, fórmulas e textos (Tex, MathTex) não renderizam."),
        _program(
            "dvisvgm", "dvisvgm", path, "O Manim o usa para transformar as fórmulas do LaTeX em desenho."
        ),
        _packages(path),
        *(_module(*entry) for entry in PYTHON_STACK),
    ]
    if sys.platform.startswith("linux"):
        report.checks.append(_sandbox())
    report.duration_s = time.perf_counter() - started
    return report


def _program(name: str, label: str, path: str, why: str) -> Check:
    if found := shutil.which(name, path=path):
        return Check(name, True, f"{label} encontrado em {found}.", path=found)
    return Check(name, False, f"{label} não encontrado. {why} {INSTALL_HINT}")


def _packages(path: str) -> Check:
    files = {package: file for package, file in tinytex.PACKAGE_FILES.items() if file}
    kpsewhich = shutil.which("kpsewhich", path=path)
    found: set[str] = set()
    if kpsewhich:
        lookup = subprocess.run(
            [kpsewhich, *files.values()],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PATH": path},
        )
        found = {Path(line.strip()).name for line in lookup.stdout.splitlines()}
    missing = [package for package, file in files.items() if file not in found]
    if not missing:
        return Check("latex-packages", True, f"Os {len(files)} pacotes LaTeX que o Manim usa estão instalados.")
    return Check(
        "latex-packages",
        False,
        f"Faltam pacotes LaTeX que o Manim usa: {', '.join(missing)}. {INSTALL_HINT}",
        missing=missing,
    )


def _sandbox() -> Check:
    if problem := linux_sandbox.problem(os.environ.get("PATH", "")):
        return Check("sandbox", False, problem)
    return Check("sandbox", True, "O isolamento que mantém o agente dentro da pasta da aula abre.")


def _module(module: str, distribution: str, label: str) -> Check:
    try:
        importlib.import_module(module)
    except Exception as error:  # A broken install can fail in many ways (DLLs on Windows).
        return Check(
            label,
            False,
            f"{label} não carrega ({error}). Reinstale o ManimFlow com "
            "`uv tool install --reinstall manimflow`.",
        )
    version = importlib.metadata.version(distribution)
    return Check(label, True, f"{label} {version} carrega.")
