"""Every raw value that moved, kept as data, and the report an owner can share.

Verifying an appliance means watching what its numbers do. The service has
always written those changes to its log, but asking people to pick the right
lines out of a log - and not to paste the wrong ones - is a poor way to ask for
help. So the same changes are kept here as data, and `appliance_report` turns
them into one file an owner can attach to an issue without reading it first.

What the report can contain is decided by what reaches it, not by what is taken
out of it: raw values have already been through the allow-list in
`pastie.connector.scrub`, and the appliance is described by its type and model
only. No appliance id, no nickname, no account, no network address.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pastie.core.store import atomic_write_text

log = logging.getLogger(__name__)

#: Changes kept per journal. A washer cycle moves a few dozen values, so this
#: is weeks of normal use - plenty to verify a machine from.
LIMIT = 5000

#: Changes shown in one report, newest kept. An issue with ten thousand lines in
#: it helps nobody.
REPORT_LINES = 400


@dataclass(frozen=True)
class Change:
    at: datetime
    appliance_id: str
    moved: dict[str, tuple[str, str]]

    def to_json(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "appliance": self.appliance_id,
            "moved": {key: list(pair) for key, pair in self.moved.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Change:
        return cls(
            at=datetime.fromisoformat(str(data["at"])),
            appliance_id=str(data["appliance"]),
            moved={str(key): (str(pair[0]), str(pair[1])) for key, pair in data["moved"].items()},
        )


class Journal:
    """An append-only record of raw changes, one JSON object per line.

    `path=None` keeps it in memory only, which is what the tests use.
    """

    def __init__(self, path: Path | None, limit: int = LIMIT) -> None:
        self._path = path
        self._limit = limit
        self._changes: list[Change] = self._load()

    def record(self, at: datetime, appliance_id: str, moved: dict[str, tuple[str, str]]) -> None:
        if not moved:
            return
        change = Change(at, appliance_id, dict(moved))
        self._changes.append(change)
        if self._path is None:
            del self._changes[: -self._limit]
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(change.to_json()) + "\n")
            if len(self._changes) > 2 * self._limit:
                self._compact()
        except OSError as error:
            # Losing a journal line must never cost an announcement.
            log.warning("could not write the change journal: %s", error)

    def changes(self, appliance_id: str) -> list[Change]:
        return [change for change in self._changes if change.appliance_id == appliance_id]

    def _load(self) -> list[Change]:
        if self._path is None or not self._path.exists():
            return []
        changes: list[Change] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                changes.append(Change.from_json(json.loads(line)))
            except (ValueError, KeyError, TypeError, IndexError):
                continue  # a torn last line after a crash is not worth failing over
        return changes[-self._limit :]

    def _compact(self) -> None:
        self._changes = self._changes[-self._limit :]
        assert self._path is not None
        atomic_write_text(
            self._path, "".join(json.dumps(change.to_json()) + "\n" for change in self._changes)
        )


def appliance_report(
    *,
    label: str,
    appliance_type: str,
    model: str,
    trust: str,
    state: str,
    raw: dict[str, Any],
    changes: list[Change],
    version: str,
    now: datetime,
) -> str:
    """A plain-text report for an appliance-verification issue.

    Everything in it is either Pastie's own words or a value that has already
    passed the allow-list. Times are local, because the owner is going to match
    them against what they remember doing: "started it at 20:05".
    """
    lines = [
        "Pastie appliance report",
        "=======================",
        f"Pastie:      {version}",
        f"Generated:   {now.astimezone():%Y-%m-%d %H:%M}",
        f"Appliance:   {label} ({appliance_type or 'unknown type'})",
        f"Model:       {model or 'unknown'}",
        f"Pastie says: {trust}, state {state}",
        "",
        "Current raw values",
        "------------------",
    ]
    lines += [f"  {key} = {raw[key]}" for key in sorted(raw)] or ["  (none yet)"]
    shown = changes[-REPORT_LINES:]
    lines += [
        "",
        f"Observed changes ({len(shown)} of {len(changes)}, oldest first, local time)",
        "------------------------------------------------------------",
    ]
    for change in shown:
        moved = ", ".join(
            f"{key} {old} -> {new}" for key, (old, new) in sorted(change.moved.items())
        )
        lines.append(f"  {change.at.astimezone():%Y-%m-%d %H:%M:%S}  {moved}")
    if not shown:
        lines.append("  (nothing has changed yet - run a cycle, then export again)")
    lines += [
        "",
        "What were you doing at those times? Add it to the issue: 'started it at",
        "20:05', 'opened the door at 21:40'. That is what turns numbers into meanings.",
        "",
        "This report holds no appliance id, serial number, MAC address, location or",
        "account. Only values on Pastie's privacy allow-list can reach it.",
    ]
    return "\n".join(lines) + "\n"
