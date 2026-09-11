"""The full water tank, and every alert having a look of its own.

Pinned against what the real HD90 sent on 2026-09-11 at 22:07:45, in one pushed
update, the moment its own tank alarm went off:

    pause 0 -> 1,  message 0 -> 4,  machMode 2 -> 3      (prPhase stayed at 19)

The earlier guess - that the tank was one of the community's "unknown" phases -
was wrong, and these tests are the record of what is actually true.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest

from pastie.connector.profiles import TUMBLE_DRYER, unverified
from pastie.connector.reading import RawReading, translate
from pastie.connector.scrub import scrub_parameters
from pastie.core.events import EventKind
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.state import ApplianceState
from pastie.core.tracker import Tracker, replay
from pastie.messengers.base import MessengerRunner, Result, for_event, per_event_defaults
from pastie.messengers.cast import CastMessenger, SpeechCache
from pastie.messengers.hue import COLOURS, HueMessenger
from tests.support import APPLIANCE, START, snapshot
from tests.test_messengers import FakeBridge, event_of, hue_with

#: Exactly the parameters that changed in the real push, on top of a running load.
RUNNING = {"machMode": "2", "pause": "0", "message": "0", "prPhase": "19"}
TANK_FULL = {"machMode": "3", "pause": "1", "message": "4", "prPhase": "19"}
IRON_DRY = {"machMode": "2", "pause": "0", "message": "1", "prPhase": "19"}


def reading(parameters: dict[str, str], minute: float = 0) -> RawReading:
    return RawReading(
        appliance_id=APPLIANCE,
        observed_at=START + timedelta(minutes=minute),
        parameters=dict(parameters),
        identity={"applianceTypeName": "TD", "modelName": "HD90-A2959R-UK"},
        programme_name="hqd_towel",
    )


def full(minute: float) -> Any:
    """A paused reading that says the tank is full."""
    return replace(snapshot(ApplianceState.PAUSED, minute), attention="the water tank is full")


def kinds(events: list[Any]) -> list[EventKind]:
    return [event.kind for event in events]


# ------------------------------------------------------------ translation


def test_the_real_tank_signature_reads_as_a_full_tank() -> None:
    tank = translate(reading(TANK_FULL), TUMBLE_DRYER)

    assert tank.state is ApplianceState.PAUSED
    assert tank.attention == "the water tank is full"


def test_the_iron_dry_notification_is_not_something_to_empty() -> None:
    """message 1 is "lightweight items are dry" - nothing is waiting on a person."""
    assert translate(reading(IRON_DRY), TUMBLE_DRYER).attention is None


def test_an_unverified_appliance_is_never_told_to_empty_anything() -> None:
    """A 4 meaning "empty the tank" on a dryer means nothing on an oven."""
    oven = translate(
        replace(reading(TANK_FULL), identity={"applianceTypeName": "OV"}), unverified("OV")
    )
    assert oven.attention is None


def test_the_allow_list_keeps_the_notification_code() -> None:
    """It was scrubbed out, so the journal saw the tank fill and wrote down "paused"."""
    assert scrub_parameters(TANK_FULL)["message"] == "4"


# ----------------------------------------------------------------- tracker


@pytest.fixture
def tracker() -> Tracker:
    return Tracker(MemoryStore(), Ledger())


def test_a_full_tank_is_announced_once_when_it_appears(tracker: Tracker) -> None:
    events = replay(tracker, [snapshot(ApplianceState.RUNNING, 0), full(40), full(42)])

    assert kinds(events) == [EventKind.NEEDS_EMPTYING]
    assert events[0].message == "The tumble dryer has stopped - the water tank is full."
    assert events[0].is_alert


def test_the_second_fill_in_the_same_load_is_announced_again(tracker: Tracker) -> None:
    """The second time is as urgent as the first."""
    events = replay(
        tracker,
        [
            snapshot(ApplianceState.RUNNING, 0),
            full(40),
            snapshot(ApplianceState.RUNNING, 45),  # emptied and restarted
            full(95),
        ],
    )
    assert kinds(events) == [EventKind.NEEDS_EMPTYING, EventKind.NEEDS_EMPTYING]


def test_emptying_it_and_carrying_on_is_not_a_new_cycle(tracker: Tracker) -> None:
    """Paused back to running is the same load resuming, not a start."""
    events = replay(
        tracker,
        [snapshot(ApplianceState.RUNNING, 0), full(40), snapshot(ApplianceState.RUNNING, 45)],
    )
    assert EventKind.CYCLE_STARTED not in kinds(events)


def test_a_restart_while_still_full_does_not_say_it_twice() -> None:
    memory, ledger = MemoryStore(), Ledger()
    replay(Tracker(memory, ledger), [snapshot(ApplianceState.RUNNING, 0), full(40)])

    assert replay(Tracker(memory, ledger), [full(50)]) == []


def test_a_tank_that_filled_while_pastie_was_off_is_announced_at_startup() -> None:
    """A deliberate exception to "the first reading announces nothing".

    That rule exists because a completion seen at startup may be days old. A
    full tank is not old news: the dryer is standing there stopped, now.
    """
    memory, ledger = MemoryStore(), Ledger()
    replay(Tracker(memory, ledger), [snapshot(ApplianceState.RUNNING, 0)])

    events = replay(Tracker(memory, ledger), [full(60)])

    assert kinds(events) == [EventKind.NEEDS_EMPTYING]


# -------------------------------------------- every alert looks like itself


BASE = {"enabled": True, "light": "light-1", "seconds": 0, "colour": "Green"}


async def flashed(kind: EventKind, settings: dict[str, Any]) -> Any:
    bridge = FakeBridge("bridge", "key")
    await MessengerRunner({"hue": hue_with(bridge)}).deliver(event_of(kind), {"hue": settings})
    return bridge.puts[0]["color"]["xy"]


def xy(name: str) -> dict[str, float]:
    x, y = COLOURS[name]
    return {"x": x, "y": y}


async def test_with_nothing_configured_each_alert_still_has_its_own_colour() -> None:
    """The regression: faults flashed green, the same as a finished cycle."""
    assert await flashed(EventKind.CYCLE_FINISHED, BASE) == xy("Green")
    assert await flashed(EventKind.FAULT, BASE) == xy("Red")
    assert await flashed(EventKind.NEEDS_EMPTYING, BASE) == xy("Cyan")
    assert await flashed(EventKind.MAINTENANCE_DUE, BASE) == xy("Blue")


async def test_a_colour_you_choose_beats_pastie_s_default() -> None:
    chosen = {**BASE, "when": {"needs_emptying": {"colour": "Purple"}}}
    assert await flashed(EventKind.NEEDS_EMPTYING, chosen) == xy("Purple")


def test_the_defaults_come_from_the_messenger_not_from_the_runner() -> None:
    assert per_event_defaults(HueMessenger(), event_of(EventKind.FAULT)) == {"colour": "Red"}
    assert per_event_defaults(HueMessenger(), event_of(EventKind.CYCLE_FINISHED)) == {}


def test_the_layers_stack_in_the_right_order() -> None:
    """Usual setting, then the default for this alert, then the user's choice."""
    config = {"colour": "Green", "when": {"fault": {"colour": "Orange"}}}
    event = event_of(EventKind.FAULT)

    assert for_event(config, event)["colour"] == "Orange"
    assert for_event(config, event, {"colour": "Red"})["colour"] == "Orange"
    assert for_event({"colour": "Green"}, event, {"colour": "Red"})["colour"] == "Red"


