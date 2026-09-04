"""The written record that makes "never announce the same thing twice" survive a
restart - and the atomic write that keeps the record readable after a crash."""

from __future__ import annotations

import contextlib
from datetime import timedelta
from pathlib import Path

import pytest

from pastie.core.ledger import Ledger
from pastie.core.store import JsonFile, atomic_write_text
from tests.support import at


def test_the_second_attempt_at_a_key_is_refused() -> None:
    ledger = Ledger()
    assert ledger.record("dryer-1|finished|4", at(0)) is True
    assert ledger.record("dryer-1|finished|4", at(1)) is False


def test_the_record_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    assert Ledger(path).record("dryer-1|finished|4", at(0)) is True
    assert Ledger(path).record("dryer-1|finished|4", at(1)) is False


def test_old_entries_are_pruned_so_the_file_never_grows(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.json", retention=timedelta(days=1))
    ledger.record("old", at(0))
    ledger.record("new", at(60 * 24 * 3))  # three days later

    assert "old" not in ledger
    assert "new" in ledger


def test_a_damaged_file_is_treated_as_an_empty_one(tmp_path: Path) -> None:
    """Refusing to start would turn a cosmetic problem into a silent appliance."""
    path = tmp_path / "ledger.json"
    path.write_text("{ this is not json", encoding="utf-8")

    ledger = Ledger(path)
    assert len(ledger) == 0
    assert ledger.record("dryer-1|finished|4", at(0)) is True


def test_an_interrupted_write_leaves_the_previous_contents_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    atomic_write_text(path, '{"kept": true}')

    def explode(self: object, target: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", explode)
    with contextlib.suppress(OSError):
        atomic_write_text(path, '{"kept": false}')

    assert path.read_text(encoding="utf-8") == '{"kept": true}'
    assert list(tmp_path.glob("*.tmp")) == []  # and no litter left behind


def test_a_store_with_no_path_keeps_everything_in_memory() -> None:
    """The app process has nothing of its own to persist - that is a real mode."""
    store = JsonFile(None)
    store.save({"a": 1})
    assert store.load() == {"a": 1}
