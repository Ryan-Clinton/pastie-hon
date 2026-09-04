"""The scenarios the specification says a build is not finished without.

Every test here is one line from section 13 of `docs/SPEC.md`, in the same
order. They are about timing and restarts, which is where the dangerous bugs in
this project live - not about parsing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest

from pastie.core.events import Event, EventKind
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.state import ApplianceState, Maintenance, Trust
from pastie.core.tracker import Tracker, replay
from tests.support import APPLIANCE, at, snapshot


@pytest.fixture
def memory() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def ledger() -> Ledger:
    return Ledger()


@pytest.fixture
def tracker(memory: MemoryStore, ledger: Ledger) -> Tracker:
    return Tracker(memory, ledger)


def kinds(events: Sequence[Event]) -> list[EventKind]:
    return [event.kind for event in events]


# --------------------------------------------------------------- starting up


def test_starting_up_while_the_machine_is_idle_says_nothing(tracker: Tracker) -> None:
    assert replay(tracker, [snapshot(ApplianceState.IDLE, 0)]) == []


def test_starting_up_while_it_is_already_finished_stays_silent(tracker: Tracker) -> None:
    """The false alarm: that load may have been put away on Tuesday."""
    events = replay(tracker, [snapshot(ApplianceState.FINISHED, 0, cycle_count=3)])
    assert events == []


def test_starting_up_mid_cycle_and_restarting_mid_cycle_stays_silent(
    memory: MemoryStore, ledger: Ledger
) -> None:
    first = Tracker(memory, ledger)
    replay(first, [snapshot(ApplianceState.RUNNING, 0, cycle_count=3)])

    # Same memory and ledger, new session: Pastie was restarted mid-cycle.
    second = Tracker(memory, ledger)
    assert replay(second, [snapshot(ApplianceState.RUNNING, 5, cycle_count=3)]) == []


# ------------------------------------------------------------- live changes


def test_running_to_finished_announces_once(tracker: Tracker) -> None:
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FINISHED, 40, cycle_count=4),
        ],
    )
    assert kinds(events) == [EventKind.CYCLE_FINISHED]
    assert events[0].message == "The tumble dryer has finished."
    assert events[0].is_alert


def test_running_to_fault_announces_the_code(tracker: Tracker) -> None:
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FAULT, 10, cycle_count=3, fault_code="E4"),
        ],
    )
    assert kinds(events) == [EventKind.FAULT]
    assert "E4" in events[0].message


def test_starting_a_cycle_is_reported_but_is_not_an_alert(tracker: Tracker) -> None:
    """Worth showing in the window; not worth shouting across the house."""
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.IDLE, 0, cycle_count=3),
            snapshot(ApplianceState.RUNNING, 1, cycle_count=3),
        ],
    )
    assert kinds(events) == [EventKind.CYCLE_STARTED]
    assert not events[0].is_alert


# ------------------------------------------------------- duplicates and order


def test_the_same_update_arriving_twice_announces_once(tracker: Tracker) -> None:
    """At-least-once delivery: duplicates are the contract, not a fault."""
    finished = snapshot(ApplianceState.FINISHED, 40, cycle_count=4)
    events = replay(
        tracker,
        [snapshot(ApplianceState.RUNNING, 0, cycle_count=3), finished, finished],
    )
    assert kinds(events) == [EventKind.CYCLE_FINISHED]


def test_updates_arriving_out_of_order_do_not_undo_a_newer_one(tracker: Tracker) -> None:
    """A poll describing an older moment must not resurrect the old state."""
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FINISHED, 40, cycle_count=4),
            snapshot(ApplianceState.RUNNING, 20, cycle_count=3),  # late poll
            snapshot(ApplianceState.FINISHED, 41, cycle_count=4),
        ],
    )
    assert kinds(events) == [EventKind.CYCLE_FINISHED]


def test_the_periodic_check_disagreeing_with_the_push_keeps_the_newer_reading(
    tracker: Tracker, memory: MemoryStore
) -> None:
    replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FINISHED, 40, cycle_count=4),  # pushed
            snapshot(ApplianceState.RUNNING, 39, cycle_count=3),  # poll, older
        ],
    )
    assert memory.get(APPLIANCE).state is ApplianceState.FINISHED


# ------------------------------------------------------- gaps and reconnects


def test_the_connection_dropping_and_coming_back_does_not_re_announce(
    tracker: Tracker,
) -> None:
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FINISHED, 40, cycle_count=4),
        ],
    )
    assert kinds(events) == [EventKind.CYCLE_FINISHED]

    tracker.connection_lost(APPLIANCE)
    # The reconnect refreshes in full, because the MQTT session replays nothing.
    assert replay(tracker, [snapshot(ApplianceState.FINISHED, 45, cycle_count=4)]) == []


def test_a_cycle_finishing_while_pastie_is_switched_off_is_reported_as_a_gap(
    memory: MemoryStore, ledger: Ledger
) -> None:
    first = Tracker(memory, ledger)
    replay(first, [snapshot(ApplianceState.RUNNING, 10, cycle_count=3)])

    # Pastie is off for an hour. The counter moved, so this is a fact.
    second = Tracker(memory, ledger)
    events = replay(second, [snapshot(ApplianceState.FINISHED, 70, cycle_count=4)])

    assert kinds(events) == [EventKind.CYCLE_FINISHED_WHILE_AWAY]
    assert events[0].message == (
        "The tumble dryer finished while Pastie wasn't running (one cycle, some time after 20:10)."
    )


def test_two_cycles_while_away_are_counted(memory: MemoryStore, ledger: Ledger) -> None:
    replay(Tracker(memory, ledger), [snapshot(ApplianceState.RUNNING, 10, cycle_count=3)])
    events = replay(
        Tracker(memory, ledger), [snapshot(ApplianceState.FINISHED, 400, cycle_count=5)]
    )
    assert "2 cycles" in events[0].message


def test_a_gap_without_a_counter_is_reported_honestly(memory: MemoryStore, ledger: Ledger) -> None:
    """No counter means no claim about how many - only that it happened."""
    replay(Tracker(memory, ledger), [snapshot(ApplianceState.RUNNING, 10)])
    events = replay(Tracker(memory, ledger), [snapshot(ApplianceState.FINISHED, 70)])

    assert kinds(events) == [EventKind.CYCLE_FINISHED_WHILE_AWAY]
    assert events[0].message == (
        "The tumble dryer finished while Pastie wasn't running. "
        "Last seen running at 20:10. Time of completion unknown."
    )


def test_a_completion_announced_live_is_not_announced_again_after_a_restart(
    memory: MemoryStore, ledger: Ledger
) -> None:
    """The ledger and the gap detector share a key space on purpose."""
    live = Tracker(memory, ledger)
    replay(
        live,
        [
            snapshot(ApplianceState.RUNNING, 0, cycle_count=3),
            snapshot(ApplianceState.FINISHED, 40, cycle_count=4),
        ],
    )
    # The restart sees the same completed cycle in the counter.
    restarted = Tracker(memory, ledger)
    assert replay(restarted, [snapshot(ApplianceState.FINISHED, 50, cycle_count=4)]) == []


def test_a_cancelled_cycle_while_away_is_not_called_a_completion(
    memory: MemoryStore, ledger: Ledger
) -> None:
    """Counter unmoved: whatever happened, nothing finished."""
    replay(Tracker(memory, ledger), [snapshot(ApplianceState.RUNNING, 10, cycle_count=3)])
    events = replay(Tracker(memory, ledger), [snapshot(ApplianceState.IDLE, 70, cycle_count=3)])
    assert events == []


# ------------------------------------------------------------------- trust


def test_an_unverified_appliance_gets_no_interpreted_state_or_alerts(
    tracker: Tracker,
) -> None:
    """Mode 6 meaning a fault on a dryer is no reason to alarm an oven owner."""
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0, trust=Trust.UNVERIFIED),
            snapshot(ApplianceState.FINISHED, 40, trust=Trust.UNVERIFIED),
            snapshot(ApplianceState.FAULT, 50, trust=Trust.UNVERIFIED, fault_code="E4"),
        ],
    )
    assert events == []


# ------------------------------------------------------------- maintenance


def test_maintenance_is_announced_once_per_service_period(tracker: Tracker) -> None:
    due = (Maintenance(name="a filter clean", interval=15, used=15),)
    events = replay(
        tracker,
        [
            snapshot(
                ApplianceState.RUNNING,
                0,
                cycle_count=15,
                maintenance=due,
                remaining=timedelta(minutes=30),
            ),
            snapshot(
                ApplianceState.RUNNING,
                20,
                cycle_count=15,
                maintenance=due,
                remaining=timedelta(minutes=10),
            ),
        ],
    )
    assert kinds(events) == [EventKind.MAINTENANCE_DUE]
    assert events[0].message == "The tumble dryer is due a filter clean (every 15 cycles)."


def test_maintenance_not_due_is_not_announced(tracker: Tracker) -> None:
    not_due = (Maintenance(name="a drum clean", interval=100, used=7),)
    assert replay(tracker, [snapshot(ApplianceState.IDLE, 0, maintenance=not_due)]) == []


# -------------------------------------------------------------- persistence


def test_memory_survives_a_restart_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    first = Tracker(MemoryStore(path), Ledger(tmp_path / "ledger.json"))
    replay(first, [snapshot(ApplianceState.RUNNING, 10, cycle_count=3)])

    reloaded = MemoryStore(path)
    assert reloaded.get(APPLIANCE).state is ApplianceState.RUNNING
    assert reloaded.get(APPLIANCE).cycle_count == 3
    assert reloaded.get(APPLIANCE).last_running_at == at(10)


def test_a_snapshot_must_carry_a_timezone() -> None:
    """Naive datetimes are the classic source of an hour-out announcement."""
    from datetime import datetime as naive_datetime

    from pastie.core.state import Snapshot

    with pytest.raises(ValueError, match="timezone-aware"):
        Snapshot(
            appliance_id=APPLIANCE,
            observed_at=naive_datetime(2026, 9, 4, 20, 0),  # noqa: DTZ001
            state=ApplianceState.IDLE,
        )


def test_remaining_time_is_not_quoted_as_fact_while_the_machine_is_guessing() -> None:
    early = snapshot(
        ApplianceState.RUNNING,
        1,
        remaining=timedelta(minutes=42),
        remaining_is_settled=False,
    )
    assert early.display_remaining() == "about 42 min (still estimating)"

    later = snapshot(ApplianceState.RUNNING, 30, remaining=timedelta(minutes=12))
    assert later.display_remaining() == "12 min"
