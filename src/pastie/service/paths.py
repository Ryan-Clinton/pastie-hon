"""Where Pastie keeps things.

Two locations, because there are two identities involved and confusing them is
the single most common way this sort of thing breaks:

* **The service's data** - what it has announced, what it last knew, the
  settings it acts on - lives in ProgramData. The service does not run as you,
  and anything written under your profile would not be readable by it.
* **The app's preferences** - window size, which tab was open - live under your
  profile, because they are yours and nobody else's business.

`PASTIE_DATA_DIR` overrides both, which is how the tests and a portable copy on
a memory stick work without special cases in the code.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Pastie"
_OVERRIDE = "PASTIE_DATA_DIR"


def service_dir() -> Path:
    """Shared, machine-wide state, written by the service."""
    override = os.environ.get(_OVERRIDE)
    if override:
        return Path(override)
    base = os.environ.get("PROGRAMDATA") or os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def app_dir() -> Path:
    """Per-user preferences, written by the desktop app."""
    override = os.environ.get(_OVERRIDE)
    if override:
        return Path(override) / "user"
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}" / "user"


def settings_file() -> Path:
    return service_dir() / "settings.json"


def memory_file() -> Path:
    return service_dir() / "memory.json"


def ledger_file() -> Path:
    return service_dir() / "announced.json"


def speech_cache_dir() -> Path:
    return service_dir() / "speech"


def log_file() -> Path:
    return service_dir() / "pastie.log"
