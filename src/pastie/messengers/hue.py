"""Philips Hue, on the current API.

The old v1 interface still works today and stops working on newer bridge
firmware, so this speaks CLIP v2. Two things about that migration, both
measured against a real bridge rather than assumed:

* **The existing key still works.** A v1 username, sent as the
  `hue-application-key` header, is accepted by v2 - lights, rooms, scenes and
  the event stream all return 200. Nobody has to press the button on their
  bridge again, which removes the most annoying part of the upgrade.
* **v2 says outright whether a light does colour.** A `color` block is present
  or it is not, so "check before sending a colour" stops being guesswork about
  the shape of a v1 state and becomes reading a field.

Everything here is local: the bridge is on your network, and no part of a Hue
alert touches the internet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from pastie.core.events import Event
from pastie.messengers.base import Kind, Result, Setting, Target, sample_event
from pastie.messengers.flash import TargetLocks, plan

log = logging.getLogger(__name__)

#: Named colours as CIE xy, which is what v2 speaks. Approximate on purpose:
#: these are "unmistakably green from the next room", not colour management.
COLOURS: dict[str, tuple[float, float]] = {
    "Green": (0.17, 0.70),
    "Red": (0.675, 0.322),
    "Orange": (0.55, 0.41),
    "Yellow": (0.45, 0.48),
    "Blue": (0.167, 0.04),
    "Purple": (0.28, 0.11),
    "Pink": (0.40, 0.19),
    "Cyan": (0.17, 0.34),
}

_TIMEOUT = 10.0


class HueError(RuntimeError):
    pass


class BridgeApi(Protocol):
    """The three calls a bridge has to answer.

    Named so a test - or a second implementation, if Philips move again - can
    stand in for the real one without inheriting from it.
    """

    def lights(self) -> list[dict[str, Any]]: ...

    def light(self, light_id: str) -> dict[str, Any]: ...

    def put(self, light_id: str, body: dict[str, Any]) -> None: ...


class Bridge:
    """The bits of CLIP v2 that Pastie needs, and nothing else."""

    def __init__(self, address: str, key: str, *, verify: bool = False) -> None:
        if not address or not key:
            raise HueError("the bridge address and application key are both required")
        self._base = f"https://{address}/clip/v2/resource"
        self._key = key
        # A Hue bridge presents a certificate signed by Philips' own authority,
        # with the bridge id as its subject - so ordinary hostname verification
        # against an IP address fails, and the usual fix of pinning the Philips
        # root needs the bridge id the user has not been asked for. The
        # connection is to a device on your own LAN, authenticated by a key the
        # bridge issued, and it carries "make the light green". Verification is
        # off by default and can be turned on by anyone who has set up a name
        # and a trust store for their bridge.
        self._context = ssl.create_default_context()
        if not verify:
            self._context.check_hostname = False
            self._context.verify_mode = ssl.CERT_NONE

    def _request(self, path: str, method: str = "GET", body: Any = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=data,
            method=method,
            headers={"hue-application-key": self._key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=_TIMEOUT, context=self._context
            ) as response:
                parsed = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise HueError("the bridge rejected the application key") from error
            raise HueError(f"the bridge returned {error.code}") from error
        except urllib.error.URLError as error:
            raise HueError(f"could not reach the bridge: {error.reason}") from error
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    def lights(self) -> list[dict[str, Any]]:
        return list(self._request("/light").get("data", []))

    def light(self, light_id: str) -> dict[str, Any]:
        """One light, including its `metadata.name` - which is what a person calls it."""
        found = self._request(f"/light/{light_id}").get("data", [])
        if not found:
            raise HueError("that light is no longer on the bridge")
        return dict(found[0])

    def put(self, light_id: str, body: dict[str, Any]) -> None:
        """Write to one light, and write down that we did.

        Recorded because "are you sure it did not touch the other bulbs?" is a
        fair question that should be answered from a log rather than from
        somebody's assurance about what the code does. Every write is one line,
        naming the single light it went to.
        """
        log.info("hue write -> %s %s", light_id, body)
        self._request(f"/light/{light_id}", "PUT", body)


def supports_colour(light: Mapping[str, Any]) -> bool:
    """v2 states this outright, so nothing here has to infer it."""
    return isinstance(light.get("color"), dict)


def _state_of(light: Mapping[str, Any]) -> dict[str, Any]:
    """The parts of a light's state worth putting back."""
    state: dict[str, Any] = {"on": {"on": bool(light.get("on", {}).get("on", False))}}
    dimming = light.get("dimming")
    if isinstance(dimming, dict) and "brightness" in dimming:
        state["dimming"] = {"brightness": dimming["brightness"]}
    colour = light.get("color")
    if isinstance(colour, dict) and isinstance(colour.get("xy"), dict):
        state["color"] = {"xy": dict(colour["xy"])}
    return state


