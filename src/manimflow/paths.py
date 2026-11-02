"""Where ManimFlow keeps its own files on the teacher's computer."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """ManimFlow's own folder: its Codex home, its settings and the example lesson live here."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "ManimFlow"


def documents_dir() -> Path:
    """The teacher's Documents folder, wherever the system puts it."""
    if sys.platform == "win32":
        return _windows_documents()
    # Linux desktops name it in the user's language, such as ~/Documentos.
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() == "XDG_DOCUMENTS_DIR":
            return Path(value.strip().strip('"').replace("$HOME", str(Path.home())))
    return Path.home() / "Documents"


def _windows_documents() -> Path:
    # Documents may be moved, to OneDrive for one, so ask Windows instead of guessing.
    import ctypes
    import uuid
    from ctypes import wintypes

    documents = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")  # FOLDERID_Documents
    path = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
    folder_id = ctypes.create_string_buffer(documents.bytes_le)
    if shell32.SHGetKnownFolderPath(folder_id, 0, wintypes.HANDLE(0), ctypes.byref(path)) != 0:
        return Path.home() / "Documents"
    try:
        return Path(path.value or Path.home() / "Documents")
    finally:
        ole32.CoTaskMemFree(path)
