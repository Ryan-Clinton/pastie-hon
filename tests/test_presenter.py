"""The presenter keeps the delight contract (SPEC 17-20, UI-SPEC 10.1 and 13)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pastie.app import voice
from pastie.app.memory import WindowMemory
from pastie.app.presenter import LEVELS, Presenter, curve

T0 = datetime(2026, 9, 25, 18, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.at = T0

    def __call__(self) -> datetime:
        return self.at

    def tick(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


def dryer(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "dryer-1",
        "name": "tumble dryer",
        "model": "HD90-A2959R-UK",
        "state": "idle",
        "trust": "verified",
        "updated_at": T0.isoformat(),
        "programme": None,
        "remaining": "unknown",
        "remaining_minutes": None,
        "remaining_settled": False,
        "progress": None,
        "remote_allowed": False,
        "fault_code": None,
        "attention": None,
        "cycle_count": 104,
        "maintenance": [],
        "raw": {},
        "programmes": [
            {
                "id": "hqd_duvet",
                "label": "Duvet",
                "dry_levels": [],
                "temperatures": [{"id": "4", "label": "High", "recommended": True}],
                "durations": [
                    {"id": "60", "label": "60 min", "recommended": True},
                    {"id": "90", "label": "90 min", "recommended": False},
                ],
            }
        ],
        "commands": ["startProgram", "stopProgram"],
    }
    base.update(overrides)
    return base


def status(*appliances: dict[str, Any], health: str = "ok", **extra: Any) -> dict[str, Any]:
    return {
        "health": health,
        "health_message": "",
        "appliances": list(appliances),
        "recent": extra.pop("recent", []),
        "command": [],
        "command_detail": extra.pop("command_detail", None),
    }


def presenter(tmp_path: Path | None = None, level: str = "dry") -> tuple[Presenter, Clock]:
    clock = Clock()
    memory = WindowMemory(tmp_path / "window.json" if tmp_path else None)
    p = Presenter(memory, now=clock)
    p.set_level(level)
    return p, clock


def connected(p: Presenter, clock: Clock) -> None:
    """Get past the connecting stages, as a real first reply does."""
    p.screen(status(dryer()))
    clock.tick(2)


RUNNING = {
    "state": "running",
    "programme": "Mixed load",
    "remaining_minutes": 47,
    "remaining_settled": False,
    "progress": 0.54,
}


# ------------------------------------------------------------- facts first


@pytest.mark.parametrize(
    "shape",
    [
        {},
        RUNNING,
        {**RUNNING, "remaining_settled": True},
        {"state": "finished", "programme": "Mixed load", "progress": 1.0},
        {"state": "fault", "fault_code": "E3"},
        {"state": "paused", "attention": "the water tank is full", "progress": 0.4},
        {"trust": "unverified", "state": "unknown", "raw": {"machMode": "6"}},
    ],
)
def test_every_level_shows_the_same_facts(shape: dict[str, Any]) -> None:
    facts = []
    for level in LEVELS:
        p, clock = presenter(level=level)
        connected(p, clock)
        hero = p.screen(status(dryer(**shape)))["hero"]
        facts.append((hero["state_word"], hero["facts"], hero["actions"]["mode"]))
    assert facts[0] == facts[1] == facts[2]


def test_an_older_service_s_own_phrasing_is_shown_as_sent() -> None:
    p, clock = presenter()
    connected(p, clock)
    old = dryer(state="running", programme="Mixed load", progress=0.5, remaining="45 min")
    del old["remaining_minutes"]
    facts = p.screen(status(old))["hero"]["facts"]
    assert facts["remaining"] == "45 min"
    assert facts["confidence"] == "settled"


def test_the_programme_and_time_only_show_during_a_cycle() -> None:
    p, clock = presenter()
    connected(p, clock)
    idle = p.screen(status(dryer(programme="Cotton", remaining_minutes=270)))["hero"]["facts"]
    assert "programme" not in idle
    assert "remaining" not in idle


def test_an_unsettled_estimate_says_so_and_so_does_its_completion_time() -> None:
    p, clock = presenter()
    connected(p, clock)
    facts = p.screen(status(dryer(**RUNNING)))["hero"]["facts"]
    assert facts["remaining"] == "about 47 min"
    assert facts["confidence"] == "still estimating"
    assert facts["completion"].startswith("about ")
    assert facts["progress"] == 54


def test_no_progress_figure_means_no_number_and_no_meters() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    hero = p.screen(status(dryer(**{**RUNNING, "progress": None})))["hero"]
    assert hero["facts"]["progress"] is None
    assert hero["meters"] == []
    assert hero["pose"] == "waiting"


# ------------------------------------------------ plain where action is needed


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize(
    "shape",
    [
        {"state": "fault", "fault_code": "E3", "progress": 0.5},
        {"state": "paused", "attention": "the water tank is full", "progress": 0.4},
    ],
)
def test_warnings_and_faults_are_plain_at_every_level(level: str, shape: dict[str, Any]) -> None:
    p, clock = presenter(level=level)
    connected(p, clock)
    hero = p.screen(status(dryer(**shape)))["hero"]
    assert hero["aside"] is None
    assert hero["meters"] == []
    assert hero["pose"] == "fault"
    assert hero["facts"]["lines"]


def test_the_tank_says_what_to_do() -> None:
    p, clock = presenter()
    connected(p, clock)
    lines = p.screen(status(dryer(state="paused", attention="the water tank is full")))["hero"][
        "facts"
    ]["lines"]
    assert lines == [
        "The water tank is full, so the tumble dryer has stopped. Empty it and press start."
    ]


def test_where_matters_stand_names_the_layer_and_carries_no_joke() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    where = p.screen(status(dryer(), health="auth"))["where"]
    assert where["aside"] is None
    assert {"name": "Haier account", "status": "CAN'T LOG IN"} in where["layers"]
    assert "hOn password" in where["try"][0]


# ------------------------------------------------------------- plain level


def test_plain_has_no_asides_meters_or_amused_poses() -> None:
    p, clock = presenter(level="plain")
    connected(p, clock)
    for shape in ({}, RUNNING, {"state": "finished", "progress": 1.0}):
        hero = p.screen(status(dryer(**shape)))["hero"]
        assert hero["aside"] is None
        assert hero["meters"] == []
        assert hero["pose"] == "normal"


# -------------------------------------------------------------- the thumbs-up


def test_a_finish_without_the_counter_moving_gets_no_thumbs_up() -> None:
    p, clock = presenter()
    connected(p, clock)
    p.screen(status(dryer(**RUNNING)))
    clock.tick(60)
    hero = p.screen(status(dryer(state="finished", programme="Mixed load", progress=1.0)))["hero"]
    assert hero["pose"] == "normal"
    assert hero["why"]["finished"]["confidence"] == "Reported by the appliance"


def test_a_finish_the_counter_proves_gets_the_thumbs_up_and_says_why() -> None:
    p, clock = presenter()
    connected(p, clock)
    p.screen(status(dryer(**RUNNING)))
    clock.tick(60)
    finished = {"state": "finished", "programme": "Mixed load", "progress": 1.0}
    p.screen(status(dryer(**finished)))
    clock.tick(60)
    hero = p.screen(status(dryer(**finished, cycle_count=105)))["hero"]
    assert hero["pose"] == "confirmed"
    why = hero["why"]["finished"]
    assert why["confidence"] == "Confirmed"
    assert "104 to 105" in " ".join(why["body"])


def command(outcome: str, **times: str) -> dict[str, Any]:
    return {
        "id": "cmd-1",
        "name": "Start",
        "appliance_id": "dryer-1",
        "outcome": outcome,
        "requested_at": T0.isoformat(),
        "accepted_at": times.get("accepted_at"),
        "confirmed_at": times.get("confirmed_at"),
        "rejected_at": None,
        "reason": None,
        "deadline_seconds": 20,
    }


def test_an_accepted_command_is_not_called_successful() -> None:
    p, clock = presenter()
    connected(p, clock)
    clock.at = T0 + timedelta(seconds=2)
    screen = p.screen(
        status(dryer(), command_detail=command("accepted", accepted_at=T0.isoformat()))
    )
    assert screen["trail"]["pose"] == "working"
    assert [row["stamp"] for row in screen["trail"]["rows"]] == [None, "AWAITING APPLIANCE"]
    assert screen["hero"]["pose"] != "confirmed"
    assert screen["hero"]["actions"] == {"mode": "none"}  # the trail replaces the panel


def test_a_timed_out_command_is_a_plain_panel() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    clock.at = T0 + timedelta(seconds=22)
    trail = p.screen(
        status(dryer(), command_detail=command("timed_out", accepted_at=T0.isoformat()))
    )["trail"]
    assert trail["panel"]["title"] == "COMMAND NOT CONFIRMED"
    assert "Nothing has been marked successful." in trail["panel"]["lines"]
    assert trail["pose"] == "fault"


def test_a_confirmed_start_gets_the_stamp_and_the_thumbs_up() -> None:
    p, clock = presenter()
    connected(p, clock)
    clock.at = T0 + timedelta(seconds=4)
    at = (T0 + timedelta(seconds=3)).isoformat()
    screen = p.screen(
        status(
            dryer(**RUNNING),
            command_detail=command("confirmed", accepted_at=T0.isoformat(), confirmed_at=at),
        )
    )
    assert screen["trail"]["rows"][-1]["stamp"] == "CONFIRMED"
    assert screen["trail"]["pose"] == "confirmed"
    assert screen["hero"]["aside"] in [
        line.format(name="the tumble dryer", Name="The tumble dryer")
        for line in voice.ASIDES["start_confirmed"]
    ]


def test_the_trail_collapses_then_goes() -> None:
    p, clock = presenter()
    connected(p, clock)
    detail = command(
        "confirmed",
        accepted_at=T0.isoformat(),
        confirmed_at=(T0 + timedelta(seconds=3)).isoformat(),
    )
    clock.at = T0 + timedelta(seconds=20)
    assert p.screen(status(dryer(**RUNNING), command_detail=detail))["trail"]["collapsed"]
    clock.at = T0 + timedelta(minutes=20)
    assert p.screen(status(dryer(**RUNNING), command_detail=detail))["trail"] is None


# ------------------------------------------------------------ stable asides


def test_a_redraw_keeps_the_same_aside() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    first = p.screen(status(dryer(**RUNNING)))["hero"]["aside"]
    clock.tick(30)
    again = p.screen(status(dryer(**{**RUNNING, "progress": 0.55})))["hero"]["aside"]
    assert first
    assert first == again


def test_a_rising_estimate_is_noticed_and_named() -> None:
    p, clock = presenter()
    connected(p, clock)
    p.screen(status(dryer(**{**RUNNING, "remaining_minutes": 39})))
    clock.tick(60)
    aside = p.screen(status(dryer(**RUNNING)))["hero"]["aside"]
    assert "39" in aside
    assert "47" in aside


def test_dry_says_nothing_when_nothing_happened() -> None:
    p, clock = presenter(level="dry")
    connected(p, clock)
    assert (
        p.screen(status(dryer(**{**RUNNING, "remaining_settled": True})))["hero"]["aside"] is None
    )


def test_narration_does_not_repeat_within_thirty_looks() -> None:
    memory = WindowMemory(None)
    shown = []
    for cycle in range(200):
        index = memory.pick_narration("running_middle", f"cycle-{cycle}", 12, cycle * 7919)
        shown.append(index)
    for i in range(len(shown)):
        window = shown[max(0, i - 11) : i]
        assert shown[i] not in window


# ------------------------------------------------------------ unknowns


def test_an_unverified_appliance_is_never_interpreted() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    raw = dryer(
        id="washer-1",
        name="washing machine",
        trust="unverified",
        state="running",
        raw={"machMode": "6"},
        progress=0.5,
    )
    screen = p.screen(status(dryer(), raw))
    chip = next(c for c in screen["caseload"] if c["id"] == "washer-1")
    assert chip["unverified"]
    assert chip["state_word"] == "STATE UNKNOWN"
    assert screen["hero"]["id"] == "dryer-1"  # never the automatic hero
    diagnostics = p.diagnostics(status(dryer(), raw))
    guesses = diagnostics["sections"][2]["rows"]
    assert any("machMode 6" in label for label, _ in guesses)


def test_unknown_facts_come_first_and_the_aside_only_explains_the_refusal() -> None:
    p, clock = presenter()
    connected(p, clock)
    hero = p.screen(status(dryer(trust="unverified", state="unknown")))["hero"]
    assert hero["facts"]["lines"][0].startswith("State unknown.")
    assert hero["aside"] in voice.ASIDES["unknown_state"]
    assert hero["meters"] == []


# ------------------------------------------------------------ connecting


def test_connecting_follows_what_can_be_seen_not_a_timer() -> None:
    p, clock = presenter()
    assert p.screen(None)["connecting"]["stage"] == "service"
    assert p.screen(status(health="slow"))["connecting"]["stage"] == "haier"
    assert p.screen(status())["connecting"]["stage"] == "appliances"
    unread = dryer(state="unknown")
    assert p.screen(status(unread))["connecting"]["stage"] == "reading"
    assert p.screen(status(dryer()))["connecting"]["stage"] == "ready"
    clock.tick(2)
    assert p.screen(status(dryer()))["connecting"] is None


# ------------------------------------------------------------ memory


def test_stored_state_holds_facts_never_sentences(tmp_path: Path) -> None:
    p, clock = presenter(tmp_path, level="departmental")
    connected(p, clock)
    rendered = []
    for shape in (RUNNING, {"state": "finished", "progress": 1.0, "programme": "Mixed load"}):
        clock.tick(60)
        screen = p.screen(status(dryer(**shape)))
        rendered.append(screen["hero"]["aside"])
    stored = (tmp_path / "window.json").read_text(encoding="utf-8")
    for line in filter(None, rendered):
        assert line not in stored
    assert json.loads(stored)["observations"]


def test_a_damaged_memory_file_is_an_empty_memory(tmp_path: Path) -> None:
    path = tmp_path / "window.json"
    path.write_text("{not json", encoding="utf-8")
    memory = WindowMemory(path)
    assert memory.state.picks == {}
    assert memory.state.appearance.level == "dry"


# ------------------------------------------------------------ meters


@pytest.mark.parametrize("kind", ["rising", "peaking", "late"])
def test_every_meter_curve_stays_between_0_and_100(kind: str) -> None:
    for step in range(-5, 106):
        assert 0 <= curve(kind, step / 100) <= 100


def test_meters_follow_the_programme() -> None:
    p, clock = presenter(level="departmental")
    connected(p, clock)
    hero = p.screen(status(dryer(**{**RUNNING, "programme": "Duvet"})))["hero"]
    assert [m["label"] for m in hero["meters"]] == [m.label for m in voice.METERS["Duvet"]]


# ------------------------------------------------------------ actions


def test_not_armed_is_literal_and_the_aside_rides_alongside() -> None:
    p, clock = presenter()
    connected(p, clock)
    actions = p.screen(status(dryer()))["hero"]["actions"]
    assert actions["mode"] == "not_armed"
    assert actions["button"] == "Waiting for Remote mode"
    assert actions["fact"].startswith("Remote start is unavailable.")
    assert actions["aside"]


def test_armed_offers_tiles_with_the_recommendation_marked() -> None:
    p, clock = presenter()
    connected(p, clock)
    tiles = p.screen(status(dryer(remote_allowed=True)))["hero"]["actions"]["programmes"]
    duvet = tiles[0]
    assert duvet["button"] == "Start Duvet"
    time = next(s for s in duvet["settings"] if s["label"] == "Time")
    assert [o["recommended"] for o in time["options"]] == [True, False]
    temperature = next(s for s in duvet["settings"] if s["label"] == "Temperature")
    assert temperature["fixed"]


# ------------------------------------------------------------ pages


def test_a_case_file_is_numbered_by_the_real_counter() -> None:
    p, clock = presenter()
    connected(p, clock)
    p.screen(status(dryer(**RUNNING)))
    clock.tick(60)
    p.screen(status(dryer(**{**RUNNING, "remaining_minutes": 52})))
    clock.tick(3600)
    p.screen(status(dryer(state="finished", programme="Mixed load", progress=1.0)))
    clock.tick(60)
    p.screen(status(dryer(state="finished", programme="Mixed load", progress=1.0, cycle_count=105)))
    case = p.cases()[0]
    assert case["number"] == "CASE 000105"
    texts = [row["text"] for row in case["evidence"]]
    assert "Estimate revised 47 → 52 min" in texts
    assert "Cycle counter 104 → 105" in texts
    assert case["closing"] == list(voice.CASE_CLOSING)


def test_the_guide_unlocks_from_real_events_only() -> None:
    p, clock = presenter()
    p.screen(status(dryer(cycle_count=17)))  # a young dryer: no milestone yet
    clock.tick(2)
    unlocked = {e["key"] for e in p.guide(None)["entries"] if e["unlocked"]}
    assert unlocked == {"pasties"}
    p.screen(status(dryer(**RUNNING, cycle_count=17)))
    unlocked = {e["key"] for e in p.guide(None)["entries"] if e["unlocked"]}
    assert "round" in unlocked
    assert "water" not in unlocked
    p.screen(status(dryer(cycle_count=50)))
    assert "milestones" in {e["key"] for e in p.guide(None)["entries"] if e["unlocked"]}


def test_departmental_about_has_the_institution_and_plain_does_not() -> None:
    p, _ = presenter(level="departmental")
    assert p.about()["institution"] == voice.INSTITUTION
    p.set_level("plain")
    assert p.about()["institution"] is None
    assert p.about()["org_chart"] == []


def test_the_poke_is_departmental_and_cooled_down() -> None:
    p, clock = presenter(level="dry")
    assert p.poke() is None
    p.set_level("departmental")
    assert p.poke() in voice.POKED
    assert p.poke() is None
    clock.tick(31 * 60)
    assert p.poke() in voice.POKED
