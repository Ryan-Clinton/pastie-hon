"""The private channel between the app and the service.

A Windows **named pipe**, not a web address. That is a security decision, not a
convenience one: a web page open in your browser can reach programs listening on
your own machine - it is a real attack, and browsers are adding warnings about
it. A named pipe cannot be reached that way.

**The trap, spelled out.** Create a pipe without saying who may use it and
Windows applies a default that grants read access to *everyone*, anonymous
logons included. It has to be locked down deliberately, so the descriptor below
is not optional decoration - it is the security of the channel.

    D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;IU)

    D:P    a discretionary list, protected: nothing is inherited, so the
           permissive default cannot leak back in
    SY     LocalSystem, full control
    BA     the local Administrators group, full control
    IU     interactively logged-on users - the person at the keyboard, which is
           who the desktop app runs as

Nobody else is named, and what is not granted is denied. Anonymous logons and
network users are not on the list.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import threading
import time
from typing import Any

from pastie.service.protocol import Dispatcher

log = logging.getLogger(__name__)

WINDOWS = sys.platform == "win32"

#: The one pipe. `.` means this machine - a named pipe can be exposed to the
#: network, and this one deliberately is not.
PIPE_NAME = r"\\.\pipe\pastie"

#: See the module docstring. Changing this changes who can drive your appliance.
SECURITY_DESCRIPTOR = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;IU)"

_BUFFER = 64 * 1024


class ChannelUnavailableError(RuntimeError):
    """The service is not running, or the pipe could not be created."""


def _security_attributes() -> Any:
    """A SECURITY_ATTRIBUTES that names exactly who may use the pipe."""
    import win32security

    # pywin32 exposes this without the W suffix the Win32 documentation uses.
    descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        SECURITY_DESCRIPTOR, win32security.SDDL_REVISION_1
    )
    attributes = win32security.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    attributes.bInheritHandle = False
    return attributes


class PipeServer:
    """Serves the dispatcher over the named pipe.

    **Several instances, not one.** An earlier version created a single pipe
    instance on the reasoning that there is only one desktop app - which was
    wrong, and wrong in a way that looked like a different bug entirely. The app
    asks for the status, the settings and a list of lights at the same moment,
    on three worker threads. With one instance the first is served and the other
    two find no pipe at all, so a running service reports itself as not running
    on half the screen.

    So: a fresh instance is created as soon as the previous one is claimed, and
    each conversation is handled on its own thread.
    """

    def __init__(self, dispatcher: Dispatcher, name: str = PIPE_NAME) -> None:
        if not WINDOWS:  # pragma: no cover - the service is Windows-only
            raise ChannelUnavailableError("named pipes need Windows")
        self._dispatcher = dispatcher
        self._name = name

    async def serve(self, stop: asyncio.Event) -> None:
        """Accept connections until told to stop.

        Only the waiting-for-a-client part is awaited; each accepted client is
        handed to a thread so the next instance can be waiting immediately.

        `ConnectNamedPipe` waits forever and cannot be cancelled, so setting
        `stop` is not enough on its own: something has to arrive for the wait to
        return. Hence the nudge - the service connects to its own pipe once, to
        wake the accept and let the loop notice it should finish. Without it the
        process hangs on exit waiting for a client that is never coming.
        """
        waker = asyncio.create_task(self._nudge_when(stop))
        try:
            while not stop.is_set():
                handle = await asyncio.to_thread(self._accept)
                if handle is None:
                    continue
                if stop.is_set():
                    _close(handle)
                    return
                threading.Thread(
                    target=self._converse, args=(handle, stop), name="pastie-pipe", daemon=True
                ).start()
        finally:
            waker.cancel()

    async def _nudge_when(self, stop: asyncio.Event) -> None:
        await stop.wait()
        await asyncio.to_thread(self._nudge)

    def _nudge(self) -> None:
        """Connect to our own pipe, so a waiting accept returns."""
        import win32file

        with contextlib.suppress(Exception):
            _close(
                win32file.CreateFile(
                    self._name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
            )

    def _accept(self) -> Any:
        """Create an instance and block until somebody connects to it."""
        import pywintypes
        import win32pipe

        handle = win32pipe.CreateNamedPipe(
            self._name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            _BUFFER,
            _BUFFER,
            1000,
            _security_attributes(),
        )
        try:
            win32pipe.ConnectNamedPipe(handle, None)
        except pywintypes.error as error:
            log.debug("nobody connected: %s", error)
            _close(handle)
            return None
        return handle

    def _converse(self, handle: Any, stop: asyncio.Event) -> None:
        """Answer one client until it goes away."""
        import pywintypes
        import win32file

        try:
            while not stop.is_set():
                try:
                    _, data = win32file.ReadFile(handle, _BUFFER)
                except pywintypes.error:
                    return  # the app closed the window
                for line in data.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    reply = asyncio.run(self._dispatcher.handle_line(line))
                    win32file.WriteFile(handle, reply.encode("utf-8"))
        finally:
            _close(handle)


def _close(handle: Any) -> None:
    import win32file
    import win32pipe

    with contextlib.suppress(Exception):
        win32pipe.DisconnectNamedPipe(handle)
    with contextlib.suppress(Exception):
        win32file.CloseHandle(handle)


class PipeClient:
    """The app's end. Connects, asks, disconnects."""

    def __init__(self, name: str = PIPE_NAME, timeout: float = 10.0) -> None:
        self._name = name
        self._timeout = timeout

    def ask(self, line: str) -> str:
        """Send one request line, return one reply line."""
        if not WINDOWS:  # pragma: no cover - the app is Windows-only
            raise ChannelUnavailableError("named pipes need Windows")
        import win32file

        handle = self._connect()
        try:
            win32file.WriteFile(handle, line.encode("utf-8"))
            _, data = win32file.ReadFile(handle, _BUFFER)
            return str(data.decode("utf-8")).splitlines()[0]
        finally:
            win32file.CloseHandle(handle)

    def _connect(self) -> Any:
        """Open the pipe, waiting briefly if every instance is busy.

        "Busy" and "not there" are different answers and must not be reported
        the same way: the service creates a new instance the moment one is
        claimed, so a busy pipe means somebody got in a few milliseconds before
        us, not that there is nothing to talk to.
        """
        import pywintypes
        import win32file
        import winerror

        deadline = time.monotonic() + self._timeout
        while True:
            try:
                return win32file.CreateFile(
                    self._name,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
            except pywintypes.error as error:
                busy = error.winerror == winerror.ERROR_PIPE_BUSY
                if not busy or time.monotonic() >= deadline:
                    raise ChannelUnavailableError(
                        "Pastie's background service is not running. Start it, and try again."
                        if not busy
                        else "Pastie's service is busy. Try again in a moment."
                    ) from error
                time.sleep(0.05)
