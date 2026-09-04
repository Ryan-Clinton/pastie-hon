"""The cap on flashing lights, and the lock that stops two alerts fighting.

Flashing light can trigger seizures in people with photosensitive epilepsy.
Philips's own developer terms put that responsibility on the application, not on
the bridge, so it is capped here - centrally, once - rather than trusted to
every messenger that ever gets written.

The numbers are deliberately conservative. Published guidance treats flashing
above about three times a second as the risk, and the entire point of a Pastie
alert is to be noticed from the next room rather than to be dramatic; one pulse
a second for a few seconds does that.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

#: Never faster than this, whatever a messenger or a user's settings ask for.
MAX_FLASHES_PER_SECOND = 1.0

#: Never longer than this in one alert. A light that will not stop is a fault
#: report from the user, not a feature.
MAX_SECONDS = 30.0


@dataclass(frozen=True)
class FlashPlan:
    """A flash pattern that has already been made safe."""

    flashes: int
    interval: float
    seconds: float

    @property
    def rate(self) -> float:
        return 1.0 / self.interval if self.interval else 0.0


def plan(flashes: int, seconds: float) -> FlashPlan:
    """Clamp a requested pattern to something safe.

    Both the count and the duration are clamped, and the interval is derived
    from the clamped pair - so asking for forty flashes in two seconds gets you
    a slower flash, not a shorter seizure risk.
    """
    seconds = max(0.0, min(float(seconds), MAX_SECONDS))
    flashes = max(1, int(flashes))
    allowed = max(1, int(seconds * MAX_FLASHES_PER_SECOND)) if seconds else 1
    flashes = min(flashes, allowed)
    interval = seconds / flashes if flashes and seconds else 0.0
    return FlashPlan(flashes=flashes, interval=interval, seconds=seconds)


class TargetLocks:
    """One alert at a time per target.

    Two events arriving together - a cycle finishing on one appliance while
    another faults - must not both snapshot the same light's state and both
    restore it. The second would restore the colour the first had just set, and
    the light would stay green until somebody noticed.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def for_target(self, target: str) -> asyncio.Lock:
        lock = self._locks.get(target)
        if lock is None:
            lock = self._locks[target] = asyncio.Lock()
        return lock
