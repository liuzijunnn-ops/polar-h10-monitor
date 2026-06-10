"""Application paths — works in dev and PyInstaller frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Directory for user data (logs). Next to .exe when frozen, else project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


LOGS_DIR = app_root() / "logs"
