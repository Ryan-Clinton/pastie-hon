"""Small durable JSON files, written so a crash cannot corrupt them.

Everything Pastie has to remember across a restart - what the appliance was
doing, what has already been announced - is a handful of fields. A database
would be a bigger promise than the data deserves; a half-written JSON file
would not be, which is why writes go through a temporary file and a rename.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    """Replace `path` with `text`, or leave it exactly as it was.

    Losing power between two writes must not leave a truncated file, because the
    file being unreadable means Pastie forgets what it already announced - and
    forgetting that is how a restart shouts about a load put away on Tuesday.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class JsonFile:
    """A JSON document on disk, or held in memory when `path` is None.

    In-memory mode is not a test convenience bolted on afterwards: the app
    process reads state over the service's channel and has nothing of its own to
    persist, so "no file" is a real deployment.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Read the document as it is *now*.

        Deliberately not cached: a setting changed in the app has to apply to
        the next alert rather than the next restart, and the file is a few
        hundred bytes. With no path, the copy held in memory is the document.
        """
        if self.path is None:
            return dict(self._data)
        if not self.path.exists():
            return {}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A damaged file is treated as an empty one. The alternative - refuse
            # to start - turns a cosmetic problem into an appliance you are no
            # longer being told about.
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def save(self, data: dict[str, Any]) -> None:
        self._data = dict(data)
        if self.path is not None:
            atomic_write_text(self.path, json.dumps(data, indent=2, sort_keys=True))