def _looks_like(light: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Whether a light is still showing what we set it to.

    Restoring blindly overrides the user, which is maddening: you switch the
    light off mid-alert and Pastie switches it back on. So the state is checked
    before it is put back, and anything else is left exactly as found.
    """
    if bool(light.get("on", {}).get("on")) is not bool(expected.get("on", {}).get("on")):
        return False
    wanted = expected.get("dimming", {}).get("brightness")
    if wanted is not None:
        actual = light.get("dimming", {}).get("brightness")
        if actual is None or abs(float(actual) - float(wanted)) > 5:
            return False
    wanted_xy = expected.get("color", {}).get("xy")
    if wanted_xy is not None:
        actual_xy = light.get("color", {}).get("xy")
        if not isinstance(actual_xy, dict):
            return False
        if any(abs(float(actual_xy.get(axis, 0)) - float(wanted_xy[axis])) > 0.05 for axis in "xy"):
            return False
    return True


class HueMessenger:
    """Flashes a light when something happens, and puts it back afterwards."""

    name = "hue"
    label = "Philips Hue"

    def __init__(self, bridge_factory: Callable[..., BridgeApi] = Bridge) -> None:
        self._bridge_factory = bridge_factory
        self._locks = TargetLocks()

    def settings(self) -> Iterable[Setting]:
        return (
            Setting("enabled", "Flash a Hue light", Kind.BOOL, default=False),
            Setting(
                "address",
                "Bridge address",
                Kind.TEXT,
                help="The bridge's IP on your network",
            ),
            Setting(
                "key",
                "Application key",
                Kind.SECRET,
                help="Your existing key works - you do not need to press the bridge button again",
            ),
            Setting("light", "Light", Kind.TARGET),
            Setting(
                "colour",
                "Colour",
                Kind.CHOICE,
                default="Green",
                choices=tuple(COLOURS),
                per_event=True,
                per_event_defaults={
                    "fault": "Red",
                    "needs_emptying": "Cyan",
                    "maintenance_due": "Blue",
                },
                help="So you can tell what happened from the next room, without going to look",
            ),
            Setting("brightness", "Brightness", Kind.NUMBER, default=100),
            Setting("seconds", "How long", Kind.NUMBER, default=15, per_event=True),
            Setting(
                "restore",
                "Put the light back afterwards",
                Kind.BOOL,
                default=True,
                help="Only if it is still showing what Pastie set - otherwise it is left alone",
            ),
        )

    def _bridge(self, config: Mapping[str, Any]) -> BridgeApi:
        return self._bridge_factory(
            str(config.get("address", "")),
            str(config.get("key", "")),
            verify=bool(config.get("verify_certificate", False)),
        )

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:
        bridge = self._bridge(config)
        lights = await asyncio.to_thread(bridge.lights)
        return [
            Target(
                id=str(light.get("id", "")),
                label=str(light.get("metadata", {}).get("name", "light")),
                detail="colour" if supports_colour(light) else "white only",
                available=bool(light.get("on") is not None),
            )
            for light in lights
        ]

    async def test(self, config: Mapping[str, Any]) -> Result:
        return await self.react(sample_event(), config)

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:  # noqa: ARG002
        # `event` is part of the messenger interface and deliberately unused
        # here: everything this alert should look like was already merged into
        # `config` by the runner, so a light cannot accidentally treat one kind
        # of event differently from what the user asked for.
        light_id = str(config.get("light", ""))
        if not light_id:
            return Result.failed("no light chosen")

        # Which colour this alert gets was decided before we were called: the
        # runner merged the per-alert override into the config. See
        # `pastie.messengers.base.for_event`.
        colour = str(config.get("colour", "Green"))

        async with self._locks.for_target(f"{config.get('address')}/{light_id}"):
            try:
                return await asyncio.to_thread(self._alert, light_id, config, colour)
            except HueError as error:
                return Result.failed(str(error))

    def _alert(self, light_id: str, config: Mapping[str, Any], colour: str) -> Result:
        bridge = self._bridge(config)
        before = bridge.light(light_id)
        restore_to = _state_of(before)

        pattern = plan(
            flashes=int(config.get("flashes", 3)),
            seconds=float(config.get("seconds", 15)),
        )
        wanted: dict[str, Any] = {
            "on": {"on": True},
            "dimming": {"brightness": float(config.get("brightness", 100))},
        }
        if supports_colour(before):
            x, y = COLOURS.get(colour, COLOURS["Green"])
            wanted["color"] = {"xy": {"x": x, "y": y}}
        else:
            # Plenty of bulbs are white-only, and sending them a colour makes the
            # call fail. Pulsing the brightness says the same thing.
            log.debug("light %s is white-only; pulsing brightness instead", light_id)

        name = str(before.get("metadata", {}).get("name", "")) or light_id
        log.info("hue: alerting %r (%s) in %s", name, light_id, colour)
        bridge.put(light_id, {**wanted, "alert": {"action": "breathe"}})
        _sleep(pattern.seconds)

        if not config.get("restore", True):
            return Result.worked("alert sent; the light was left as set")

        after = bridge.light(light_id)
        if not _looks_like(after, wanted):
            return Result.worked("alert sent; the light had been changed, so it was left alone")
        bridge.put(light_id, restore_to)
        return Result.worked(f"flashed for {pattern.seconds:.0f}s and restored")


def _sleep(seconds: float) -> None:
    """Only ever called on a worker thread, never on the event loop."""
    time.sleep(seconds)
