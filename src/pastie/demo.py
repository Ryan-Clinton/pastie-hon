"""Watch Pastie work, without an appliance.

`pastie demo` replays recorded appliance readings through the **real** connector,
the **real** brain and the **real** command tracker, and prints what it decided
and why. No hOn account, no network, no dryer, no Windows service.

That is not a toy: it is the same code path a real cycle takes, and it exists
because the interesting behaviour of this project is impossible to show in a
screenshot. "Announces nothing on the first reading", "reports a gap rather than
news", "refuses to call an accepted command done" - all of it is about *time*,
and the only honest way to demonstrate it is to run it.

The readings are the values the tested Haier HD90-A2959R-UK actually reports.
The timestamps are invented, because timing is the thing each scenario varies.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pastie.connector.profiles import TUMBLE_DRYER, Profile, unverified
from pastie.connector.reading import RawReading, translate
from pastie.core.commands import CommandOutcome, CommandSpec, CommandTracker, stop_programme
from pastie.core.events import Event
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.tracker import Tracker

APPLIANCE = "a1b2c3d4e5f6"
START = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)

Out = Callable[[str], None]


# --------------------------------------------------------------- the steps


@dataclass
class Look:
    """A reading arrives."""

    minute: float
    parameters: dict[str, str]
    counter: int | None = None
    programme: str = "hqd_mix"
    note: str = ""
    profile: Profile = TUMBLE_DRYER

    def reading(self) -> RawReading:
        statistics: dict[str, Any] = {}
        if self.counter is not None:
            statistics = {
                "programsCounter": self.counter,
                "filterCleaning": {"tot": 15, "count": self.counter},
            }
        return RawReading(
            appliance_id=APPLIANCE,
            observed_at=START + timedelta(minutes=self.minute),
            parameters=self.parameters,
            identity={
                "applianceTypeName": self.profile.appliance_type,
                "modelName": "HD90-A2959R-UK" if self.profile is TUMBLE_DRYER else "SOMETHING",
            },
            statistics=statistics,
            programme_name=self.programme,
        )


@dataclass
class Restart:
    """Pastie stops and starts again. The memory survives; the session does not."""

    note: str = "Pastie is restarted"


@dataclass
class Send:
    """A command goes out, and Haier takes it."""

    minute: float
    spec: CommandSpec
    accepted: bool = True
    note: str = ""


Step = Look | Restart | Send


@dataclass
class Scenario:
    key: str
    title: str
    why: str
    steps: list[Step] = field(default_factory=list)


# ----------------------------------------------------------- the readings

#: The values the machine reports, as observed. `machMode` 1 is idle, 2 running,
#: 7 the finish signal; `dryTimeMM` is the honest total and `remainingTimeMM`
#: wanders above it while the machine is still measuring the load.
IDLE = {"machMode": "1", "remainingTimeMM": "270", "dryTimeMM": "0", "remoteCtrValid": "1"}
SENSING = {"machMode": "2", "remainingTimeMM": "120", "dryTimeMM": "90", "remoteCtrValid": "1"}
RUNNING = {"machMode": "2", "remainingTimeMM": "45", "dryTimeMM": "90", "remoteCtrValid": "1"}
NEARLY = {"machMode": "2", "remainingTimeMM": "8", "dryTimeMM": "90", "remoteCtrValid": "1"}
FINISHED = {"machMode": "7", "remainingTimeMM": "0", "dryTimeMM": "90", "remoteCtrValid": "0"}
FAULTED = {"machMode": "6", "remainingTimeMM": "0", "dryTimeMM": "90", "errors": "E4"}


def scenarios() -> dict[str, Scenario]:
    """Every scenario the demo can run, in the order they are worth watching."""
    ordered = (_cycle(), _gap(), _noise(), _ignored(), _oven())
    return {scenario.key: scenario for scenario in ordered}


def _cycle() -> Scenario:
    return Scenario(
        key="cycle",
        title="A cycle, watched from start to finish",
        why=(
            "One load, four readings, and exactly one thing worth shouting about. "
            "Note that the first reading announces nothing, and that the time "
            "remaining is not quoted as a fact while the machine is still guessing."
        ),
        steps=[
            Look(0, IDLE, counter=3, programme="No Program", note="Pastie starts. Baseline only."),
            Look(5, SENSING, counter=3, note="Still working out how wet the load is"),
            Look(20, RUNNING, counter=3, note="Now counting down honestly"),
            Look(85, NEARLY, counter=3),
            Look(90, FINISHED, counter=4, note="The counter moved: a cycle completed"),
        ],
    )


def _gap() -> Scenario:
    return Scenario(
        key="gap",
        title="A cycle that finished while Pastie was switched off",
        why=(
            "The hard case. Pastie sees it running, the PC reboots, and by the time "
            "anyone looks again the machine says finished. That is a real completion "
            "and must be reported - but as a gap, not as news, because nobody knows "
            "when it happened. The cycle counter is what turns an apology into a fact."
        ),
        steps=[
            Look(0, IDLE, counter=3, programme="No Program"),
            Look(10, RUNNING, counter=3, note="Last seen running at 20:10"),
            Restart("The PC reboots. The cycle finishes while nothing is watching."),
            Look(70, FINISHED, counter=4, note="Counter 3 -> 4 while away"),
        ],
    )


def _noise() -> Scenario:
    return Scenario(
        key="noise",
        title="The same update twice, and a poll that arrives late",
        why=(
            "Haier's push delivers at least once, so duplicates are the contract "
            "rather than a fault, and a periodic poll regularly describes an older "
            "moment than a push that already landed. Neither may produce a second "
            "announcement, and the late poll must not resurrect the old state."
        ),
        steps=[
            Look(0, RUNNING, counter=3, note="Pastie starts mid-cycle. Silence."),
            Look(90, FINISHED, counter=4, note="The push arrives"),
            Look(90, FINISHED, counter=4, note="...and arrives again"),
            Look(88, RUNNING, counter=3, note="A poll describing 21:28 - two minutes stale"),
            Look(95, FINISHED, counter=4),
        ],
    )


def _ignored() -> Scenario:
    return Scenario(
        key="ignored",
        title="Haier accepts a command the machine then ignores",
        why=(
            "Measured on the real appliance: a stop command returned success while "
            "the dryer carried on. Accepted by a server is not done by a machine, "
            "and Pastie will not say otherwise."
        ),
        steps=[
            Look(0, RUNNING, counter=3),
            Send(1, stop_programme(), accepted=True, note="Haier takes the message"),
            Look(1.2, RUNNING, counter=3, note="Still running"),
            Look(1.5, RUNNING, counter=3, note="Still running, and the deadline passes"),
        ],
    )


def _oven() -> Scenario:
    oven = unverified("OV")
    return Scenario(
        key="unverified",
        title="An appliance nobody here has verified",
        why=(
            "Mode 6 means a fault on the tested dryer. On an oven it means whatever "
            "the oven's manufacturer decided, and this project does not own one. So "
            "the oven is detected and named, its raw values are shown, and nothing "
            "is interpreted or announced."
        ),
        steps=[
            Look(0, {"machMode": "1"}, programme="", profile=oven, note="Detected and named"),
            Look(
                5,
                {"machMode": "6", "errors": "E4"},
                programme="",
                profile=oven,
                note="Would be a fault on a dryer. Not announced here.",
            ),
        ],
    )


# ------------------------------------------------------------- the runner


def run(scenario: Scenario, out: Out = print) -> list[Event]:
    """Play a scenario through the real code, narrating as it goes."""
    memory, ledger = MemoryStore(), Ledger()
    tracker = Tracker(memory, ledger)
    commands = CommandTracker()
    announced: list[Event] = []

    out("")
    out(f"  {scenario.title}")
    out(f"  {'-' * len(scenario.title)}")
    for line in _wrap(scenario.why):
        out(f"  {line}")
    out("")

    for step in scenario.steps:
        if isinstance(step, Restart):
            tracker = Tracker(memory, ledger)  # a new session; the memory persists
            out(f"         ---  {step.note}  ---")
            continue

        if isinstance(step, Send):
            progress = commands.request(
                step.spec, APPLIANCE, _at(step.minute), tracker_snapshot(memory)
            )
            if step.accepted and not progress.outcome.is_final:
                commands.accepted(APPLIANCE, _at(step.minute))
            out(f"  {_clock(step.minute)}  COMMAND   {step.spec.name} - {step.note}")
            continue

        snapshot = translate(step.reading(), step.profile)
        settled = commands.observe(snapshot)
        events = tracker.observe(snapshot)
        announced.extend(events)

        out(f"  {_clock(step.minute)}  reading   {_describe(snapshot)}")
        if step.note:
            out(f"                      ({step.note})")
        if settled is not None:
            outcome = "confirmed" if settled.outcome is CommandOutcome.CONFIRMED else "NOT done"
            out(f"                      command {outcome}: {settled.lines()[-1]}")
        for event in events:
            marker = "ANNOUNCE " if event.is_alert else "note     "
            out(f"  {_clock(step.minute)}  {marker} {event.message}")

    out("")
    alerts = [event for event in announced if event.is_alert]
    out(f"  {len(announced)} event(s), {len(alerts)} worth interrupting somebody for.")
    out("")
    return announced


def tracker_snapshot(memory: MemoryStore) -> Any:
    """The last reading, as the command tracker needs it for its precondition."""
    remembered = memory.get(APPLIANCE)
    return translate(
        Look(0, RUNNING if remembered.state.is_known else IDLE).reading(), TUMBLE_DRYER
    )


def _describe(snapshot: Any) -> str:
    bits = [snapshot.state.value]
    if snapshot.programme:
        bits.append(snapshot.programme)
    if snapshot.remaining is not None:
        bits.append(snapshot.display_remaining())
    if snapshot.fault_code:
        bits.append(f"fault {snapshot.fault_code}")
    if not snapshot.is_verified:
        bits.append("unverified - raw only")
    return ", ".join(bits)


def _clock(minute: float) -> str:
    return f"{START + timedelta(minutes=minute):%H:%M}"


def _at(minute: float) -> datetime:
    return START + timedelta(minutes=minute)


def _wrap(text: str, width: int = 74) -> Iterator[str]:
    line: list[str] = []
    for word in text.split():
        if sum(len(w) + 1 for w in line) + len(word) > width:
            yield " ".join(line)
            line = []
        line.append(word)
    if line:
        yield " ".join(line)
