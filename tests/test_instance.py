"""One service, and the window's ability to start it.

The design rests on a single connection to Haier. Two services would put back
the thing the app/service split exists to prevent - two opinions about what the
machine is doing - and add two ledgers racing to announce the same cycle.

Nothing enforced that until the window started launching the service itself.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from pastie.app.launch import service_command, start_service_if_needed
from pastie.service.instance import AlreadyRunningError, is_running, only_one

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the guard is a Windows named mutex"
)


@pytest.fixture
def claim() -> str:
    """A mutex name of this test's own.

    Never the real one: these would otherwise compete with whatever service the
    developer happens to have running, and fail for a reason that has nothing to
    do with what they are testing.
    """
    return rf"Local\pastie-test-{uuid.uuid4().hex}"


@windows_only
def test_a_second_service_is_refused_rather_than_queued(claim: str) -> None:
    with only_one(claim), pytest.raises(AlreadyRunningError, match="only be one"), only_one(claim):
        pass


@windows_only
def test_the_claim_is_released_when_the_service_stops(claim: str) -> None:
    with only_one(claim):
        pass
    with only_one(claim):  # the next one starts cleanly
        pass


@windows_only
def test_asking_whether_one_is_running_does_not_become_one(claim: str) -> None:
    """`is_running` opens the mutex rather than creating it.

    A check that accidentally makes the claim would report "already running" to
    the very process about to start, which is the worst possible answer.
    """
    assert is_running(claim) is False
    assert is_running(claim) is False  # asking twice still says no

    with only_one(claim):
        assert is_running(claim) is True

    assert is_running(claim) is False


def test_the_service_is_started_with_this_interpreter() -> None:
    """Not `pastie.exe` on the PATH: a venv install must start its own service."""
    command = service_command()

    assert command[1:] == ["-m", "pastie.cli", "service"]
    assert Path(command[0]).exists()


def test_a_console_window_is_not_flashed_up_where_it_can_be_avoided() -> None:
    executable = Path(service_command()[0])
    if (executable.parent / "pythonw.exe").exists():
        assert executable.name == "pythonw.exe"


def test_nothing_is_started_when_a_service_is_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[Any] = []
    monkeypatch.setattr("pastie.app.launch.is_running", lambda: True)
    monkeypatch.setattr("subprocess.Popen", lambda *args, **_kwargs: started.append(args))

    assert start_service_if_needed() is False
    assert started == []


def test_a_service_that_will_not_start_does_not_stop_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A window that refuses to open is worse than one saying the service is down."""

    def refuse(*_a: Any, **_k: Any) -> None:
        raise OSError("no such executable")

    monkeypatch.setattr("pastie.app.launch.is_running", lambda: False)
    monkeypatch.setattr("subprocess.Popen", refuse)

    assert start_service_if_needed() is False
