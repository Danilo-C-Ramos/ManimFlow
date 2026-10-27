"""Where ManimFlow keeps its own files on the teacher's computer."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """ManimFlow's own folder: its Codex home and the example lesson live here."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "ManimFlow"
