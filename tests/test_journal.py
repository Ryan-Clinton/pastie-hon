"""The change journal, and the appliance report an owner shares.

The report goes into public GitHub issues, so what these pin down most is what
it can never contain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pastie.service.journal import Journal, appliance_report

AT = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)


def test_changes_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    Journal(path).record(AT, "washer-1", {"machMode": ("1", "2")})

    reopened = Journal(path)

    assert [change.moved for change in reopened.changes("washer-1")] == [{"machMode": ("1", "2")}]
    assert reopened.changes("dryer-1") == []


def test_a_torn_last_line_after_a_crash_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    Journal(path).record(AT, "washer-1", {"machMode": ("1", "2")})
    with path.open("a", encoding="utf-8") as file:
        file.write('{"at": "2026-09-30T20:0')

    assert len(Journal(path).changes("washer-1")) == 1


def test_the_journal_keeps_to_its_limit(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    journal = Journal(path, limit=3)
    for minute in range(8):
        journal.record(AT + timedelta(minutes=minute), "w", {"prPhase": (str(minute), "x")})

    kept = Journal(path, limit=3).changes("w")
    assert [change.moved["prPhase"][0] for change in kept] == ["5", "6", "7"]


def test_nothing_moved_is_not_a_change() -> None:
    journal = Journal(None)
    journal.record(AT, "w", {})
    assert journal.changes("w") == []


def test_the_report_says_what_moved_and_nothing_that_identifies_anybody() -> None:
    journal = Journal(None)
    journal.record(AT, "3fa94c1e7b20", {"machMode": ("1", "2"), "prPhase": ("0", "3")})

    report = appliance_report(
        label="washing machine",
        appliance_type="WM",
        model="HW100-BP14357U1",
        trust="unverified",
        state="unknown",
        raw={"machMode": "2", "prPhase": "3"},
        changes=journal.changes("3fa94c1e7b20"),
        version="0.3.1",
        now=AT,
    )

    assert "washing machine (WM)" in report
    assert "HW100-BP14357U1" in report
    assert "machMode 1 -> 2, prPhase 0 -> 3" in report
    assert "3fa94c1e7b20" not in report  # not even the hashed id
    assert "What were you doing at those times?" in report
