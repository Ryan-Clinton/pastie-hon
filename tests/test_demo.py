"""The demo has to keep telling the truth.

`pastie demo` is the thing somebody runs before deciding whether to trust any of
this, so every claim its narration makes is pinned here. If the brain's
behaviour changes, these fail - which is the point: a demonstration that drifts
away from the code is worse than none, because it is a confident lie.
"""

from __future__ import annotations

from pastie.core.events import EventKind
from pastie.demo import run, scenarios


def transcript(key: str) -> tuple[list[str], list[EventKind]]:
    lines: list[str] = []
    events = run(scenarios()[key], out=lines.append)
    return lines, [event.kind for event in events]


def test_every_scenario_runs() -> None:
    for scenario in scenarios().values():
        run(scenario, out=lambda _line: None)


def test_a_watched_cycle_announces_once() -> None:
    lines, kinds = transcript("cycle")

    assert kinds == [EventKind.CYCLE_STARTED, EventKind.CYCLE_FINISHED]
    assert sum("ANNOUNCE" in line for line in lines) == 1
    # The first reading is a baseline and says nothing at all.
    assert "20:00  ANNOUNCE" not in "\n".join(lines)


def test_the_estimate_is_shown_as_an_estimate_while_the_machine_guesses() -> None:
    lines, _ = transcript("cycle")
    joined = "\n".join(lines)

    assert "about 120 min (still estimating)" in joined
    assert "45 min" in joined  # and as a plain figure once it has settled


def test_a_gap_is_reported_as_a_gap_with_the_number_of_cycles() -> None:
    lines, kinds = transcript("gap")

    assert EventKind.CYCLE_FINISHED_WHILE_AWAY in kinds
    assert EventKind.CYCLE_FINISHED not in kinds  # never claimed as live news
    assert any(
        "finished while Pastie wasn't running (one cycle, some time after 20:10)" in line
        for line in lines
    )


def test_duplicates_and_a_late_poll_produce_one_announcement() -> None:
    lines, kinds = transcript("noise")

    assert kinds == [EventKind.CYCLE_FINISHED]
    assert sum("ANNOUNCE" in line for line in lines) == 1


def test_an_ignored_command_is_reported_as_not_done() -> None:
    lines, kinds = transcript("ignored")

    assert kinds == []  # a command going nowhere is not an announcement
    assert any("didn't react within 20 seconds" in line for line in lines)
    assert not any("confirmed" in line for line in lines)


def test_an_unverified_appliance_announces_nothing_at_all() -> None:
    lines, kinds = transcript("unverified")

    assert kinds == []
    assert any("unverified - raw only" in line for line in lines)
    assert not any("fault" in line.lower() and "ANNOUNCE" in line for line in lines)


def test_the_narration_counts_what_it_actually_did() -> None:
    lines, _ = transcript("cycle")
    assert any("2 event(s), 1 worth interrupting somebody for." in line for line in lines)


def test_the_command_line_lists_the_scenarios() -> None:
    from pastie.cli import main

    assert main(["demo", "list"]) == 0
    assert main(["demo", "nothing-like-this"]) == 2
