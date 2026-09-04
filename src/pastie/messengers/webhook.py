"""A webhook, so this can be wired into anything at all.

The most useful messenger in the list, because it is the one nobody has to
write: ntfy, Telegram, Home Assistant, a shell script behind a tiny server, a
company chat channel. Anything that accepts an HTTP POST.

Every delivery carries the event's unique id. Pastie promises not to *announce*
the same thing twice, but if it dies between acting and writing that down, a
webhook may fire twice - so the id is there for a receiver that cares to
recognise the repeat. That trade is deliberate: the alternative is a webhook
that sometimes never fires at all.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any

from pastie.core.events import Event
from pastie.messengers.base import Kind, Result, Setting, Target, redact, sample_event

log = logging.getLogger(__name__)

_TIMEOUT = 15.0


class WebhookMessenger:
    """POSTs a small JSON document when something happens."""

    name = "webhook"
    label = "Webhook"

    def __init__(self, post: Any = None) -> None:
        self._post = post or _post

    def settings(self) -> Iterable[Setting]:
        return (
            Setting("enabled", "Send a webhook", Kind.BOOL, default=False),
            Setting("url", "URL", Kind.TEXT, help="Where to POST. https, unless it is on your LAN"),
            Setting(
                "token",
                "Authorisation header",
                Kind.SECRET,
                help="Optional. Sent as 'Authorization', and never written to a log",
            ),
        )

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:  # noqa: ARG002
        return []  # nothing to enumerate: a webhook is wherever you point it

    async def test(self, config: Mapping[str, Any]) -> Result:
        return await self.react(sample_event(), config)

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        url = str(config.get("url", ""))
        if not url:
            return Result.failed("no URL set")

        body = {
            "id": event.id,
            "key": event.key,
            "kind": event.kind.value,
            "appliance": event.appliance_id,
            "at": event.at.isoformat(),
            "message": event.message,
            "detail": event.detail,
        }
        token = str(config.get("token") or "")
        log.debug("posting %s to %s (auth %s)", event.kind.value, url, redact(token))

        try:
            status = await asyncio.to_thread(self._post, url, body, token)
        except urllib.error.HTTPError as error:
            return Result.failed(f"the endpoint returned {error.code}")
        except urllib.error.URLError as error:
            return Result.failed(f"could not reach the endpoint: {error.reason}")
        return Result.worked(f"posted, {status}")


def _post(url: str, body: dict[str, Any], token: str) -> int:
    headers = {"Content-Type": "application/json", "User-Agent": "pastie"}
    if token:
        headers["Authorization"] = token
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return int(response.status)
