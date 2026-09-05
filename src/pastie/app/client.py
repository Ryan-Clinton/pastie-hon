"""The app's end of the conversation, with no window attached.

Everything the desktop app can ask the service for is a method here, and none of
it knows about tkinter. That separation is what makes the app's behaviour
testable: the tests point this at the real `Dispatcher` and check the whole
round trip, request line to reply, without Windows, a pipe, or a screen.

The transport is a single callable - "here is a line, give me a line back" - so
the pipe is one implementation and a test's in-process function is another.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pastie.service.protocol import Reply, Request

#: A transport is anything that turns a request line into a reply line.
Transport = Callable[[str], str]


class ServiceUnavailableError(RuntimeError):
    """The service is not answering. Shown to the user as a sentence, not a stack."""


@dataclass
class MessengerDescription:
    """A messenger as the settings screen needs to know it.

    The screen is built from this rather than from a list of hard-coded widgets,
    which is the whole reason a new messenger needs no interface code.
    """

    name: str
    label: str
    settings: list[dict[str, Any]] = field(default_factory=list)
    #: (kind, label) for every alert that can be given its own settings.
    alerts: list[tuple[str, str]] = field(default_factory=list)


class ServiceClient:
    """Asks the service things. Never talks to Haier, and never holds a password."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def _ask(self, action: str, **arguments: Any) -> dict[str, Any]:
        try:
            raw = self._transport(Request(action, arguments).to_line())
        except Exception as error:
            raise ServiceUnavailableError(str(error)) from error

        try:
            reply = Reply.parse(raw)
        except ValueError as error:
            raise ServiceUnavailableError(f"the service replied with nonsense: {error}") from error
        if not reply.ok:
            raise ServiceUnavailableError(reply.error or "the service refused that")
        return reply.data or {}

    # ------------------------------------------------------------- reading

    def status(self) -> dict[str, Any]:
        return self._ask("status")

    def settings(self) -> tuple[dict[str, Any], list[MessengerDescription], bool]:
        """Current settings, how to draw them, and whether an account is saved.

        The alerts that can be given their own settings come back too, and are
        kept on the description rather than hard-coded in the window.
        """
        reply = self._ask("settings.get")
        alerts = [
            (str(item.get("kind", "")), str(item.get("label", "")))
            for item in reply.get("alerts", [])
        ]
        messengers = [
            MessengerDescription(
                name=str(item.get("name", "")),
                label=str(item.get("label", "")),
                settings=list(item.get("settings", [])),
                alerts=alerts,
            )
            for item in reply.get("messengers", [])
        ]
        return dict(reply.get("settings", {})), messengers, bool(reply.get("account"))

    # ------------------------------------------------------------- writing

    def save_messenger(self, name: str, values: dict[str, Any]) -> None:
        self._ask("settings.set", messenger=name, values=values)

    def set_account(self, username: str, password: str) -> bool:
        """Hand a new password to the service, which encrypts it.

        The app does not keep it, does not read it back, and has nowhere to
        store it: the service and the logged-in user are different accounts, and
        a secret saved here would be unreadable to the half that needs it.
        """
        reply = self._ask("account.set", username=username, password=password)
        return bool(reply.get("restart_needed"))

    def test_messenger(self, name: str) -> tuple[bool, str]:
        """Whether the messenger worked, and what it said.

        Distinct from whether the *request* worked: a service that is running
        happily can report a Hue bridge that is not.
        """
        reply = self._ask("messenger.test", name=name)
        return bool(reply.get("worked")), str(reply.get("detail", ""))

    def discover(self, name: str) -> list[dict[str, Any]]:
        return list(self._ask("messenger.discover", name=name).get("targets", []))

    def start(self, appliance: str, programme: str, **extra: Any) -> list[str]:
        """Ask for a cycle. Returns the progress lines - not a claim of success."""
        reply = self._ask("command.start", appliance=appliance, programme=programme, **extra)
        return [str(line) for line in reply.get("lines", [])]

    def stop(self, appliance: str) -> list[str]:
        reply = self._ask("command.stop", appliance=appliance)
        return [str(line) for line in reply.get("lines", [])]