# ------------------------------------------------ and sounds like itself


async def said(kind: EventKind, text: str, tmp_path: Any) -> str:
    captured: list[str] = []
    speaker = CastMessenger(SpeechCache(tmp_path, renderer=lambda words: words.encode()))

    def announce(device: str, text: str, config: Mapping[str, Any]) -> Result:
        captured.append(text)
        return Result.worked()

    speaker._announce = announce  # type: ignore[method-assign]
    event = event_of(kind)
    event = replace(event, message="The tumble dryer has stopped - the water tank is full.")
    settings = {"enabled": True, "device": "Living Room speaker", "text": text}
    await MessengerRunner({"cast": speaker}).deliver(event, {"cast": settings})
    return captured[0]


async def test_a_full_tank_is_not_announced_with_the_finished_sentence(tmp_path: Any) -> None:
    words = await said(EventKind.NEEDS_EMPTYING, "Tumble dryer finished.", tmp_path)
    assert words == "The tumble dryer has stopped - the water tank is full."


async def test_a_finished_cycle_still_says_what_you_wrote(tmp_path: Any) -> None:
    assert await said(EventKind.CYCLE_FINISHED, "Dryer's done.", tmp_path) == "Dryer's done."


async def test_a_stray_brace_in_your_sentence_does_not_break_the_announcement(
    tmp_path: Any,
) -> None:
    words = await said(EventKind.CYCLE_FINISHED, "Done {or not}.", tmp_path)
    assert words == "Done {or not}."


# ------------------------------------------------------------------ journal


async def test_the_journal_now_records_the_notification_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The line it should have written on the night, and did not."""
    from tests.test_service import FakeConnector, build_watcher

    watcher = build_watcher(FakeConnector([reading(RUNNING, 0), reading(TANK_FULL, 1)]))
    with caplog.at_level(logging.INFO, logger="pastie.service.watcher"):
        await watcher.refresh()
        await watcher.refresh()

    assert "message 0 -> 4" in caplog.text
    assert "machMode 2 -> 3" in caplog.text


def test_the_demo_shows_the_real_tank_signature() -> None:
    from pastie.demo import run, scenarios

    events = run(scenarios()["tank"], out=lambda _line: None)
    assert kinds(events).count(EventKind.NEEDS_EMPTYING) == 2
