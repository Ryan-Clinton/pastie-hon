"""Things worth telling somebody about.

An event is the brain's output and the messengers' input. It carries its own
`key`, which is its identity for "never announce the same thing twice" - stable
across restarts, because that is precisely when double announcements happen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventKind(Enum):
    CYCLE_STARTED = "cycle_started"
    CYCLE_FINISHED = "cycle_finished"
    #: Finished while Pastie was not watching. Reported as a gap, not as news.
    CYCLE_FINISHED_WHILE_AWAY = "cycle_finished_while_away"
    FAULT = "fault"
    MAINTENANCE_DUE = "maintenance_due"

    @property
    def is_alert(self) -> bool:
        """Whether this is something to flash a light and speak about.

        A cycle starting is worth showing in the window; it is not worth
        shouting across the house.
        """
        return self in _ALERTS


_ALERTS = frozenset(
    {
        EventKind.CYCLE_FINISHED,
        EventKind.CYCLE_FINISHED_WHILE_AWAY,
        EventKind.FAULT,
    }
)


@dataclass(frozen=True, slots=True)
class Event:
    """Something that happened, and how to describe it.

    `key` is the deduplication identity and must be derivable from the
    appliance's own facts - a cycle counter, a fault code - and never from a
    random value or the current time, or a restart would produce a new key for
    an event already announced.

    `id` is per-delivery and unique. It goes out with anything sent to another
    system, so a receiver that cares can drop a repeat: Pastie promises not to
    announce twice, but if it dies between acting and recording, a light may
    still flash twice. That trade is deliberate - the alternative is a light
    that sometimes never flashes at all.
    """

    kind: EventKind
    appliance_id: str
    at: datetime
    key: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex, compare=False)

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            raise ValueError("Event.at must be timezone-aware")

    @property
    def is_alert(self) -> bool:
        return self.kind.is_alert
