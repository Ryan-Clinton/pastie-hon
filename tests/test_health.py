"""Pastie must always be able to say which kind of broken it is.

Each of these states needs a different response from whoever reads it - change
a password, check the router, open an issue - so getting one confused for
another wastes the user's time in a specific and annoying way.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from pastie.core.health import Health, HealthMonitor, classify
from tests.support import at


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PermissionError("401 Unauthorized"), Health.AUTH),
        (RuntimeError("authentication failed"), Health.AUTH),
        (RuntimeError("password rejected"), Health.AUTH),
        (TimeoutError("read timed out"), Health.OFFLINE),
        (OSError("Connection refused"), Health.OFFLINE),
        (RuntimeError("failed to resolve host"), Health.OFFLINE),
        (KeyError("machMode"), Health.SCHEMA),
        (TypeError("'NoneType' object is not subscriptable"), Health.SCHEMA),
        (RuntimeError("something nobody has seen before"), Health.SCHEMA),
    ],
)
def test_failures_are_classified_by_what_the_user_can_do_about_them(
    error: Exception, expected: Health
) -> None:
    state, _ = classify(error)
    assert state is expected


def test_an_unrecognised_failure_reads_as_a_changed_response_not_a_shrug() -> None:
    """The failure this project should expect most is Haier moving something."""
    state, detail = classify(RuntimeError("boom"))
    assert state is Health.SCHEMA
    assert "RuntimeError" in detail


def test_updates_going_quiet_is_slow_not_broken() -> None:
    monitor = HealthMonitor(stale_after=timedelta(minutes=10))
    monitor.ok(at(0))

    assert monitor.degraded(at(5), last_update=at(0)).state is Health.OK
    report = monitor.degraded(at(20), last_update=at(0))
    assert report.state is Health.SLOW
    assert report.state.is_working
    assert report.message == "Working, but updates are slow - nothing new for 20 min"


def test_recovering_clears_the_state_and_stamps_the_change() -> None:
    monitor = HealthMonitor()
    monitor.failed(at(0), TimeoutError("read timed out"))
    assert monitor.report.state is Health.OFFLINE

    recovered = monitor.ok(at(5))
    assert recovered.state is Health.OK
    assert recovered.since == at(5)


def test_the_same_failure_repeating_does_not_reset_when_it_started() -> None:
    """ "Offline since 20:00" is useful; "offline since 4 seconds ago" is not."""
    monitor = HealthMonitor()
    first = monitor.failed(at(0), TimeoutError("timed out"))
    again = monitor.failed(at(9), TimeoutError("timed out"))

    assert again.since == first.since == at(0)


def test_every_state_has_words_a_user_can_act_on() -> None:
    monitor = HealthMonitor()
    monitor.failed(at(0), RuntimeError("401 Unauthorized"))
    assert monitor.report.message.startswith("Can't log in")
