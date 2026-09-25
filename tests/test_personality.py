"""Configurable personalities (docs/UI-SPEC.md 7.9, A20, A21)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from pastie.app import personality, voice
from pastie.app.memory import WindowMemory
from pastie.app.personality import Meter, PersonalityStore, Pool, Sheet, check_line
from pastie.app.presenter import Presenter
from tests.test_presenter import RUNNING, T0, Clock, command, dryer, status
from tests.test_webview import FakeClient

KEY = "tumble-dryer"


def with_sheet(
    sheet: Sheet | None = None, level: str = "departmental", **extra: Sheet
) -> tuple[Presenter, Clock]:
    store = PersonalityStore(None)
    if sheet is not None:
        store.save(sheet)
    for other in extra.values():
        store.save(other)
    clock = Clock()
    p = Presenter(WindowMemory(None), now=clock, personalities=store)
    p.set_level(level)
    p.screen(status(dryer()))
    clock.tick(2)
    return p, clock


# ------------------------------------------------------------- checking lines


def test_a_line_for_anything_needing_action_is_refused() -> None:
    for pool in ("fault", "tank_full", "needs_emptying", "auth"):
        assert not check_line(pool, "Oh dear, {name}.").ok


def test_a_line_with_a_placeholder_pastie_cannot_fill_is_refused() -> None:
    check = check_line("finished", "{name} is done, says {mystery}.")
    assert not check.ok
    assert "{mystery}" in (check.refused or "")
    assert not check_line("finished", "An unclosed {brace").ok
    assert not check_line("finished", "   ").ok


def test_long_and_borrowed_lines_warn_but_are_allowed() -> None:
    long = check_line("finished", "x" * 200)
    assert long.ok
    assert long.warnings
    borrowed = check_line("finished", "{Name} says don't panic.")
    assert borrowed.ok
    assert any("books" in w for w in borrowed.warnings)


# ------------------------------------------------------------- round trips (A21)


def full_sheet() -> Sheet:
    return Sheet(
        key=KEY,
        name="Big Dave",
        temperament="Dramatic",
        stance="Fond",
        level="dry",
        meters=[Meter("Heat", "rising"), Meter("Mood", "peaking")],
        pools={
            "finished": Pool(disabled=[voice.NARRATION["finished"][0]], added=["{Name} is done."])
        },
    )


def test_a_sheet_survives_toml_exactly() -> None:
    sheet = full_sheet()
    again, dropped = personality.from_toml(personality.to_toml(sheet))
    assert dropped == []
    assert again == sheet


def test_the_store_saves_loads_and_resets(tmp_path: Path) -> None:
    folder = tmp_path / "personalities"
    PersonalityStore(folder).save(full_sheet())
    loaded = PersonalityStore(folder)
    assert loaded.get(KEY) == full_sheet()

    loaded.reset(KEY, "finished")
    assert "finished" not in PersonalityStore(folder).sheet(KEY).pools
    loaded.reset(KEY)
    assert PersonalityStore(folder).get(KEY) is None
    assert (
        personality.effective(PersonalityStore(folder).get(KEY), "finished")
        == voice.NARRATION["finished"]
    )


def test_an_import_applies_what_is_valid_and_reports_the_rest() -> None:
    pack = """
[sheet]
key = "tumble-dryer"
name = "Big Dave"
temperament = "Furious"
stance = "Fond"

[[meters]]
label = "Heat"
curve = "sideways"

[pools.finished]
added = ["{Name} is done.", "{mystery} broke it."]

