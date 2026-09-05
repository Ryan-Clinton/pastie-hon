"""One service, and only one.

The whole design rests on there being a single connection to Haier's servers -
the app asks the service rather than opening its own, so the two can never
disagree about what the machine is doing. Two services would put that back, and
worse: two sets of announcements, two ledgers racing each other, and a light
flashed twice for one finished cycle.

Nothing enforced that until the window started launching the service for you.
Now it does.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Iterator

log = logging.getLogger(__name__)

WINDOWS = sys.platform == "win32"

#: `Local\` rather than `Global\`: a Global object needs a privilege ordinary
#: accounts do not have, and the service runs as the logged-in user. If it ever
#: moves to a service identity this has to become Global, and the mutex will be
#: the thing that tells you - a second copy will start happily.
MUTEX_NAME = r"Local\PastieService"


class AlreadyRunningError(RuntimeError):
    """Another service holds the connection to Haier."""


@contextlib.contextmanager
def only_one(name: str = MUTEX_NAME) -> Iterator[None]:
    """Hold the claim to being *the* service for the life of the block.

    Raises `AlreadyRunningError` immediately if somebody else has it, rather
    than waiting: a second service is a mistake to report, not a queue to join.

    `name` exists so the tests can claim something of their own. Without it they
    would compete with whatever service the developer has running, and fail for
    a reason that has nothing to do with the code under test.
    """
    if not WINDOWS:  # pragma: no cover - the service is Windows-only
        yield
        return

    import win32api
    import win32event
    import winerror

    handle = win32event.CreateMutex(None, True, name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(handle)
        raise AlreadyRunningError(
            "Pastie's service is already running. There can only be one, because "
            "it holds the only connection to Haier."
        )
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            win32event.ReleaseMutex(handle)
        with contextlib.suppress(Exception):
            win32api.CloseHandle(handle)


def is_running(name: str = MUTEX_NAME) -> bool:
    """Whether a service is already up, without disturbing it.

    Opening the mutex is a question, not a claim: it does not create one, so
    asking cannot accidentally become the thing being asked about.
    """
    if not WINDOWS:  # pragma: no cover - the service is Windows-only
        return False

    import win32api
    import win32event

    try:
        handle = win32event.OpenMutex(win32event.SYNCHRONIZE, False, name)
    except Exception:  # noqa: BLE001 - "cannot open it" is the answer, whatever the reason
        return False
    win32api.CloseHandle(handle)
    return True
