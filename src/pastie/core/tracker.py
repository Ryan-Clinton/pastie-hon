"""The brain: turning "here is what the machine looks like now" into "here is
what just happened".

The obvious version of this - *if the machine says finished, announce it* - is
wrong in both directions. It shouts about a load that was put away on Tuesday,
and it says nothing about the one that finished while the PC was rebooting.

Four things are tracked separately, and the separation is the whole design:

    what the machine sent us      -> Snapshot          (the connector's job)
    what state it is in now       -> Snapshot.state
    what changed                  -> compared with ApplianceMemory
    what that means               -> Event

Two rules do most of the work:

* **Unknown is a real state.** The first reading of a session sets a baseline.
  Anything it differs from the last session by is reported as a *gap* - "this
  happened while I wasn't looking" - never as news.
* **Once announced, never re-announced.** Every event key goes through the
  ledger before it is returned to the caller.
"""

from __future__ import annotations

from collections.abc import Iterable

from pastie.core.events import Event, EventKind
from pastie.core.ledger import Ledger
from pastie.core.memory import ApplianceMemory, MemoryStore
from pastie.core.state import ApplianceState, Snapshot

#: States from which reaching FINISHED means a cycle actually completed.
#: Reaching it from IDLE means the machine was already finished and somebody
#: turned it on and off again, which is not a completion.
_RUNNING_STATES = frozenset({ApplianceState.RUNNING, ApplianceState.PAUSED})


