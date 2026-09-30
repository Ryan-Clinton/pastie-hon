"""The desktop window's entry point: `pastie-app`.

Two processes is an implementation detail, not something to make somebody open
a terminal for. If the background half is not up, this starts it, then opens
the window (app/webview.py), which draws what app/presenter.py decides.
"""

from __future__ import annotations

import logging
import sys

from pastie.app.client import ServiceClient
from pastie.app.launch import start_service_if_needed
from pastie.app.memory import WindowMemory
from pastie.app.personality import PersonalityStore
from pastie.app.webview import run
from pastie.service import paths
from pastie.service.channel import PipeClient


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    start_service_if_needed()
    memory = WindowMemory(paths.app_dir() / "window.json")
    personalities = PersonalityStore(paths.app_dir() / "personalities")
    run(ServiceClient(PipeClient().ask), memory, personalities)
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
