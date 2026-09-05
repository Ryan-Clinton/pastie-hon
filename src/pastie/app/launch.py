"""Starting the background half, so a shortcut is all anybody needs.

Pastie is two processes: a service that holds the only connection to Haier, and
a window that asks it things. That split is deliberate and worth keeping - but
it is an implementation detail, and making somebody open a terminal first is a
poor way to introduce it.

So the window starts the service if it is not already up. The guard against two
of them is in `pastie.service.instance`, not here: a check followed by a launch
is a race, and the mutex is what actually settles it.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from pastie.service.instance import is_running

log = logging.getLogger(__name__)

#: Windows creation flags: no console window, and not tied to this process, so
#: closing the window does not take the watcher down with it.
_DETACHED = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW


def service_command() -> list[str]:
    """How to start the service, from wherever this happens to be running.

    `pythonw` rather than `python` when it is there: a console window flashing
    up behind the app looks like something went wrong.
    """
    executable = Path(sys.executable)
    quiet = executable.with_name("pythonw.exe")
    if quiet.exists():
        executable = quiet
    return [str(executable), "-m", "pastie.cli", "service"]


def start_service_if_needed() -> bool:
    """Start the service unless one is already running. Returns whether we started one.

    Never raises: a window that will not open because it could not start a
    background process is worse than a window that opens and says the service is
    not running.
    """
    if is_running():
        return False
    try:
        subprocess.Popen(
            service_command(),
            creationflags=_DETACHED if sys.platform == "win32" else 0,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        log.warning("could not start the service: %s", error)
        return False
    return True
