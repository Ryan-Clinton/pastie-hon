"""The pastie's ordeal: the jokes are allowed to be daft, not to be wrong."""

from __future__ import annotations

import pytest

from pastie.app.ordeal import REAL, Ordeal, ordeal_for


def meter(ordeal: Ordeal, label: str) -> int:
    return next(m.value for m in ordeal.meters if m.label == label)


def test_the_first_meter_is_the_real_progress() -> None:
    ordeal = ordeal_for("running", 0.37, seed="dryer/Cotton")

    assert ordeal.meters[0].label == REAL
    assert meter(ordeal, REAL) == 37


@pytest.mark.parametrize("progress", [0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0, 1.7, -0.3])
def test_every_meter_stays_between_0_and_100(progress: float) -> None:
    for state in ("running", "paused", "finished"):
        for m in ordeal_for(state, progress).meters:
            assert 0 <= m.value <= 100, (state, progress, m)


def test_no_number_means_no_meters_rather_than_a_false_zero() -> None:
    ordeal = ordeal_for("running", None)

    assert ordeal.meters == ()
    assert "still thinking" in ordeal.headline


def test_dread_peaks_in_the_middle_and_resolves_into_acceptance() -> None:
    dread = [meter(ordeal_for("running", p), "Existential dread") for p in (0.1, 0.5, 0.95)]

    assert dread[1] == 100
    assert dread[0] < dread[1]
    assert dread[2] < dread[1]


def test_the_socks_are_42_until_the_end() -> None:
    assert meter(ordeal_for("running", 0.3), "Sock escape probability") == 42
    assert meter(ordeal_for("finished", None), "Sock escape probability") == 100


def test_a_finished_cycle_is_done_whatever_the_last_reading_said() -> None:
    assert meter(ordeal_for("finished", 0.8), REAL) == 100


def test_a_full_tank_still_says_what_to_do() -> None:
    ordeal = ordeal_for("paused", 0.4, attention="the water tank is full")

    assert "Empty it" in ordeal.headline


def test_a_fault_still_says_what_to_do() -> None:
    ordeal = ordeal_for("fault", 0.4)

    assert "fault" in ordeal.headline
    assert "Check the machine" in ordeal.headline
    assert ordeal.meters == ()  # no cheerful numbers next to a broken machine


def test_a_refresh_does_not_change_the_story() -> None:
    first = ordeal_for("running", 0.40, seed="dryer/Duvet")
    again = ordeal_for("running", 0.45, seed="dryer/Duvet")  # same stage, next poll

    assert first.headline == again.headline


def test_each_stage_of_a_cycle_gets_its_own_line() -> None:
    lines = {ordeal_for("running", p, seed="dryer/Duvet").headline for p in (0.1, 0.5, 0.9)}

    assert len(lines) == 3


@pytest.mark.parametrize("state", ["idle", "scheduled", "unknown", "something-new"])
def test_quiet_states_have_a_line_and_no_meters(state: str) -> None:
    ordeal = ordeal_for(state, None)

    assert ordeal.headline
    assert ordeal.meters == ()