[pools.fault]
added = ["Ha, a fault."]
"""
    sheet, dropped = PersonalityStore(None).import_pack(pack)
    assert sheet.name == "Big Dave"
    assert sheet.stance == "Fond"
    assert sheet.temperament == "Indecisive"  # the unknown one was dropped, the default stands
    assert sheet.meters == []
    assert sheet.pools["finished"].added == ["{Name} is done."]
    assert "fault" not in sheet.pools
    assert len(dropped) == 4


def test_nonsense_is_not_a_pack() -> None:
    with pytest.raises(ValueError, match="isn't a personality pack"):
        PersonalityStore(None).import_pack("this = [is not toml")


# ------------------------------------------------------------- the limits (A20)


SHAPES: list[dict[str, Any]] = [
    {},
    {"remote_allowed": True},
    RUNNING,
    {"state": "finished", "programme": "Mixed load", "progress": 1.0},
    {"state": "paused", "attention": "the water tank is full", "progress": 0.4},
    {"state": "fault", "fault_code": "E3"},
]


@pytest.mark.parametrize("shape", SHAPES)
def test_no_sheet_changes_a_fact_a_stamp_or_a_pose(shape: dict[str, Any]) -> None:
    plain_p, _ = with_sheet(None)
    wild = Sheet(
        key=KEY,
        name="Big Dave",
        temperament="Custom",
        stance="Firm",
        level="departmental",
        pools={
            p: Pool(added=["{Name} did a thing."], replace=True)
            for p in personality.APPLIANCE_POOLS
        },
    )
    wild_p, _ = with_sheet(wild)
    a = plain_p.screen(status(dryer(**shape)))["hero"]
    b = wild_p.screen(status(dryer(**shape)))["hero"]
    for key in ("state_word", "facts", "stamps", "pose", "severity", "why", "name"):
        assert a[key] == b[key], key
    assert a["actions"]["mode"] == b["actions"]["mode"]


@pytest.mark.parametrize("shape", SHAPES[4:])
def test_nothing_needing_action_takes_a_joke_whatever_the_sheet(shape: dict[str, Any]) -> None:
    wild = Sheet(
        key=KEY, pools={p: Pool(added=["Ha!"], replace=True) for p in personality.APPLIANCE_POOLS}
    )
    p, _ = with_sheet(wild)
    hero = p.screen(status(dryer(**shape)))["hero"]
    assert hero["aside"] is None
    assert hero["meters"] == []


def test_the_thumbs_up_still_needs_the_machine() -> None:
    p, clock = with_sheet(Sheet(key=KEY, temperament="Cheerful", stance="Fond"), level="dry")
    clock.at = T0 + timedelta(seconds=2)
    screen = p.screen(
        status(dryer(), command_detail=command("accepted", accepted_at=T0.isoformat()))
    )
    assert screen["hero"]["pose"] != "confirmed"


def test_an_unverified_appliance_ignores_its_sheet_until_verified() -> None:
    p, _ = with_sheet(Sheet(key="washing-machine", name="Wanda", level="departmental"))
    washer = dryer(id="w", name="washing machine", trust="unverified", state="unknown")
    assert p.name_for(washer) == "the washing machine"
    assert p.name_for({**washer, "trust": "verified"}) == "Wanda"


# ------------------------------------------------------------- what sheets do


def test_the_name_is_used_in_asides_and_never_in_facts() -> None:
    p, _ = with_sheet(Sheet(key=KEY, name="Big Dave"), level="dry")
    hero = p.screen(status(dryer()))["hero"]
    assert "Big Dave" in (hero["actions"]["aside"] or "")
    assert "Big Dave" not in hero["actions"]["fact"]
    assert hero["name"] == "Tumble dryer"


def test_a_per_appliance_level_overrides_the_global_one() -> None:
    p, _ = with_sheet(Sheet(key=KEY, level="plain"), level="departmental")
    hero = p.screen(status(dryer(**RUNNING)))["hero"]
    assert hero["aside"] is None
    assert hero["meters"] == []


def test_custom_temperament_speaks_only_the_owner_s_lines() -> None:
    own = "{Name} is getting on with it, as instructed."
    sheet = Sheet(
        key=KEY, name="Big Dave", temperament="Custom", pools={"running_middle": Pool(added=[own])}
    )
    p, _ = with_sheet(sheet)
    aside = p.screen(status(dryer(**{**RUNNING, "remaining_settled": True})))["hero"]["aside"]
    assert aside == "Big Dave is getting on with it, as instructed."


def test_a_temperament_and_a_stance_join_the_narration() -> None:
    sheet = Sheet(key=KEY, temperament="Dramatic", stance="Fond")
    p, _ = with_sheet(sheet)
    pool = p._narration_pool(dryer(**RUNNING), "running_middle")
    assert set(voice.TEMPERAMENT_LINES["Dramatic"]["running"]) <= set(pool)
    assert set(voice.STANCE_LINES["Fond"]) <= set(pool)
    assert set(voice.NARRATION["running_middle"]) <= set(pool)


def test_the_owner_s_meters_replace_the_programme_s() -> None:
    p, _ = with_sheet(Sheet(key=KEY, meters=[Meter("Heat", "rising")]))
    hero = p.screen(status(dryer(**{**RUNNING, "programme": "Duvet"})))["hero"]
    assert [m["label"] for m in hero["meters"]] == ["Heat"]


def test_the_household_can_be_renamed_everywhere() -> None:
    household = Sheet(key=personality.HOUSEHOLD, name="the Clintons")
    p, _ = with_sheet(None, household=household)
    assert p.household() == ("the Clintons", "the Clintons'")
    pool = p._narration_pool(dryer(remote_allowed=True), "armed")
    assert any("{household_s}" in line for line in pool)


def test_pastie_s_own_lines_join_the_three_click_remark() -> None:
    mine = "Pastie is on its tea break. It will be back presently."
    me = Sheet(key=personality.PASTIE, pools={"poked": Pool(added=[mine], replace=True)})
    p, _ = with_sheet(None, pastie=me)
    assert p.poke() == mine


# ------------------------------------------------------------- the bridge


def bridge_with(store: PersonalityStore) -> Any:
    from pastie.app.webview import Bridge

    presenter = Presenter(WindowMemory(None), personalities=store)
    return Bridge(FakeClient(status(dryer())), presenter)  # type: ignore[arg-type]


def test_the_cast_always_includes_the_household_and_pastie() -> None:
    b = bridge_with(PersonalityStore(None))
    b.screen()
    keys = [card["key"] for card in b.personalities()["cards"]]
    assert keys == [KEY, personality.HOUSEHOLD, personality.PASTIE]


def test_saving_lines_keeps_the_good_and_names_the_refused() -> None:
    store = PersonalityStore(None)
    b = bridge_with(store)
    result = b.save_pool(KEY, "finished", [], ["{Name} is done.", "{oops} is not."], False)
    assert result["ok"]
    assert len(result["refused"]) == 1
    assert store.sheet(KEY).pools["finished"].added == ["{Name} is done."]
    assert not b.save_pool(KEY, "fault", [], ["no"], False)["ok"]


def test_the_preview_renders_before_anything_is_saved() -> None:
    store = PersonalityStore(None)
    b = bridge_with(store)
    hero = b.preview(
        KEY, "running", "departmental", {"name": "Big Dave", "temperament": "Cheerful"}
    )
    assert hero["state_word"] == "RUNNING"
    assert hero["meters"]
    assert store.get(KEY) is None  # nothing was saved
