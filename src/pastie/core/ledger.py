"""A written record of everything already announced.

The rule from the specification is "once announced, never re-announced", and it
has to survive a restart to mean anything - a restart is the only time the
question comes up. Hence a file rather than a set in memory.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from pastie.core.store import JsonFile

#: Long enough that a machine left finished over a fortnight's holiday is still
#: remembered as announced; short enough that the file never grows.
RETENTION = timedelta(days=90)


class Ledger:
    """Records event keys, and refuses the second attempt at the same one."""

    def __init__(self, path: Path | None = None, retention: timedelta = RETENTION) -> None:
        self._file = JsonFile(path)
        self._retention = retention
        self._seen: dict[str, str] = {}
        for key, when in self._file.load().items():
            if isinstance(when, str):
                self._seen[key] = when

    def __contains__(self, key: str) -> bool:
        return key in self._seen

    def __len__(self) -> int:
        return len(self._seen)

    def record(self, key: str, when: datetime) -> bool:
        """Write `key` down. Returns False if it was already there.

        The caller announces only on True. Recording happens *before* the light
        flashes, not after: crashing between the two is possible either way, and
        a light that flashes twice is a smaller failure than one that announces
        the same finished cycle twice.
        """
        if key in self._seen:
            return False
        self._seen[key] = when.isoformat()
        self._prune(when)
        self._file.save(dict(self._seen))
        return True

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._retention
        stale = [
            key
            for key, stamp in self._seen.items()
            if (parsed := _parse(stamp)) is not None and parsed < cutoff
        ]
        for key in stale:
            del self._seen[key]

    def keys(self) -> Iterable[str]:
        return tuple(self._seen)


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
