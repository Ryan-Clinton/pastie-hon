"""The release page is built from CHANGELOG.md; these pin how."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"

spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert spec is not None
assert spec.loader is not None
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [1.2.0] — 2026-10-01 — a release

The short part — for people.

### Added

- The long part, for the record.

## [1.1.0] — 2026-09-01

Older.
"""


def test_the_release_page_gets_the_summary_and_a_link_not_the_whole_section() -> None:
    notes = release_notes.notes(CHANGELOG, "1.2.0")

    assert notes.startswith("The short part — for people.")
    assert "The long part" not in notes
    assert "Older." not in notes
    assert "CHANGELOG.md" in notes


def test_the_notes_are_written_as_utf8_whatever_the_console_uses() -> None:
    """The 0.3.0 release went up with its dashes as replacement characters."""
    written = subprocess.run(
        [sys.executable, str(SCRIPT), "0.3.0"],
        capture_output=True,
        check=True,
        env={"PYTHONIOENCODING": "cp1252", "SYSTEMROOT": "C:\\Windows", "PATH": ""},
    ).stdout

    text = written.decode("utf-8")  # raises if it isn't UTF-8
    assert "\ufffd" not in text
    assert "—" in text or "→" in text
