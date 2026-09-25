"""The shipped lines obey the mechanical rules (UI-SPEC 7.1, 7.4, A14)."""

from __future__ import annotations

import string

import pytest

from pastie.app import voice

MINIMUM = {
    "idle": 12,
    "armed": 12,
    "running_early": 12,
    "running_middle": 12,
    "running_late": 12,
    "finished": 12,
    "paused": 6,
    "estimating": 6,
    "scheduled": 6,
}

ALLOWED_FIELDS = {"name", "Name", "minutes", "before", "after", "count", "household", "household_s"}


def every_line() -> list[str]:
    lines: list[str] = []
    for pool in voice.NARRATION.values():
        lines.extend(pool)
    for pool in voice.ASIDES.values():
        lines.extend(pool)
    for groups in voice.TEMPERAMENT_LINES.values():
        for pool in groups.values():
            lines.extend(pool)
    for pool in voice.STANCE_LINES.values():
        lines.extend(pool)
    lines.extend(voice.POKED)
    lines.extend(voice.IDLE_LINE.values())
    lines.extend(voice.CONNECTING.values())
    lines.extend([voice.RECONNECTED, *voice.CASE_CLOSING, voice.CASE_MILESTONE])
    lines.extend(voice.HISTORY_EMPTY.values())
    lines.extend(voice.EMPTY_NO_APPLIANCE.values())
    lines.extend(voice.ONBOARDING_ASIDES.values())
    lines.extend(example for _, _, example in voice.LEVEL_EXAMPLES)
    lines.extend([voice.INSTITUTION, voice.INSTITUTION_NOTE, voice.DIVISION])
    for entry in voice.GUIDE:
        lines.extend([entry.title, entry.condition, entry.body])
    for specs in voice.METERS.values():
        lines.extend(spec.label for spec in specs)
    for role, duty in voice.ORG_CHART:
        lines.extend([role, duty])
    return lines


@pytest.mark.parametrize(("stage", "minimum"), sorted(MINIMUM.items()))
def test_every_narration_pool_meets_its_minimum(stage: str, minimum: int) -> None:
    assert len(voice.NARRATION[stage]) >= minimum


def test_there_is_no_pool_for_anything_somebody_must_act_on() -> None:
    for plain in ("fault", "tank", "needs_emptying", "auth", "login"):
        assert plain not in voice.NARRATION
        assert plain not in voice.ASIDES


def test_every_aside_key_has_three_variants() -> None:
    for key, pool in voice.ASIDES.items():
        assert len(pool) >= 3, key
    assert len(voice.POKED) >= 12


def test_every_narration_and_aside_line_fits_the_hero() -> None:
    for pool in [*voice.NARRATION.values(), *voice.ASIDES.values(), voice.POKED]:
        for line in pool:
            filled = line.format(
                household="the Household",
                household_s="the Household's",
                name="the tumble dryer",
                Name="The tumble dryer",
                minutes=120,
                before=120,
                after=135,
                count=100,
            )
            assert len(filled) <= 160, line


def test_no_line_appears_in_two_pools() -> None:
    seen: dict[str, str] = {}
    pools = {f"narration.{k}": v for k, v in voice.NARRATION.items()}
    pools |= {f"aside.{k}": v for k, v in voice.ASIDES.items()}
    pools["poked"] = voice.POKED
    for name, pool in pools.items():
        for line in pool:
            assert line not in seen, f"{line!r} is in {seen.get(line)} and {name}"
            seen[line] = name


def test_no_shipped_line_borrows_somebody_elses_catchphrases() -> None:
    for line in every_line():
        lowered = line.lower()
        for term in voice.BORROWED:
            assert term not in lowered, f"{term!r} in {line!r}"


def test_placeholders_are_only_the_ones_the_presenter_fills() -> None:
    for line in every_line():
        fields = {name for _, name, _, _ in string.Formatter().parse(line) if name}
        assert fields <= ALLOWED_FIELDS, line


def test_every_temperament_and_stance_has_its_lines() -> None:
    for temperament in voice.TEMPERAMENTS:
        if temperament in ("Indecisive", "Custom"):
            continue  # Indecisive is the base narration; Custom is the owner's
        for group in ("running", "finished", "idle"):
            assert len(voice.TEMPERAMENT_LINES[temperament][group]) >= 4
    for stance in voice.STANCES:
        assert len(voice.STANCE_LINES[stance]) >= 4


def test_stage_names_and_remark_names_never_collide() -> None:
    """The personality editor addresses pools by name, so a name must mean one pool."""
    assert not set(voice.NARRATION) & set(voice.ASIDES)
