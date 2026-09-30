"""What the window remembers between looks, and between sessions.

Kept by the window, under the user's profile (`paths.app_dir()`), never by the
service: this is presentation, and the service must not depend on it.

**Canonical facts only** (UI-SPEC A15). This file holds which line was picked
for which event (as an index into a pool, never the rendered words), what has
already been remarked on, what the Guide has unlocked, and the evidence Pastie
observed for each cycle's case file. A redraw re-renders from these; nothing
here is a sentence anybody has read.

A damaged or missing file is an empty memory, not an error. The window must
open whatever state this file is in.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: How many narration picks per stage to remember, so a line is not repeated
#: within this many looks at the same stage (UI-SPEC 7.4).
NARRATION_MEMORY = 30

#: Evidence rows kept, oldest dropped first.
OBSERVATION_LIMIT = 2000


@dataclass
class Appearance:
    #: plain | dry | departmental (UI-SPEC 7.2). Dry is the default.
    level: str = "dry"
    #: system | dark | light
    theme: str = "system"
    #: system | on
    reduce_motion: str = "system"


@dataclass
class State:
    appearance: Appearance = field(default_factory=Appearance)
    #: event id -> index of the chosen line in its pool.
    picks: dict[str, int] = field(default_factory=dict)
    #: stage -> the last NARRATION_MEMORY indexes shown, newest last.
    narration: dict[str, list[int]] = field(default_factory=dict)
    #: aside key -> ISO date it was first shown, for "first time" rules.
    firsts: dict[str, str] = field(default_factory=dict)
    #: Guide entry key -> ISO time it unlocked.
    unlocked: dict[str, str] = field(default_factory=dict)
    #: Guide entry keys the user has opened since they unlocked.
    seen_guide: list[str] = field(default_factory=list)
    #: Canonical evidence, oldest first (see `Observation`).
    observations: list[dict[str, Any]] = field(default_factory=list)
    #: The appliance the user picked as the hero, and when (ISO).
    pinned: dict[str, str] = field(default_factory=dict)


class WindowMemory:
    """Loads, holds and saves `State`. Saving is explicit and cheap."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self.state = self._load()
        self._dirty = False

    # ------------------------------------------------------------ loading

    def _load(self) -> State:
        if self._path is None or not self._path.exists():
            return State()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            log.warning("window memory unreadable, starting afresh: %s", error)
            return State()
        if not isinstance(raw, dict):
            return State()
        state = State()
        appearance = raw.get("appearance")
        if isinstance(appearance, dict):
            state.appearance = Appearance(
                level=_one_of(appearance.get("level"), ("plain", "dry", "departmental"), "dry"),
                theme=_one_of(appearance.get("theme"), ("system", "dark", "light"), "system"),
                reduce_motion=_one_of(appearance.get("reduce_motion"), ("system", "on"), "system"),
            )
        state.picks = _typed_dict(raw.get("picks"), int)
        state.narration = {
            str(k): [int(i) for i in v if isinstance(i, int)]
            for k, v in (raw.get("narration") or {}).items()
            if isinstance(v, list)
        }
        state.firsts = _typed_dict(raw.get("firsts"), str)
        state.unlocked = _typed_dict(raw.get("unlocked"), str)
        state.seen_guide = [str(k) for k in raw.get("seen_guide") or [] if isinstance(k, str)]
        state.observations = [o for o in raw.get("observations") or [] if isinstance(o, dict)]
        state.pinned = _typed_dict(raw.get("pinned"), str)
        return state

    def save(self) -> None:
        if self._path is None or not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(self.state), indent=1), encoding="utf-8")
            temporary.replace(self._path)
            self._dirty = False
        except OSError as error:
            log.warning("could not save window memory: %s", error)

    def touch(self) -> None:
        self._dirty = True

    # ------------------------------------------------------------ picking

    def pick(self, event_id: str, size: int, seed: int) -> int:
        """The line index for an event: chosen once, then remembered."""
        chosen = self.state.picks.get(event_id)
        if chosen is None or not 0 <= chosen < size:
            chosen = seed % size
            self.state.picks[event_id] = chosen
            self.touch()
        return chosen

    def pick_narration(self, stage: str, event_id: str, size: int, seed: int) -> int:
        """A narration line not shown in the last NARRATION_MEMORY looks at this stage.

        Stable for the event: the same stage of the same cycle keeps its line.
        """
        chosen = self.state.picks.get(event_id)
        if chosen is not None and 0 <= chosen < size:
            return chosen
        recent = self.state.narration.setdefault(stage, [])
        avoid = set(recent[-min(NARRATION_MEMORY, size - 1) :]) if size > 1 else set()
        for step in range(size):
            candidate = (seed + step) % size
            if candidate not in avoid:
                chosen = candidate
                break
        else:  # pragma: no cover - unreachable while avoid is smaller than size
            chosen = seed % size
        self.state.picks[event_id] = chosen
        recent.append(chosen)
        del recent[:-NARRATION_MEMORY]
        self.touch()
        return chosen

    def first(self, key: str, today: str) -> bool:
        """Whether `key` is being shown for the first time ever. Records it."""
        if key in self.state.firsts:
            return False
        self.state.firsts[key] = today
        self.touch()
        return True

    def first_today(self, key: str, today: str) -> bool:
        """Whether `key` has not yet been shown today. Records it."""
        if self.state.firsts.get(key) == today:
            return False
        self.state.firsts[key] = today
        self.touch()
        return True

    # ------------------------------------------------------------ evidence

    def observe(self, row: dict[str, Any]) -> None:
        self.state.observations.append(row)
        del self.state.observations[:-OBSERVATION_LIMIT]
        self.touch()

    def unlock(self, key: str, at: str) -> bool:
        if key in self.state.unlocked:
            return False
        self.state.unlocked[key] = at
        self.touch()
        return True


def _one_of(value: object, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _typed_dict(value: object, kind: type) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, kind)}
