"""Checks that Codex's Linux sandbox can start, and explains in Portuguese how to fix it.

Codex runs every agent command inside bubblewrap: the `bwrap` on the PATH, or else the
one bundled with Codex. Ubuntu 23.10 and later restrict user namespaces to programs
with an AppArmor profile, so there bubblewrap fails before any command runs. See
docs/adr/0002-linux-sandbox-on-ubuntu-uses-an-apparmor-profile.md.
"""

import shlex
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import codex_cli_bin

PROFILE = Path(str(files("manimflow") / "apparmor" / "manimflow-bwrap"))
RESTRICT_SYSCTL = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")


def fix_command() -> str:
    """What the teacher runs once, as administrator, to let the sandbox start."""
    return (
        f"sudo apt install bubblewrap && sudo cp {shlex.quote(str(PROFILE))} /etc/apparmor.d/ "
        "&& sudo apparmor_parser -r /etc/apparmor.d/manimflow-bwrap"
    )


def problem(path: str) -> str | None:
    """Why the sandbox can't start with this PATH, for the teacher; None when it starts,
    and always None outside Linux."""
    if not sys.platform.startswith("linux"):
        return None
    bwrap = shutil.which("bwrap", path=path) or str(codex_cli_bin.bundled_package_dir() / "codex-resources" / "bwrap")
    # The namespaces Codex asks for: a sandbox with no network needs its own.
    try:
        run = subprocess.run(
            [bwrap, "--unshare-all", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        details = str(error)
    else:
        if run.returncode == 0:
            return None
        details = run.stderr.strip()
    if _restricted():
        return (
            "O Ubuntu bloqueia o isolamento que o agente usa para só mexer na pasta da aula, "
            "então ele não consegue rodar nenhum comando. Para liberar só esse isolamento, "
            f"rode uma vez no terminal: {fix_command()}"
        )
    return f"O isolamento que o agente usa para só mexer na pasta da aula não abriu ({details})."


def _restricted() -> bool:
    try:
        return RESTRICT_SYSCTL.read_text().strip() == "1"
    except OSError:
        return False
