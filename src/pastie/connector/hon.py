"""The only file that talks to Haier.

Everything Haier-shaped is here: their client library, their field names, their
command names, and the workarounds for their behaviour. When they change
something - and they have, in June 2026, breaking every installation until the
community client caught up - this is the file that needs fixing.

The client is `pyhon-revived`: unofficial, community-maintained, and pinned to
an exact version. That is not stable ground, and the design assumes it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from pastie.connector.profiles import Profile, for_appliance
from pastie.connector.reading import RawReading
from pastie.connector.scrub import scrub_identity, scrub_parameters, scrub_statistics

log = logging.getLogger(__name__)


@contextmanager
def _ignoring(what: str) -> Iterator[None]:
    """Swallow a failure from a step worth having but not worth failing on.

    Used only where the alternative is losing a whole update because one extra
    endpoint was unavailable - never around anything the user is told succeeded.
    """
    try:
        yield
    except Exception as error:  # noqa: BLE001 - deliberately broad, and logged
        log.debug("ignored a failure while %s: %s", what, error)


class ConnectorError(RuntimeError):
    """Anything the connector could not do. Classified by `pastie.core.health`."""


class CommandRejectedError(ConnectorError):
    """Haier would not take the command. Distinct from the machine ignoring it."""


def appliance_key(raw_id: str) -> str:
    """A stable id for an appliance that is not the appliance's identity.

    Haier's own identifiers are the MAC address and the serial number, and those
    end up in the memory file, in event keys, and in anything a user pastes into
    an issue. Hashing gives something equally stable to key on and nothing worth
    redacting later.
    """
    return hashlib.sha256(raw_id.encode()).hexdigest()[:12]


class HonConnector:
    """Reads appliances, sends commands, and subscribes to pushed updates.

    Construction does nothing; `connect()` logs in. The client is passed in
    rather than imported here so the whole class can be exercised against a
    stand-in - there is no other way to test the awkward paths, since the real
    thing needs an account and a physical appliance.
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._client_factory = client_factory or _default_client
        self._client: Any | None = None
        self._appliances: dict[str, Any] = {}
        self._profiles: dict[str, Profile] = {}

    # ------------------------------------------------------------ connection

    async def connect(self) -> None:
        try:
            self._client = await self._client_factory(self._username, self._password).create()
        except Exception as error:
            raise ConnectorError(str(error) or type(error).__name__) from error
        self._index()

    async def close(self) -> None:
        client, self._client = self._client, None
        self._appliances.clear()
        if client is not None:
            with _ignoring("closing the client"):
                await client.close()

    def _index(self) -> None:
        self._appliances = {}
        self._profiles = {}
        for appliance in getattr(self._client, "appliances", []):
            key = appliance_key(_identity_of(appliance))
            self._appliances[key] = appliance
            self._profiles[key] = for_appliance(getattr(appliance, "appliance_type", ""))

    def profile(self, appliance_id: str) -> Profile:
        return self._profiles.get(appliance_id) or for_appliance("")

    # --------------------------------------------------------------- reading

    async def read(self, *, with_statistics: bool = True) -> list[RawReading]:
        """One reading per appliance, taken now.

        Statistics come from a separate endpoint that is easy to miss, and they
        carry the cycle counter and the service schedule. They are fetched on
        the same pass but tolerated failing: a missing counter costs some
        precision in one message, while a failed read costs the whole update.
        """
        readings = []
        for appliance_id, appliance in self._appliances.items():
            try:
                await appliance.update()
            except Exception as error:
                raise ConnectorError(str(error) or type(error).__name__) from error
            statistics: dict[str, Any] = {}
            if with_statistics:
                statistics = await self._statistics(appliance)
            readings.append(self._reading(appliance_id, appliance, statistics))
        return readings

    async def _statistics(self, appliance: Any) -> dict[str, Any]:
        try:
            await appliance.load_statistics()
        except Exception as error:  # noqa: BLE001 - an extra endpoint, not the update
            log.debug("statistics unavailable: %s", error)
            return {}
        return scrub_statistics(getattr(appliance, "statistics", None))

    def _reading(self, appliance_id: str, appliance: Any, statistics: dict[str, Any]) -> RawReading:
        attributes = getattr(appliance, "attributes", {}) or {}
        parameters = attributes.get("parameters", {}) or {}
        programme = attributes.get("programName")
        return RawReading(
            appliance_id=appliance_id,
            observed_at=datetime.now(UTC),
            parameters=scrub_parameters(parameters),
            identity=scrub_identity(_appliance_record(appliance)),
            statistics=statistics,
            programme_name=str(programme) if programme is not None else None,
            nickname=getattr(appliance, "nick_name", None),
        )

    # ---------------------------------------------------------------- pushes

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Ask for pushed updates.

        Two things about the client's API, both learned the hard way:
        `subscribe_updates` is **not** a coroutine - awaiting it fails - and it
        requires a callback argument.

        Three things about the session Haier negotiates, all of which shape the
        watcher above this: there is no session persistence, so a reconnect
        replays nothing and a full refresh afterwards is the only correct
        behaviour; delivery is at-least-once, so duplicates are the contract
        rather than a fault; and the presence topics tell us when the appliance
        goes offline and comes back instead of leaving us to infer it.
        """
        if self._client is None:
            raise ConnectorError("not connected")
        result = self._client.subscribe_updates(lambda *_a, **_k: callback())
        if asyncio.iscoroutine(result):  # pragma: no cover - client-version dependent
            raise ConnectorError("subscribe_updates returned a coroutine; the client changed")

    # -------------------------------------------------------------- commands

    async def send(self, appliance_id: str, command: str, arguments: dict[str, Any]) -> None:
        """Send a command, and report only what the server did with it.

        Whether the *machine* did anything is not knowable here, and is decided
        by `pastie.core.commands` from later readings. A success returned by this
        method means Haier took the message. Nothing more.
        """
        appliance = self._appliances.get(appliance_id)
        if appliance is None:
            raise ConnectorError(f"unknown appliance {appliance_id}")

        profile = self.profile(appliance_id)
        if command not in profile.commands:
            # Haier's data lists commands for appliance types nobody here has
            # tested. Offering them because the data says they exist is exactly
            # the guess this project does not make.
            raise CommandRejectedError(
                f"{command} is not confirmed on a {profile.label}, so Pastie won't send it"
            )

        for key, value in arguments.items():
            self._apply_setting(appliance, key, value)

        try:
            accepted = await appliance.commands[command].send()
        except KeyError as error:
            raise CommandRejectedError(f"the appliance has no {command} command") from error
        except Exception as error:
            raise ConnectorError(str(error) or type(error).__name__) from error
        if not accepted:
            raise CommandRejectedError(f"Haier refused the {command} command")

    @staticmethod
    def _apply_setting(appliance: Any, key: str, value: Any) -> None:
        """Set one command parameter, if this machine exposes it.

        Models differ in which settings they accept, and an absent one is not an
        error - it is a feature the machine does not have.
        """
        name = f"startProgram.{key}"
        settings = getattr(appliance, "settings", {}) or {}
        if name not in settings:
            log.debug("appliance does not expose %s; skipped", name)
            return
        try:
            settings[name].value = value
        except Exception as error:  # noqa: BLE001 - a rejected value is not fatal
            log.warning("appliance rejected %s=%r: %s", name, value, error)


# ------------------------------------------------------------------ helpers


def _default_client(username: str, password: str) -> Any:
    from pyhon import Hon

    return Hon(username, password)


def _identity_of(appliance: Any) -> str:
    for attribute in ("unique_id", "mac_address", "nick_name"):
        value = getattr(appliance, attribute, None)
        if value:
            return str(value)
    return "unknown"


def _appliance_record(appliance: Any) -> dict[str, Any]:
    """The identity block, from wherever this version of the client keeps it."""
    data = getattr(appliance, "data", None)
    if isinstance(data, dict) and isinstance(data.get("appliance"), dict):
        return dict(data["appliance"])
    return {
        "applianceTypeName": getattr(appliance, "appliance_type", ""),
        "modelName": getattr(appliance, "model_name", ""),
        "brand": getattr(appliance, "brand", ""),
    }
