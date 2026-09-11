"""What Pastie remembers about an appliance between runs.

This is the difference between "the dryer has finished" and "the dryer finished
at some point while I wasn't looking". Without it, every restart either invents
a completion that happened days ago or silently misses one that happened ten
minutes ago.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pastie.core.state import ApplianceState, Snapshot
from pastie.core.store import JsonFile


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@dataclass
class ApplianceMemory:
    """The last thing Pastie knew, and when.

    `cycle_count` is the valuable one. If it has moved while Pastie was off, a
    cycle finished, and that can be said as a fact rather than hedged.
    """

    appliance_id: str
    state: ApplianceState = ApplianceState.UNKNOWN
    observed_at: datetime | None = None
    cycle_count: int | None = None
    last_running_at: datetime | None = None
    fingerprint: str | None = None
    #: What the machine was waiting on at the last reading. Kept so a restart
    #: while the tank is still full does not announce it a second time.
    attention: str | None = None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        for key in ("observed_at", "last_running_at"):
            value = getattr(self, key)
            data[key] = value.isoformat() if value else None
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ApplianceMemory:
        try:
            state = ApplianceState(data.get("state", "unknown"))
        except ValueError:
            # An unrecognised state from a newer version reads as "no idea",
            # which re-baselines silently instead of guessing.
            state = ApplianceState.UNKNOWN
        count = data.get("cycle_count")
        return cls(
            appliance_id=str(data.get("appliance_id", "")),
            state=state,
            observed_at=_parse_time(data.get("observed_at")),
            cycle_count=count if isinstance(count, int) else None,
            last_running_at=_parse_time(data.get("last_running_at")),
            fingerprint=data.get("fingerprint") or None,
            attention=data.get("attention") or None,
        )

    def updated_with(self, snapshot: Snapshot) -> ApplianceMemory:
        """The memory implied by having just seen `snapshot`.

        `cycle_count` and `last_running_at` are carried forward when the new
        reading does not mention them: statistics are fetched on their own
        schedule, and a live update that omits the counter is not evidence that
        the counter went away.
        """
        return ApplianceMemory(
            appliance_id=snapshot.appliance_id,
            state=snapshot.state,
            observed_at=snapshot.observed_at,
            cycle_count=(
                snapshot.cycle_count if snapshot.cycle_count is not None else self.cycle_count
            ),
            last_running_at=(
                snapshot.observed_at
                if snapshot.state is ApplianceState.RUNNING
                else self.last_running_at
            ),
            fingerprint=snapshot.fingerprint,
            # Not carried forward: the tank being emptied is exactly the change
            # that has to be recorded, so the next fill is news again.
            attention=snapshot.attention,
        )


class MemoryStore:
    """Per-appliance memory, persisted as one small JSON document."""

    def __init__(self, path: Path | None = None) -> None:
        self._file = JsonFile(path)
        raw = self._file.load()
        self._memories: dict[str, ApplianceMemory] = {}
        for appliance_id, data in raw.items():
            if isinstance(data, dict):
                memory = ApplianceMemory.from_json(data)
                memory.appliance_id = appliance_id
                self._memories[appliance_id] = memory

    def get(self, appliance_id: str) -> ApplianceMemory:
        return self._memories.get(appliance_id) or ApplianceMemory(appliance_id=appliance_id)

    def put(self, memory: ApplianceMemory) -> None:
        self._memories[memory.appliance_id] = memory
        self._file.save({k: v.to_json() for k, v in self._memories.items()})
