"""Commands, and how we know one actually worked.

Sending a command to Haier's servers returns success as soon as they have taken
the message. That is not the same as the machine having done anything: a stop
command has been observed returning success while the appliance sat there
ignoring it.

So every command runs through the same sequence, and the user is shown which
part of it actually happened:

    requested -> accepted by Haier -> confirmed by the machine
                                   \\-> rejected | timed out | refused

Nothing here talks to Haier. It takes the two facts the outside world provides -
"they accepted it" and "here is a later reading of the machine" - and decides
what they add up to.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from pastie.core.state import ApplianceState, Snapshot

#: Long enough for a machine that is going to react to have reacted; short
#: enough that the user is not left watching a spinner. Twenty seconds is what
#: the tested dryer needed, with room to spare.
DEFAULT_DEADLINE = timedelta(seconds=20)


class CommandOutcome(Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    CONFIRMED = "confirmed"
    REFUSED = "refused"  # we would not send it - a precondition failed
    REJECTED = "rejected"  # Haier would not take it
    TIMED_OUT = "timed_out"  # accepted, but the machine never did it

    @property
    def is_final(self) -> bool:
        return self is not CommandOutcome.REQUESTED and self is not CommandOutcome.ACCEPTED

    @property
    def succeeded(self) -> bool:
        return self is CommandOutcome.CONFIRMED


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """What to send, what would prove it worked, and how long to wait.

    `confirms` is the important field. A command with no way to prove it worked
    has no business being offered: reporting success off the back of the server
    response alone is the exact mistake this module exists to prevent.
    """

    name: str
    confirms: Callable[[Snapshot], bool]
    deadline: timedelta = DEFAULT_DEADLINE
    #: Returns a reason to refuse, or None to allow. Preconditions protect the
    #: appliance's own safety interlocks - never bypass one, only respect it.
    precondition: Callable[[Snapshot], str | None] | None = None
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass
class CommandProgress:
    """The live record of one attempt, as the user sees it."""

    id: str
    name: str
    appliance_id: str
    requested_at: datetime
    outcome: CommandOutcome = CommandOutcome.REQUESTED
    accepted_at: datetime | None = None
    confirmed_at: datetime | None = None
    reason: str | None = None
    rejected_at: datetime | None = None
    #: Recorded so `lines()` can report the deadline the attempt was held to.
    deadline_seconds: float | None = None

    def lines(self) -> list[str]:
        """The progress display from the specification, verbatim in shape."""
        out = [f"{self.name} requested".ljust(24) + f"{self.requested_at:%H:%M:%S}"]
        if self.accepted_at:
            out.append("Accepted by Haier".ljust(24) + f"{self.accepted_at:%H:%M:%S}")
        if self.confirmed_at:
            out.append("Machine confirmed".ljust(24) + f"{self.confirmed_at:%H:%M:%S}   OK")
        if self.outcome is CommandOutcome.TIMED_OUT:
            seconds = int(self.deadline_seconds or 0)
            out.append(f"Accepted by Haier, but the machine didn't react within {seconds} seconds")
        if self.outcome in (CommandOutcome.REFUSED, CommandOutcome.REJECTED) and self.reason:
            out.append(self.reason)
        return out


class CommandTracker:
    """Follows commands from requested to proven, one appliance at a time."""

    def __init__(self) -> None:
        self._active: dict[str, tuple[CommandProgress, CommandSpec]] = {}
        self._history: list[CommandProgress] = []

    @property
    def history(self) -> list[CommandProgress]:
        return list(self._history)

    def active(self, appliance_id: str) -> CommandProgress | None:
        found = self._active.get(appliance_id)
        return found[0] if found else None

    def active_any(self) -> bool:
        """Whether anything is still waiting on the machine.

        The watcher reads more often while this is true: somebody is looking at
        a screen that says "waiting", and twenty seconds of nothing is a long
        time to look at.
        """
        return bool(self._active)

    def active_lines(self) -> list[str]:
        """The progress display for the attempt worth showing.

        The one in flight if there is one, otherwise the last one to finish -
        so the outcome stays on screen instead of vanishing the moment it is
        known.
        """
        for progress, _ in self._active.values():
            return progress.lines()
        return self._history[-1].lines() if self._history else []

    def request(
        self, spec: CommandSpec, appliance_id: str, at: datetime, snapshot: Snapshot | None = None
    ) -> CommandProgress:
        """Begin an attempt. Refuses on the spot if a precondition fails."""
        progress = CommandProgress(
            id=uuid.uuid4().hex,
            name=spec.name,
            appliance_id=appliance_id,
            requested_at=at,
            deadline_seconds=spec.deadline.total_seconds(),
        )
        if snapshot is not None and spec.precondition is not None:
            refusal = spec.precondition(snapshot)
            if refusal:
                progress.outcome = CommandOutcome.REFUSED
                progress.reason = refusal
                self._history.append(progress)
                return progress
        self._active[appliance_id] = (progress, spec)
        return progress

    def accepted(self, appliance_id: str, at: datetime) -> CommandProgress | None:
        found = self._active.get(appliance_id)
        if not found:
            return None
        progress, _ = found
        progress.accepted_at = at
        progress.outcome = CommandOutcome.ACCEPTED
        return progress

    def rejected(self, appliance_id: str, at: datetime, reason: str) -> CommandProgress | None:
        """Haier would not take the command. `at` is recorded as the end of the attempt."""
        found = self._active.pop(appliance_id, None)
        if not found:
            return None
        progress, _ = found
        progress.outcome = CommandOutcome.REJECTED
        progress.reason = reason
        progress.rejected_at = at
        progress.confirmed_at = None
        self._history.append(progress)
        return progress

    def observe(self, snapshot: Snapshot) -> CommandProgress | None:
        """Feed a reading in. Returns the attempt if this reading settled it.

        Confirmation is a state the *machine* reports, never a response from a
        server, and the deadline is measured from acceptance rather than from
        the request so a slow network does not read as an ignored command.
        """
        found = self._active.get(snapshot.appliance_id)
        if not found:
            return None
        progress, spec = found

        if spec.confirms(snapshot):
            progress.outcome = CommandOutcome.CONFIRMED
            progress.confirmed_at = snapshot.observed_at
            self._settle(snapshot.appliance_id, progress)
            return progress

        started = progress.accepted_at or progress.requested_at
        if snapshot.observed_at - started >= spec.deadline:
            progress.outcome = CommandOutcome.TIMED_OUT
            self._settle(snapshot.appliance_id, progress)
            return progress
        return None

    def _settle(self, appliance_id: str, progress: CommandProgress) -> None:
        self._active.pop(appliance_id, None)
        self._history.append(progress)


# --------------------------------------------------------------------- specs


def requires_remote_allowed(snapshot: Snapshot) -> str | None:
    """The interlock on the tested dryer, expressed in plain terms.

    The machine itself refuses a remote start unless somebody has switched it on
    and turned the dial to the remote position, and it disarms again after every
    completed cycle. Pastie checks first so the user gets a sentence explaining
    what to do, instead of a rejection from a server - but the machine's refusal
    is the real protection, and nothing here may attempt to defeat it.
    """
    if snapshot.remote_allowed:
        return None
    return (
        "The machine isn't armed for remote control. Switch it on and turn the "
        "dial to the remote position, then try again."
    )


def start_programme(programme: str, **arguments: object) -> CommandSpec:
    """Start an already-armed cycle, and prove it by the machine running."""
    return CommandSpec(
        name="Start",
        confirms=lambda snapshot: snapshot.state is ApplianceState.RUNNING,
        precondition=requires_remote_allowed,
        arguments={"programme": programme, **arguments},
    )


def stop_programme() -> CommandSpec:
    """Stop a cycle, and prove it by the machine no longer running.

    This is the command that was seen returning success while the appliance
    carried on regardless, which is why it is confirmed rather than believed.
    """
    return CommandSpec(
        name="Stop",
        confirms=lambda snapshot: (
            snapshot.state not in (ApplianceState.RUNNING, ApplianceState.PAUSED)
        ),
    )
