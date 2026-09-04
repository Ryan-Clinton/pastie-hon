"""What the app and the service say to each other.

Pure request-and-reply handling, with no transport in it - the Windows named
pipe lives next door in `channel.py`. Splitting them is what makes the
conversation testable on any machine, and it keeps the interesting decisions
(what is allowed, what a bad request does) away from the Windows API calls.

Rules of the conversation:

* One JSON object per line, in each direction. A line is a whole message.
* A request Pastie does not recognise gets an error, never a guess.
* **No password ever comes back out.** `account.set` goes in; nothing returns a
  password, and no reply contains one. The app hands a new password over and
  forgets it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

#: Requests that change something. Listed so the pipe can be read-only for
#: anyone the service decides should only be able to look.
WRITING = frozenset({"account.set", "settings.set", "command.start", "command.stop"})


@dataclass(frozen=True)
class Request:
    action: str
    arguments: dict[str, Any]

    @classmethod
    def parse(cls, line: str) -> Request:
        parsed = json.loads(line)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("action"), str):
            raise ValueError("a request needs an action")
        arguments = parsed.get("arguments")
        return cls(parsed["action"], dict(arguments) if isinstance(arguments, dict) else {})

    def to_line(self) -> str:
        return json.dumps({"action": self.action, "arguments": self.arguments}) + "\n"


@dataclass(frozen=True)
class Reply:
    ok: bool
    data: dict[str, Any] | None = None
    error: str = ""

    @classmethod
    def worked(cls, **data: Any) -> Reply:
        return cls(True, data)

    @classmethod
    def failed(cls, error: str) -> Reply:
        return cls(False, None, error)

    def to_line(self) -> str:
        body: dict[str, Any] = {"ok": self.ok}
        if self.data is not None:
            body.update(self.data)
        if self.error:
            body["error"] = self.error
        return json.dumps(body) + "\n"

    @classmethod
    def parse(cls, line: str) -> Reply:
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError("a reply must be an object")
        ok = bool(parsed.get("ok"))
        error = str(parsed.get("error", ""))
        data = {key: value for key, value in parsed.items() if key not in ("ok", "error")}
        return cls(ok, data, error)


Handler = Callable[[dict[str, Any]], Awaitable[Reply]]


class Dispatcher:
    """Routes a request to whatever handles it.

    Unknown actions are refused by name rather than ignored, so an app talking
    to an older service gets a sentence explaining that instead of a silence.
    """

    def __init__(self, handlers: Mapping[str, Handler] | None = None) -> None:
        self._handlers: dict[str, Handler] = dict(handlers or {})

    def on(self, action: str, handler: Handler) -> None:
        self._handlers[action] = handler

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    async def handle_line(self, line: str) -> str:
        """Take one line, return one line. Never raises."""
        try:
            request = Request.parse(line)
        except ValueError as error:
            return Reply.failed(f"that request could not be read: {error}").to_line()

        handler = self._handlers.get(request.action)
        if handler is None:
            return Reply.failed(f"'{request.action}' is not something this service does").to_line()

        try:
            reply = await handler(request.arguments)
        except Exception as error:
            log.exception("handling %s failed", request.action)
            reply = Reply.failed(f"{type(error).__name__}: {error}")
        return reply.to_line()
