"""ManimFlow's own TinyTeX: where it lives, how render subprocesses find it, and how
`manimflow doctor --install` puts it there."""

import lzma
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

# The same daily build TinyTeX's own installers download. An older build can't install
# packages once CTAN moves on to the next TeX Live year.
DOWNLOAD_URL = "https://github.com/rstudio/tinytex-releases/releases/download/daily/{}"

# Manim's documented LaTeX package list (docs.manim.community, installation), without
# `ms`, which TeX Live retired. Each maps to a file the package installs, which
# kpsewhich finds whatever the TeX distribution, or to None for dvisvgm, a program
# checked on its own.
PACKAGE_FILES: dict[str, str | None] = {
    "standalone": "standalone.cls",
    "preview": "preview.sty",
    "doublestroke": "dsfont.sty",
    "setspace": "setspace.sty",
    "rsfs": "rsfs10.tfm",
    "relsize": "relsize.sty",
    "ragged2e": "ragged2e.sty",
    "fundus-calligra": "calligra.sty",
    "microtype": "microtype.sty",
    "wasysym": "wasysym.sty",
    "physics": "physics.sty",
    "dvisvgm": None,
    "jknapltx": "mathrsfs.sty",
    "wasy": "wasy10.tfm",
    "cm-super": "sfrm1000.pfb",
    "babel-english": "english.ldf",
    "gnu-freefont": "FreeSerif.otf",
    "mathastext": "mathastext.sty",
    "cbfonts-fd": "lgrcmr.fd",
}


def data_dir() -> Path:
    """ManimFlow's per-user data folder."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        # TeX Live breaks on paths with spaces or non-ASCII characters, common in Windows
        # user names ("José da Silva"). TinyTeX's own installer falls back the same way.
        if not re.fullmatch(r"[!-~]+", local):
            local = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(local) / "ManimFlow"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "manimflow"


def root() -> Path:
    """Where ManimFlow's TinyTeX is, or goes."""
    return data_dir() / "TinyTeX"


def bin_dir() -> Path | None:
    """The folder with ManimFlow's TinyTeX programs, or None when it isn't installed."""
    for folder in sorted((root() / "bin").glob("*")):
        if shutil.which("tlmgr", path=str(folder)):
            return folder
    return None


def search_path() -> str:
    """The PATH render subprocesses get: ManimFlow's TinyTeX first, when it is installed, then
    the user's own. Only those subprocesses see it, so other tools (Anaconda among them)
    keep their own LaTeX, or none."""
    path = os.environ.get("PATH", "")
    folder = bin_dir()
    return f"{folder}{os.pathsep}{path}" if folder else path


class InstallError(Exception):
    """Why the install stopped, in Portuguese for the teacher; `output` is what the failed
    program printed."""

    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


def install(progress: Callable[[str], None]) -> list[str]:
    """Installs TinyTeX and those of Manim's LaTeX packages that are missing, reporting each
    step to `progress` in Portuguese. Returns what it installed: nothing when all of it was
    already there. Never touches the system PATH."""
    installed = []
    if bin_dir() is None:
        _download(progress)
        installed.append("TinyTeX")
    folder = bin_dir()
    if folder is None:
        raise InstallError(f"O TinyTeX baixado não tem o tlmgr em {root() / 'bin'}.")
    present = set(_tlmgr(folder, "info", "--list", "--only-installed", "--data", "name").split())
    missing = [package for package in PACKAGE_FILES if package not in present]
    if missing:
        progress(f"Instalando pacotes LaTeX: {', '.join(missing)}...")
        _tlmgr(folder, "update", "--self")
        _tlmgr(folder, "install", *missing)
        installed += missing
    return installed


def _bundle() -> str | None:
    """The name of this platform's TinyTeX-1 bundle, or None if there is no prebuilt one.
    Windows is what teachers use; Linux is what CI also runs on."""
    if sys.platform == "win32":
        return "TinyTeX-1-windows.exe"
    if sys.platform == "linux" and platform.machine().lower() in ("x86_64", "amd64"):
        return "TinyTeX-1-linux-x86_64.tar.xz"
    return None


def _download(progress: Callable[[str], None]) -> None:
    name = _bundle()
    if name is None:
        raise InstallError(
            f"Não há TinyTeX pronto para este sistema ({platform.system()} {platform.machine()}). "
            "Instale uma distribuição LaTeX por conta própria e rode `manimflow doctor` de novo."
        )
    url = DOWNLOAD_URL.format(name)
    target = root()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Unpacked next to the target, so moving it there is a rename, and a download that stops
    # halfway never looks installed.
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        bundle = Path(staging) / name
        progress(f"Baixando o TinyTeX (cerca de 70 MB) de {url}...")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, bundle.open("wb") as file:
                shutil.copyfileobj(response, file)
        except OSError as error:
            raise InstallError(
                f"Não foi possível baixar o TinyTeX de {url} ({error}). "
                "Verifique a conexão com a internet e rode de novo."
            ) from error
        progress("Descompactando o TinyTeX...")
        unpacked = Path(staging) / "unpacked"
        unpacked.mkdir()
        try:
            folder = _unpack(bundle, unpacked)
            # What a failed install left behind.
            shutil.rmtree(target, ignore_errors=True)
            folder.rename(target)
        except (OSError, EOFError, ValueError, tarfile.TarError, lzma.LZMAError) as error:
            raise InstallError(
                f"Não foi possível descompactar o TinyTeX em {target} ({error}). "
                "Feche programas que possam estar usando essa pasta e rode de novo."
            ) from error


def _unpack(bundle: Path, into: Path) -> Path:
    """Unpacks a TinyTeX bundle into the empty folder `into`; returns the TinyTeX folder."""
    if bundle.suffix == ".exe":
        # A self-extracting 7-Zip archive. Without -o it writes next to itself, not
        # where it runs.
        extract = subprocess.run(
            [str(bundle), "-y", f"-o{into}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if extract.returncode != 0:
            raise InstallError("Não foi possível descompactar o TinyTeX.", extract.stdout + extract.stderr)
    else:
        with tarfile.open(bundle) as archive:
            archive.extractall(into, filter="data")
    # A single folder: TinyTeX on Windows, .TinyTeX on Linux.
    (folder,) = into.iterdir()
    return folder


def _tlmgr(folder: Path, *args: str) -> str:
    tlmgr = shutil.which("tlmgr", path=str(folder))
    assert tlmgr is not None, "bin_dir() only returns a folder with tlmgr"
    result = subprocess.run(
        [tlmgr, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PATH": search_path()},
    )
    if result.returncode != 0:
        raise InstallError(f"O tlmgr falhou em `tlmgr {' '.join(args)}`.", result.stdout + result.stderr)
    return result.stdout