class Tracker:
    """Consumes snapshots, produces events. One instance watches every appliance.

    A `Tracker` is per-session: the set of appliances it has already seen this
    run is deliberately not persisted, because it is exactly what distinguishes
    "I watched this happen" from "this had happened by the time I looked".
    """

    def __init__(self, memory: MemoryStore, ledger: Ledger) -> None:
        self._memory = memory
        self._ledger = ledger
        self._seen_this_session: set[str] = set()

    # ------------------------------------------------------------------ input

    def observe(self, snapshot: Snapshot) -> list[Event]:
        """Take a reading and return whatever should be announced because of it.

        Returns an empty list far more often than not, which is the point.
        """
        memory = self._memory.get(snapshot.appliance_id)

        if self._is_stale(snapshot, memory):
            return []

        first_of_session = snapshot.appliance_id not in self._seen_this_session
        self._seen_this_session.add(snapshot.appliance_id)

        duplicate = memory.fingerprint is not None and memory.fingerprint == snapshot.fingerprint

        if not snapshot.is_verified:
            # An unverified appliance type gets detection and raw diagnostics
            # only. Its numbers have not been confirmed by anyone who owns one,
            # and "mode 6" meaning a fault on a dryer is no reason to announce a
            # fault on somebody's oven.
            self._remember(snapshot, memory)
            return []

        if duplicate:
            self._remember(snapshot, memory)
            return []

        events = (
            self._resume_events(snapshot, memory)
            if first_of_session
            else self._live_events(snapshot, memory)
        )
        events.extend(self._maintenance_events(snapshot))

        self._remember(snapshot, memory)
        return [event for event in events if self._ledger.record(event.key, event.at)]

    def connection_lost(self, appliance_id: str) -> None:
        """Note that we have stopped hearing from an appliance.

        The next reading is then treated as the first of a session: it
        re-baselines, and anything that changed during the outage is reported as
        a gap rather than as something we watched happen. The negotiated MQTT
        session replays nothing on reconnect, so a full refresh after one is not
        a precaution - it is the only correct behaviour.
        """
        self._seen_this_session.discard(appliance_id)

    def forget_session(self) -> None:
        """Re-baseline every appliance. Used when the connection is rebuilt."""
        self._seen_this_session.clear()

    # ------------------------------------------------------------- transitions

    def _resume_events(self, snapshot: Snapshot, memory: ApplianceMemory) -> list[Event]:
        """The first reading of a session: report gaps, announce nothing live."""
        if not memory.state.is_known and memory.cycle_count is None:
            return []  # nothing to compare against

        completed = self._cycles_completed_while_away(snapshot, memory)
        if completed is None:
            return []

        when = memory.last_running_at
        if completed > 0:
            body = "one cycle" if completed == 1 else f"{completed} cycles"
            detail = f" ({body}, some time after {when:%H:%M})" if when else f" ({body})"
        else:
            detail = (
                f". Last seen running at {when:%H:%M}. Time of completion unknown"
                if when
                else ". Time of completion unknown"
            )

        return [
            Event(
                kind=EventKind.CYCLE_FINISHED_WHILE_AWAY,
                appliance_id=snapshot.appliance_id,
                at=snapshot.observed_at,
                key=self._finished_key(snapshot),
                message=f"{_subject(snapshot)} finished while Pastie wasn't running{detail}.",
                detail={
                    "cycles": completed or None,
                    "last_seen_running": when.isoformat() if when else None,
                },
            )
        ]

    def _live_events(self, snapshot: Snapshot, memory: ApplianceMemory) -> list[Event]:
        """A reading that follows one we already saw this session."""
        events: list[Event] = []
        previous = memory.state

        if snapshot.state is ApplianceState.FAULT and previous is not ApplianceState.FAULT:
            code = snapshot.fault_code or "unknown"
            events.append(
                Event(
                    kind=EventKind.FAULT,
                    appliance_id=snapshot.appliance_id,
                    at=snapshot.observed_at,
                    key=f"{snapshot.appliance_id}|fault|{code}|{memory.cycle_count}",
                    message=f"{_subject(snapshot)} has reported a fault (code {code}).",
                    detail={"code": code},
                )
            )

        if snapshot.state is ApplianceState.FINISHED and previous in _RUNNING_STATES:
            events.append(
                Event(
                    kind=EventKind.CYCLE_FINISHED,
                    appliance_id=snapshot.appliance_id,
                    at=snapshot.observed_at,
                    key=self._finished_key(snapshot),
                    message=f"{_subject(snapshot)} has finished.",
                    detail={"programme": snapshot.programme},
                )
            )

        if snapshot.state is ApplianceState.RUNNING and previous not in _RUNNING_STATES:
            events.append(
                Event(
                    kind=EventKind.CYCLE_STARTED,
                    appliance_id=snapshot.appliance_id,
                    at=snapshot.observed_at,
                    key=(
                        f"{snapshot.appliance_id}|started|"
                        f"{snapshot.cycle_count}|{snapshot.observed_at:%Y-%m-%dT%H:%M}"
                    ),
                    message=f"{_subject(snapshot)} has started.",
                    detail={"programme": snapshot.programme},
                )
            )

        return events

    def _maintenance_events(self, snapshot: Snapshot) -> list[Event]:
        """Service intervals the appliance keeps for itself.

        Keyed by which service period it is in, so a machine left un-serviced
        nags once rather than after every load.
        """
        events = []
        for item in snapshot.maintenance:
            if not item.due or item.interval <= 0:
                continue
            period = item.used // item.interval
            events.append(
                Event(
                    kind=EventKind.MAINTENANCE_DUE,
                    appliance_id=snapshot.appliance_id,
                    at=snapshot.observed_at,
                    key=f"{snapshot.appliance_id}|maintenance|{item.name}|{period}",
                    message=(
                        f"{_subject(snapshot)} is due {item.name} (every {item.interval} cycles)."
                    ),
                    detail={"name": item.name, "interval": item.interval, "used": item.used},
                )
            )
        return events

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _is_stale(snapshot: Snapshot, memory: ApplianceMemory) -> bool:
        """Whether this reading describes a moment we have already moved past.

        A poll and a pushed update race each other constantly, and the poll can
        easily describe an older moment. Ordering by when the reading was taken
        - not by when it arrived - is what stops a stale poll undoing a push.
        """
        return memory.observed_at is not None and snapshot.observed_at < memory.observed_at

    @staticmethod
    def _cycles_completed_while_away(snapshot: Snapshot, memory: ApplianceMemory) -> int | None:
        """How many cycles finished during the gap, or None if none did.

        Zero is a distinct answer from None: it means "something finished but the
        appliance cannot tell us how many", which still deserves an honest
        report. The counter is what separates a completed cycle from a cancelled
        one, so without it we only claim a completion when the machine itself
        says FINISHED.
        """
        if snapshot.cycle_count is not None and memory.cycle_count is not None:
            moved = snapshot.cycle_count - memory.cycle_count
            return moved if moved > 0 else None
        if memory.state in _RUNNING_STATES and snapshot.state is ApplianceState.FINISHED:
            return 0
        return None

    @staticmethod
    def _finished_key(snapshot: Snapshot) -> str:
        """Identity of a completed cycle.

        Live completions and gap-detected ones share this key space on purpose:
        if a cycle was announced as it happened, a later restart that infers the
        same completion from the counter must not announce it a second time.
        """
        if snapshot.cycle_count is not None:
            return f"{snapshot.appliance_id}|finished|{snapshot.cycle_count}"
        return f"{snapshot.appliance_id}|finished|{snapshot.observed_at:%Y-%m-%dT%H:%M}"

    def _remember(self, snapshot: Snapshot, memory: ApplianceMemory) -> None:
        self._memory.put(memory.updated_with(snapshot))


def _subject(snapshot: Snapshot) -> str:
    return f"The {snapshot.name}" if snapshot.name else "The appliance"


def replay(tracker: Tracker, snapshots: Iterable[Snapshot]) -> list[Event]:
    """Feed a recorded sequence through a tracker. Used by the tests."""
    events: list[Event] = []
    for snapshot in snapshots:
        events.extend(tracker.observe(snapshot))
    return events
