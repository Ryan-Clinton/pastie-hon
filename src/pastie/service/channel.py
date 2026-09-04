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
import logging
import sys
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

    descriptor = win32security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        SECURITY_DESCRIPTOR, win32security.SDDL_REVISION_1
    )
    attributes = win32security.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    attributes.bInheritHandle = False
    return attributes


class PipeServer:
    """Serves the dispatcher over the named pipe, one client at a time.

    One at a time is not a limitation worth removing: the only client is the
    desktop app, and a second connection is a second window, which can wait the
    few milliseconds a status reply takes.
    """

    def __init__(self, dispatcher: Dispatcher, name: str = PIPE_NAME) -> None:
        if not WINDOWS:  # pragma: no cover - the service is Windows-only
            raise ChannelUnavailableError("named pipes need Windows")
        self._dispatcher = dispatcher
        self._name = name

    async def serve(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await asyncio.to_thread(self._serve_one_client, stop)

    def _serve_one_client(self, stop: asyncio.Event) -> None:
        import pywintypes
        import win32file
        import win32pipe

        handle = win32pipe.CreateNamedPipe(
            self._name,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,  # one instance: one app, one conversation
            _BUFFER,
            _BUFFER,
            1000,
            _security_attributes(),
        )
        try:
            win32pipe.ConnectNamedPipe(handle, None)
            while not stop.is_set():
                try:
                    _, data = win32file.ReadFile(handle, _BUFFER)
                except pywintypes.error:
                    return  # the app closed the window; wait for the next one
                for line in data.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    reply = asyncio.run(self._dispatcher.handle_line(line))
                    win32file.WriteFile(handle, reply.encode("utf-8"))
        finally:
            win32pipe.DisconnectNamedPipe(handle)
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
        import pywintypes
        import win32file

        try:
            handle = win32file.CreateFile(
                self._name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None,
            )
        except pywintypes.error as error:
            raise ChannelUnavailableError(
                "Pastie's background service is not running. Start it, and try again."
            ) from error

        try:
            win32file.WriteFile(handle, line.encode("utf-8"))
            _, data = win32file.ReadFile(handle, _BUFFER)
            return str(data.decode("utf-8")).splitlines()[0]
        finally:
            win32file.CloseHandle(handle)
