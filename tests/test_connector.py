"""The boundary: Haier's fields in, plain language out.

These run a recorded cycle through translation and then through the brain, which
is the whole pipeline minus the network - and the only kind of test that can
catch a dependency update quietly changing how a field is decoded.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from pastie.connector.profiles import TUMBLE_DRYER, for_appliance, unverified
from pastie.connector.reading import RawReading, translate
from pastie.connector.scrub import scrub_identity, scrub_parameters, scrub_statistics
from pastie.core.events import EventKind
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.state import ApplianceState, Trust
from pastie.core.tracker import Tracker

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list[RawReading]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [RawReading.from_json(item) for item in data]


@pytest.fixture
def cycle() -> list[RawReading]:
    return load("dryer_cycle.json")


# ------------------------------------------------------------- translation


def test_a_recorded_cycle_translates_into_plain_language(cycle: list[RawReading]) -> None:
    states = [translate(reading, TUMBLE_DRYER).state for reading in cycle]
    assert states == [
        ApplianceState.IDLE,
        ApplianceState.RUNNING,
        ApplianceState.RUNNING,
        ApplianceState.FINISHED,
    ]


def test_time_remaining_is_only_reported_during_a_cycle(cycle: list[RawReading]) -> None:
    """Idle, the machine reports the programme's nominal length, not a countdown."""
    idle = translate(cycle[0], TUMBLE_DRYER)
    assert idle.remaining is None
    assert idle.display_remaining() == "unknown"


def test_an_estimate_above_the_programme_length_is_flagged_as_unsettled(
    cycle: list[RawReading],
) -> None:
    """Early on the machine is still measuring the load, and its guess wanders."""
    sensing = translate(cycle[1], TUMBLE_DRYER)
    assert sensing.remaining == timedelta(minutes=120)
    assert sensing.total == timedelta(minutes=90)
    assert not sensing.remaining_is_settled
    assert sensing.display_remaining() == "about 120 min (still estimating)"
    assert sensing.progress is None


def test_a_settled_estimate_gives_an_honest_progress_figure(
    cycle: list[RawReading],
) -> None:
    settled = translate(cycle[2], TUMBLE_DRYER)
    assert settled.remaining_is_settled
    assert settled.display_remaining() == "45 min"
    assert settled.progress == pytest.approx(0.5)


def test_the_programme_and_the_appliance_get_names_a_person_would_use(
    cycle: list[RawReading],
) -> None:
    running = translate(cycle[1], TUMBLE_DRYER)
    assert running.programme == "Mixed load"
    assert running.name == "tumble dryer"
    assert running.model == "HD90-A2959R-UK"

    idle = translate(cycle[0], TUMBLE_DRYER)
    assert idle.programme is None  # "No Program" is not a programme


def test_the_counter_and_the_service_schedule_come_off_the_statistics_endpoint(
    cycle: list[RawReading],
) -> None:
    finished = translate(cycle[3], TUMBLE_DRYER)
    assert finished.cycle_count == 4
    assert [item.name for item in finished.maintenance] == ["a filter clean", "a drum clean"]
    assert finished.maintenance[0].remaining == 11
    assert not finished.maintenance[0].due


def test_the_arming_flag_is_reported_and_clears_after_a_cycle(
    cycle: list[RawReading],
) -> None:
    """It disarms itself once the load is done: once per load, somebody walks over."""
    assert translate(cycle[1], TUMBLE_DRYER).remote_allowed is True
    assert translate(cycle[3], TUMBLE_DRYER).remote_allowed is False


def test_an_unconfirmed_phase_is_labelled_unconfirmed_in_the_diagnostics(
    cycle: list[RawReading],
) -> None:
    """The tested machine's phase numbers look reversed against the shared mapping."""
    running = translate(cycle[1], TUMBLE_DRYER)
    assert running.raw["phase"] == "drying (unconfirmed)"
    assert running.raw["prPhase"] == "19"


# ------------------------------------------------------------------- trust


def test_an_unverified_appliance_type_is_named_but_not_interpreted() -> None:
    oven = unverified("OV")
    reading = RawReading(
        appliance_id="oven-1",
        observed_at=load("dryer_cycle.json")[0].observed_at,
        parameters={"machMode": "6", "errors": "E4"},
        identity={"applianceTypeName": "OV", "modelName": "SOMETHING"},
    )
    snapshot = translate(reading, oven)

    assert snapshot.name == "oven"  # detected and named
    assert snapshot.state is ApplianceState.UNKNOWN  # but not interpreted
    assert snapshot.trust is Trust.UNVERIFIED
    assert snapshot.fault_code is None  # and never alerted on
    assert snapshot.raw["machMode"] == "6"  # raw values still shown


def test_an_unknown_appliance_type_still_gets_a_profile() -> None:
    profile = for_appliance("SOMETHING-NEW")
    assert profile.trust is Trust.UNVERIFIED
    assert profile.commands == frozenset()


def test_the_dryer_only_offers_commands_that_were_tested() -> None:
    assert TUMBLE_DRYER.commands == {"startProgram", "stopProgram"}


# ------------------------------------------------------------------ scrub


def test_the_allow_list_drops_everything_it_has_not_been_shown() -> None:
    """A field nobody has looked at is dropped, including one added tomorrow."""
    appliance = {
        "applianceTypeName": "TD",
        "modelName": "HD90-A2959R-UK",
        "coords": {"lat": 55.86, "lng": -4.25},
        "macAddress": "78-1c-3c-c1-92-b8",
        "serialNumber": "ABC123456",
        "PK": "user#eu-west-1:c0f806c3",
        "somethingHaierAddedTomorrow": "your address, probably",
    }

    kept = scrub_identity(appliance)

    assert kept == {"applianceTypeName": "TD", "modelName": "HD90-A2959R-UK"}


def test_parameters_come_out_as_plain_strings() -> None:
    class Attribute:
        """The client hands back its own objects as often as plain values."""

        def __init__(self, value: str) -> None:
            self.value = value

    kept = scrub_parameters({"machMode": Attribute("2"), "gpsThing": Attribute("55.86")})
    assert kept == {"machMode": "2"}


def test_statistics_are_allow_listed_too() -> None:
    assert scrub_statistics({"programsCounter": 4, "lastCheckup": "2026-01-01"}) == {
        "programsCounter": 4
    }
    assert scrub_statistics(None) == {}


# --------------------------------------------------- the whole way through


def test_a_recorded_cycle_produces_exactly_one_announcement(
    cycle: list[RawReading],
) -> None:
    """Four readings, one thing worth saying."""
    tracker = Tracker(MemoryStore(), Ledger())
    events = [
        event for reading in cycle for event in tracker.observe(translate(reading, TUMBLE_DRYER))
    ]

    assert [event.kind for event in events] == [
        EventKind.CYCLE_STARTED,
        EventKind.CYCLE_FINISHED,
    ]
    assert [event.message for event in events if event.is_alert] == [
        "The tumble dryer has finished."
    ]


def test_replaying_the_same_recording_twice_announces_nothing_new(
    cycle: list[RawReading],
) -> None:
    """The ledger is what makes a re-read of the same history harmless."""
    memory, ledger = MemoryStore(), Ledger()
    for _ in range(2):
        tracker = Tracker(memory, ledger)
        events = [
            event
            for reading in cycle
            for event in tracker.observe(translate(reading, TUMBLE_DRYER))
        ]
    assert events == []
