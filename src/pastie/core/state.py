"""What an appliance is doing, in plain language.

Haier's own field names (`machMode`, `prPhase`, `remoteCtrValid` and the rest) do
not appear in this module, and must not appear anywhere outside
`pastie.connector`. A `Snapshot` is the boundary: everything upstream of it is
Haier's vocabulary, everything downstream is ours.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ApplianceState(Enum):
    """What the machine is doing now.

    UNKNOWN is a real state, not a null. Pastie is in it at startup and after a
    dropped connection, and the whole point of it is that nothing is announced
    from an unknown baseline - see `pastie.core.tracker`.
    """

    UNKNOWN = "unknown"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    FAULT = "fault"

    @property
    def is_known(self) -> bool:
        return self is not ApplianceState.UNKNOWN


class Trust(Enum):
    """How much we are willing to say about an appliance.

    UNVERIFIED means nobody has confirmed what this model's numbers mean. Such an
    appliance gets detection and raw diagnostics only: no interpreted state, no
    fault alerts, no commands. Announcing "fault" because a number matched what
    it means on somebody else's dryer is exactly the mistake this prevents.
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True)
class Maintenance:
    """A service interval the appliance keeps track of itself.

    The machine reports these - filter every 15 cycles, drum every 100 on the
    tested dryer - so Pastie never has to carry per-model service knowledge.
    """

    name: str
    interval: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.interval - self.used)

    @property
    def due(self) -> bool:
        return self.remaining == 0


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One reading of one appliance, already translated out of Haier's terms.

    `observed_at` is when *we* saw it, and it is what orders readings against
    each other: a poll and a pushed update can arrive in either order, and the
    older one must lose. It is always timezone-aware.
    """

    appliance_id: str
    observed_at: datetime
    state: ApplianceState
    trust: Trust = Trust.UNVERIFIED
    name: str = ""
    model: str = ""
    programme: str | None = None
    remaining: timedelta | None = None
    total: timedelta | None = None
    remaining_is_settled: bool = False
    progress: float | None = None
    door_open: bool | None = None
    remote_allowed: bool | None = None
    fault_code: str | None = None
    cycle_count: int | None = None
    maintenance: tuple[Maintenance, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("Snapshot.observed_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        """Identity of the *reading*, ignoring when it was taken.

        Two readings with the same fingerprint say the same thing, so the second
        one is a duplicate however it reached us. At-least-once delivery means
        duplicates are expected by design rather than a fault - the negotiated
        MQTT session offers no better guarantee - so this is not an optimisation.

        `raw` is deliberately excluded: Haier can add fields whenever they like,
        and a new diagnostic field appearing must not read as a state change.
        """
        parts = (
            self.appliance_id,
            self.state.value,
            self.programme or "",
            str(self.remaining),
            str(self.total),
            str(self.door_open),
            str(self.remote_allowed),
            self.fault_code or "",
            str(self.cycle_count),
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    @property
    def is_verified(self) -> bool:
        return self.trust is Trust.VERIFIED

    def display_remaining(self) -> str:
        """Time remaining, phrased honestly.

        Early in a cycle the machine is still measuring how wet the load is, and
        its estimate jumps about and can go up. Saying "42 minutes" then is a
        lie with a number attached, which is worse than saying nothing.
        """
        if self.remaining is None:
            return "unknown"
        minutes = int(self.remaining.total_seconds() // 60)
        if not self.remaining_is_settled:
            return f"about {minutes} min (still estimating)"
        return f"{minutes} min"
