"""What the pastie is going through, instead of a progress bar.

The window's mascot is a pastie, and a cycle is something that happens *to* it.
This turns the appliance's state and progress into a sentence of narration and
a handful of 0-100 meters.

One rule keeps it honest: the jokes may not cost anybody information. The first
meter is the real progress and says so, the remaining time stays in the detail
lines where it always was, and a fault or a full tank is said plainly inside the
joke. Everything else is decoration, and is allowed to be daft.

Pure functions only - nothing here touches Tk - so every line is testable.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

#: The one meter that is not a joke. Named so tests and the window agree on it.
REAL = "Doneness (real)"


@dataclass(frozen=True)
class Meter:
    label: str
    value: int  # 0 to 100, always


@dataclass(frozen=True)
class Ordeal:
    headline: str
    meters: tuple[Meter, ...] = ()


# ------------------------------------------------------------------ the words

_IDLE = (
    "The pastie is not currently being dried. On the whole it considers this the "
    "best available outcome.",
    "Nothing is happening. The pastie has been assured that this is normal, and "
    "has chosen to believe it.",
    "The pastie is at rest. It has not been asked to do anything, which is exactly "
    "how it likes to be asked.",
)

_SCHEDULED = (
    "A cycle has been booked. The pastie is waiting for it the way one waits for a "
    "bus that has been promised in writing.",
)

_STARTING = (
    "The pastie has entered the drum. It had been led to believe this would be "
    "rather more optional.",
    "Warm air is being applied to the pastie in the manner of a planning "
    "department: steadily, pointlessly and without right of appeal.",
    "The pastie is going round. Then, with a sort of grim inevitability, it is going round again.",
)

_MIDDLE = (
    "The pastie has begun to wonder whether the universe is fundamentally round, "
    "or merely this bit of it.",
    "Somewhere in the drum a sock is quietly preparing to leave for a better "
    "universe. The pastie will not be told which one.",
    "The pastie is now roughly as dry as a committee meeting, and a good deal warmer.",
)

_LATE = (
    "The pastie has reached the part of the cycle where hope and lint look much the same.",
    "Nearly there. The pastie has decided, on reflection, that it would rather "
    "have been a sandwich.",
    "The heat is easing off. The pastie is cooling down, and so, it feels, is its opinion of you.",
)

_ESTIMATING = (
    "The pastie is in the drum. How long it will be there is a question the dryer "
    "is still thinking about, in the unhurried way of large machines.",
)

_PAUSED = (
    "Everything has stopped. The pastie hangs in the drum like a thought nobody "
    "has bothered to finish.",
)

_FINISHED = (
    "It's over. The pastie has emerged, changed in ways it would prefer not to discuss.",
    "Finished. The pastie is dry, noticeably wiser, and would like a lie down in a cupboard.",
)

_UNKNOWN = (
    "The pastie's whereabouts are, for the moment, unknown. This is much less "
    "alarming than it sounds.",
)

# The two that carry instructions. The joke comes second; the instruction does not.
_TANK = (
    "The water tank is full, so the dryer has stopped. Empty it and press start. "
    "The pastie will wait, damply, in the dark.",
)

_FAULT = (
    "The dryer has reported a fault and stopped. Check the machine's display. The "
    "pastie has no idea what happened either, and was right there.",
)


# ---------------------------------------------------------------- the meters


def _meters(progress: float) -> tuple[Meter, ...]:
    p = min(max(progress, 0.0), 1.0)
    return (
        Meter(REAL, round(p * 100)),
        # Goes up fast and levels off, like most things involving an oven.
        Meter("Crispiness", round(100 * (1 - (1 - p) ** 2))),
        # Worst in the middle; by the end it has turned into acceptance.
        Meter("Existential dread", round(100 * math.sin(math.pi * p))),
        # Constant throughout, for reasons that have never been adequately explained.
        Meter("Sock escape probability", 100 if p >= 1 else 42),
    )


def _known(progress: float | None) -> tuple[Meter, ...]:
    """Meters only when there is a real number behind them. A 0 would be a lie."""
    return () if progress is None else _meters(progress)


def _pick(lines: tuple[str, ...], seed: str) -> str:
    """The same line for the same moment, so a refresh never changes the story.

    crc32 rather than hash(): hash() is salted per process, so the line would
    change every time the window was reopened.
    """
    return lines[zlib.crc32(seed.encode()) % len(lines)]


def ordeal_for(
    state: str,
    progress: float | None,
    *,
    attention: str | None = None,
    seed: str = "",
) -> Ordeal:
    """The narration and meters for one reading of one appliance.

    `seed` should identify the cycle (appliance and programme, say), so the lines
    vary between cycles but hold still within a stage of one.
    """
    if attention and "tank" in attention.lower():
        return Ordeal(_pick(_TANK, seed), _known(progress))
    if state == "fault":
        return Ordeal(_pick(_FAULT, seed))
    if state == "finished":
        return Ordeal(_pick(_FINISHED, seed), _meters(1.0))
    if state == "paused":
        return Ordeal(_pick(_PAUSED, seed), _known(progress))
    if state == "running":
        if progress is None:
            return Ordeal(_pick(_ESTIMATING, seed))  # no number yet, so no meters
        stage = _STARTING if progress < 0.34 else _MIDDLE if progress < 0.67 else _LATE
        # The stage is part of the seed, so each stage gets its own line.
        return Ordeal(_pick(stage, f"{seed}/{stage[0][:12]}"), _meters(progress))
    if state == "scheduled":
        return Ordeal(_pick(_SCHEDULED, seed))
    if state == "idle":
        return Ordeal(_pick(_IDLE, seed))
    return Ordeal(_pick(_UNKNOWN, seed))
