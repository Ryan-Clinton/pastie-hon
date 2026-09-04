"""Builders for recorded sequences.

The tests check *what Pastie announced*, never what it parsed. That is the
distinction that makes them worth having: a dependency update that quietly
changes how a field is decoded shows up here as a missing or duplicated
announcement, which is the thing a user would actually notice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pastie.core.state import ApplianceState, Maintenance, Snapshot, Trust

APPLIANCE = "dryer-1"
START = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    """A moment `minutes` after the start of the recorded sequence."""
    return START + timedelta(minutes=minutes)


def snapshot(
    state: ApplianceState,
    minute: float = 0,
    *,
    cycle_count: int | None = None,
    trust: Trust = Trust.VERIFIED,
    programme: str | None = "Mixed",
    fault_code: str | None = None,
    remaining: timedelta | None = None,
    remaining_is_settled: bool = True,
    remote_allowed: bool | None = True,
    maintenance: tuple[Maintenance, ...] = (),
    name: str = "tumble dryer",
    observed_at: datetime | None = None,
) -> Snapshot:
    return Snapshot(
        appliance_id=APPLIANCE,
        observed_at=observed_at or at(minute),
        state=state,
        trust=trust,
        name=name,
        model="HD90-A2959R-UK",
        programme=programme,
        remaining=remaining,
        remaining_is_settled=remaining_is_settled,
        remote_allowed=remote_allowed,
        fault_code=fault_code,
        cycle_count=cycle_count,
        maintenance=maintenance,
    )
