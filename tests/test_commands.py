"""Commands are not done until the machine says so.

The scenario that matters most here is the last line of section 13: Haier
accepting a command the machine then ignores. It has actually happened - a stop
command returned success while the dryer carried on - so it is the default
assumption, not an edge case.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from pastie.core.commands import (
    CommandOutcome,
    CommandTracker,
    start_programme,
    stop_programme,
)
from pastie.core.state import ApplianceState
from tests.support import APPLIANCE, at, snapshot


def test_a_command_is_only_confirmed_by_the_machine_changing_state() -> None:
    tracker = CommandTracker()
    idle = snapshot(ApplianceState.IDLE, 0)

    progress = tracker.request(start_programme("Mixed"), APPLIANCE, at(0), idle)
    lifecycle = [progress.outcome]

    tracker.accepted(APPLIANCE, at(0.05))
    lifecycle.append(progress.outcome)
    assert not progress.outcome.succeeded  # accepted by Haier is not done

    settled = tracker.observe(snapshot(ApplianceState.RUNNING, 0.1))
    lifecycle.append(progress.outcome)

    assert settled is progress
    assert lifecycle == [
        CommandOutcome.REQUESTED,
        CommandOutcome.ACCEPTED,
        CommandOutcome.CONFIRMED,
    ]
    assert progress.outcome.succeeded


def test_haier_accepting_a_command_the_machine_ignores_times_out() -> None:
    tracker = CommandTracker()
    running = snapshot(ApplianceState.RUNNING, 0)

    tracker.request(stop_programme(), APPLIANCE, at(0), running)
    tracker.accepted(APPLIANCE, at(0))

    # The machine keeps running. Every reading says so.
    assert tracker.observe(snapshot(ApplianceState.RUNNING, 0.1)) is None
    settled = tracker.observe(snapshot(ApplianceState.RUNNING, 0.5))

    assert settled is not None
    assert settled.outcome is CommandOutcome.TIMED_OUT
    assert settled.lines()[-1] == (
        "Accepted by Haier, but the machine didn't react within 20 seconds"
    )


def test_the_deadline_runs_from_acceptance_not_from_the_request() -> None:
    """A slow network is not the same as an appliance ignoring us."""
    tracker = CommandTracker()
    spec = stop_programme()
    tracker.request(spec, APPLIANCE, at(0), snapshot(ApplianceState.RUNNING, 0))
    tracker.accepted(APPLIANCE, at(1))  # a minute to be taken

    assert tracker.observe(snapshot(ApplianceState.RUNNING, 1.2)) is None
    assert tracker.observe(snapshot(ApplianceState.IDLE, 1.3)) is not None


def test_a_start_is_refused_when_the_machine_is_not_armed() -> None:
    """The interlock belongs to the appliance. Pastie explains it, never defeats it."""
    tracker = CommandTracker()
    not_armed = snapshot(ApplianceState.IDLE, 0, remote_allowed=False)

    progress = tracker.request(start_programme("Mixed"), APPLIANCE, at(0), not_armed)

    assert progress.outcome is CommandOutcome.REFUSED
    assert progress.reason is not None
    assert "dial to the remote position" in progress.reason
    assert tracker.active(APPLIANCE) is None  # nothing was sent


def test_a_rejection_from_haier_is_reported_as_such() -> None:
    tracker = CommandTracker()
    tracker.request(stop_programme(), APPLIANCE, at(0), snapshot(ApplianceState.RUNNING, 0))

    progress = tracker.rejected(APPLIANCE, at(0.1), "the server said no")

    assert progress is not None
    assert progress.outcome is CommandOutcome.REJECTED
    assert progress.confirmed_at is None


def test_the_progress_display_shows_which_steps_actually_happened() -> None:
    tracker = CommandTracker()
    progress = tracker.request(
        start_programme("Mixed"), APPLIANCE, at(0), snapshot(ApplianceState.IDLE, 0)
    )
    tracker.accepted(APPLIANCE, at(0.05))
    tracker.observe(snapshot(ApplianceState.RUNNING, 0.1))

    assert progress.lines() == [
        "Start requested         20:00:00",
        "Accepted by Haier       20:00:03",
        "Machine confirmed       20:00:06   OK",
    ]


def test_readings_for_another_appliance_do_not_settle_this_command() -> None:
    tracker = CommandTracker()
    tracker.request(stop_programme(), APPLIANCE, at(0), snapshot(ApplianceState.RUNNING, 0))
    tracker.accepted(APPLIANCE, at(0))

    other = replace(snapshot(ApplianceState.IDLE, 10), appliance_id="washer-2")
    assert tracker.observe(other) is None
    assert tracker.active(APPLIANCE) is not None


def test_history_records_every_attempt_including_the_refused_ones() -> None:
    tracker = CommandTracker()
    unarmed = snapshot(ApplianceState.IDLE, 0, remote_allowed=False)
    tracker.request(start_programme("Mixed"), APPLIANCE, at(0), unarmed)
    tracker.request(stop_programme(), APPLIANCE, at(1), snapshot(ApplianceState.RUNNING, 1))
    tracker.accepted(APPLIANCE, at(1))
    tracker.observe(snapshot(ApplianceState.IDLE, 1.1))

    outcomes = [progress.outcome for progress in tracker.history]
    assert outcomes == [CommandOutcome.REFUSED, CommandOutcome.CONFIRMED]


def test_a_command_with_a_longer_deadline_waits_longer() -> None:
    tracker = CommandTracker()
    patient = replace(stop_programme(), deadline=timedelta(minutes=2))
    tracker.request(patient, APPLIANCE, at(0), snapshot(ApplianceState.RUNNING, 0))
    tracker.accepted(APPLIANCE, at(0))

    assert tracker.observe(snapshot(ApplianceState.RUNNING, 1)) is None
    assert tracker.observe(snapshot(ApplianceState.RUNNING, 2)) is not None
