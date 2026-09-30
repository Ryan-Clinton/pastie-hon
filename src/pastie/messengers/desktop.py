"""A Windows notification, for anybody with nothing else to poke.

The smallest useful Pastie is a Haier appliance and a Windows PC: no bridge, no
speaker, no server to receive a webhook. This is that Pastie.

It uses Windows' own toast notifications through Windows PowerShell, which every
supported version of Windows has, rather than a new dependency. The event's text
reaches PowerShell through environment variables and is XML-escaped there -
never pasted into the script - so a programme name containing a quote or an
angle bracket is text, not code.

**It needs somebody's desktop.** A notification appears in the session of the
account that raises it. The service runs as a login task, as you, so it shows
on your screen. If the service ever moves to an identity of its own (SPEC 14,
experiment 4), this messenger will have nobody to show anything to, and will
need to hand the notification to the window instead.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pastie.core.events import Event, EventKind
from pastie.messengers.base import Kind, Result, Setting, Target, sample_event

log = logging.getLogger(__name__)

#: Toasts are attributed to an installed application. Windows PowerShell's is
#: always present; an identity of Pastie's own needs a registered Start menu
#: shortcut carrying it, which the zip download cannot promise.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_TIMEOUT = 20.0

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = [Security.SecurityElement]::Escape($env:PASTIE_TOAST_TITLE)
$body = [Security.SecurityElement]::Escape($env:PASTIE_TOAST_BODY)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$body</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:PASTIE_TOAST_APP).Show($toast)
"""

#: The headline for each alert. The event's own sentence is the body.
_TITLES = {
    EventKind.CYCLE_FINISHED: "Finished",
    EventKind.CYCLE_FINISHED_WHILE_AWAY: "Finished while Pastie was away",
    EventKind.FAULT: "Fault",
    EventKind.NEEDS_EMPTYING: "Needs you",
    EventKind.MAINTENANCE_DUE: "Cleaning due",
}

#: (title, body) -> None, raising on failure. Swapped out by the tests.
Show = Callable[[str, str], None]


class DesktopMessenger:
    """Raises a Windows notification when something happens."""

    name = "desktop"
    label = "Windows notification"

    def __init__(self, show: Show | None = None) -> None:
        self._show = show or _show

    def settings(self) -> Iterable[Setting]:
        return (
            Setting(
                "enabled",
                "Show a Windows notification",
                Kind.BOOL,
                default=False,
                help="On this PC, for whoever is signed in",
            ),
        )

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:  # noqa: ARG002
        return []  # the only target is this desktop

    async def test(self, config: Mapping[str, Any]) -> Result:
        return await self.react(sample_event(), config)

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:  # noqa: ARG002
        if sys.platform != "win32" and self._show is _show:
            return Result.failed("Windows notifications need Windows")
        title = f"Pastie - {_TITLES.get(event.kind, event.kind.label)}"
        try:
            await asyncio.to_thread(self._show, title, event.message)
        except (OSError, subprocess.SubprocessError) as error:
            return Result.failed(f"Windows would not show it: {error}")
        return Result.worked("shown")


def _show(title: str, body: str) -> None:
    encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    env = {
        **os.environ,
        "PASTIE_TOAST_TITLE": title,
        "PASTIE_TOAST_BODY": body,
        "PASTIE_TOAST_APP": _APP_ID,
    }
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout).strip().splitlines()
        raise OSError(reason[-1] if reason else f"PowerShell exited {completed.returncode}")
