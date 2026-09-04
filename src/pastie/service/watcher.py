"""The long-running part: watch, decide, tell somebody.

One connection to Haier's servers, ever. The app does not open its own - it asks
this - so the two can never disagree about what the machine is doing.

The loop is deliberately dull:

    connect -> subscribe -> wait for a push or the poll interval -> read
            -> translate -> tracker -> messengers

Everything interesting is in what happens when it goes wrong. A dropped
connection re-baselines the tracker, because the MQTT session Haier negotiates
persists nothing and replays nothing: after a reconnect a full refresh is not a
precaution, it is the only correct behaviour. A failure is classified into
something a user can act on. And a command that was accepted is followed up
until the machine either does it or is judged to have ignored it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pastie.connector.profiles import Profile
from pastie.connector.reading import RawReading, translate
from pastie.core.commands import CommandProgress, CommandSpec, CommandTracker
from pastie.core.events import Event
from pastie.core.health import Health, HealthMonitor, HealthReport
from pastie.core.state import Snapshot
from pastie.core.tracker import Tracker
from pastie.messengers.base import Delivery, MessengerRunner
from pastie.service.config import SettingsStore

log = logging.getLogger(__name__)

#: How long to wait after a failure before trying again, in seconds. Backs off
#: so a Haier outage is not hammered, and stops backing off at a minute so a
#: brief one is not punished with a long wait.
_BACKOFF = (5, 10, 20, 40, 60)

#: While a command is in flight, ask more often - the user is watching a screen
#: that says "waiting for the machine", and twenty seconds of nothing is a long
#: time to look at.
_URGENT_SECONDS = 5


class ApplianceConnector(Protocol):
    """What the watcher needs from a connector. `HonConnector` is the one."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def read(self, *, with_statistics: bool = True) -> list[RawReading]: ...

    def profile(self, appliance_id: str) -> Profile: ...

    def subscribe(self, callback: Callable[[], None]) -> None: ...

    async def send(self, appliance_id: str, command: str, arguments: dict[str, Any]) -> None: ...


@dataclass
class ApplianceStatus:
    """One appliance, as the window shows it."""

    id: str
    name: str
    model: str
    state: str
    trust: str
    updated_at: str
    programme: str | None = None
    remaining: str = "unknown"
    progress: float | None = None
    door_open: bool | None = None
    remote_allowed: bool | None = None
    fault_code: str | None = None
    cycle_count: int | None = None
    maintenance: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    #: What this appliance can be asked to do, and with what - sent from here so
    #: the window never has to hold a list of Haier's programme identifiers.
    programmes: list[dict[str, str]] = field(default_factory=list)
    dry_levels: list[dict[str, str]] = field(default_factory=list)
    temperatures: list[dict[str, str]] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, snapshot: Snapshot, profile: Profile | None = None) -> ApplianceStatus:
        return cls(
            id=snapshot.appliance_id,
            name=snapshot.name,
            model=snapshot.model,
            state=snapshot.state.value,
            trust=snapshot.trust.value,
            updated_at=snapshot.observed_at.isoformat(),
            programme=snapshot.programme,
            remaining=snapshot.display_remaining(),
            progress=snapshot.progress,
            door_open=snapshot.door_open,
            remote_allowed=snapshot.remote_allowed,
            fault_code=snapshot.fault_code,
            cycle_count=snapshot.cycle_count,
            maintenance=[
                {
                    "name": item.name,
                    "interval": item.interval,
                    "remaining": item.remaining,
                    "due": item.due,
                }
                for item in snapshot.maintenance
            ],
            raw=dict(snapshot.raw),
            programmes=_choices(profile.programmes if profile else {}),
            dry_levels=_choices(profile.dry_levels if profile else {}),
            temperatures=_choices(profile.temperatures if profile else {}),
            # An unverified appliance offers no commands at all, whatever Haier's
            # data claims is available on it.
            commands=sorted(profile.commands) if profile and profile.states_verified else [],
        )


@dataclass
class Status:
    """Everything the app asks for, in one reply."""

    health: str
    health_message: str
    appliances: list[ApplianceStatus] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    command: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "health": self.health,
            "health_message": self.health_message,
            "appliances": [vars(appliance) for appliance in self.appliances],
            "recent": self.recent,
            "command": self.command,
        }


def _choices(mapping: Mapping[str, str]) -> list[dict[str, str]]:
    """A mapping as an ordered list the window can put straight into a dropdown."""
    seen: dict[str, str] = {}
    for value, label in mapping.items():
        seen.setdefault(label, value)
    return [{"id": value, "label": label} for label, value in sorted(seen.items())]


class Watcher:
    """Holds the connection, the brain and the messengers together."""

    def __init__(
        self,
        connector: ApplianceConnector,
        tracker: Tracker,
        messengers: MessengerRunner,
        settings: SettingsStore,
        *,
        health: HealthMonitor | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self._connector = connector
        self._tracker = tracker
        self._messengers = messengers
        self._settings = settings
        self._health = health or HealthMonitor()
        self._now = now
        self._sleep = sleep

        self._snapshots: dict[str, Snapshot] = {}
        self._commands = CommandTracker()
        self._recent: list[Event] = []
        self._wake = asyncio.Event()
        self._reads = 0

    # ------------------------------------------------------------ the loop

    async def run(self, stop: asyncio.Event) -> None:
        """Watch until asked to stop. Reconnects on its own.

        The connection is closed on the way out of every attempt, successful or
        not. Leaving it open leaks the client's HTTP session, which shows up as
        "Unclosed client session" at exit and, less visibly, as a socket per
        reconnect on a machine that has been up for a week.
        """
        failures = 0
        while not stop.is_set():
            try:
                await self._connect_and_watch(stop)
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - classified, then retried
                report = self._health.failed(self._now(), error)
                log.warning("watch failed (%s): %s", report.state.value, error)
                self.connection_dropped()
                await self._sleep(_BACKOFF[min(failures, len(_BACKOFF) - 1)])
                failures += 1
            finally:
                await self._close_quietly()

    async def _close_quietly(self) -> None:
        try:
            await self._connector.close()
        except Exception as error:  # noqa: BLE001 - tidying up must not raise
            log.debug("ignored while closing the connection: %s", error)

    async def _connect_and_watch(self, stop: asyncio.Event) -> None:
        await self._connector.connect()
        self._subscribe()
        await self.refresh()

        while not stop.is_set():
            await self._wait_for_work()
            if stop.is_set():
                return
            await self.refresh()

    async def _wait_for_work(self) -> None:
        """Sleep until something pushes, or until the next poll is due."""
        settings = self._settings.load()
        seconds = _URGENT_SECONDS if self._commands.active_any() else settings.poll_seconds
        self._wake.clear()
        try:
            async with asyncio.timeout(seconds):
                await self._wake.wait()
        except TimeoutError:
            return

    def _subscribe(self) -> None:
        """Ask for pushed updates, and wake the loop when one lands.

        The callback arrives on the client's own thread, so it may not touch the
        event loop directly - hence `call_soon_threadsafe`. Getting this wrong
        produces an update that is only noticed at the next poll, which looks
        exactly like push not working at all.
        """
        loop = asyncio.get_running_loop()

        def pushed() -> None:
            loop.call_soon_threadsafe(self._wake.set)

        try:
            self._connector.subscribe(pushed)
        except Exception as error:  # noqa: BLE001 - polling still works without it
            log.warning("pushed updates are unavailable, polling instead: %s", error)

    # ------------------------------------------------------------- reading

    async def refresh(self) -> list[Event]:
        """Read every appliance once, and act on whatever it means."""
        settings = self._settings.load()
        self._reads += 1
        with_statistics = self._reads % max(1, settings.statistics_every) == 1

        readings = await self._connector.read(with_statistics=with_statistics)
        self._health.ok(self._now())

        events: list[Event] = []
        for reading in readings:
            snapshot = translate(reading, self._connector.profile(reading.appliance_id))
            self._snapshots[snapshot.appliance_id] = snapshot
            self._commands.observe(snapshot)
            log.debug(
                "%s is %s (%s)", snapshot.name, snapshot.state.value, snapshot.display_remaining()
            )
            events.extend(self._tracker.observe(snapshot))

        for event in events:
            log.info("%s", event.message)
            self._recent = ([event, *self._recent])[:20]
            await self._deliver(event)
        return events

    async def _deliver(self, event: Event) -> list[Delivery]:
        if not event.is_alert:
            return []
        settings = self._settings.load()
        return await self._messengers.deliver(event, settings.messengers)

    def connection_dropped(self) -> None:
        """A dropped connection means the next reading is a fresh baseline.

        Anything that changed while we were away is then reported as a gap -
        honestly - rather than as something we watched happen.
        """
        self._tracker.forget_session()

    # ------------------------------------------------------------ commands

    async def send(
        self, appliance_id: str, spec: CommandSpec, command: str, arguments: dict[str, Any]
    ) -> CommandProgress:
        """Ask the machine to do something, and follow it up until it has.

        Returns as soon as Haier has answered. The outcome the user cares about -
        whether the appliance actually did it - arrives on a later reading, and
        `status()` shows which step it has reached.
        """
        snapshot = self._snapshots.get(appliance_id)
        progress = self._commands.request(spec, appliance_id, self._now(), snapshot)
        if progress.outcome.is_final:
            return progress

        try:
            await self._connector.send(appliance_id, command, arguments)
        except Exception as error:  # noqa: BLE001 - the reason is shown to the user
            rejected = self._commands.rejected(appliance_id, self._now(), str(error))
            return rejected or progress

        self._commands.accepted(appliance_id, self._now())
        self._wake.set()  # start watching for the machine to react
        return progress

    # -------------------------------------------------------------- status

    def status(self) -> Status:
        report: HealthReport = self._health.report
        active = self._commands.active_lines()
        return Status(
            health=report.state.value,
            health_message=report.message,
            appliances=[
                ApplianceStatus.of(snapshot, self._connector.profile(appliance_id))
                for appliance_id, snapshot in self._snapshots.items()
            ],
            recent=[
                {
                    "kind": event.kind.value,
                    "at": event.at.isoformat(),
                    "message": event.message,
                }
                for event in self._recent
            ],
            command=active,
        )

    @property
    def health(self) -> Health:
        return self._health.report.state

    def snapshot(self, appliance_id: str) -> Snapshot | None:
        return self._snapshots.get(appliance_id)

    def messenger_settings(self) -> Mapping[str, Mapping[str, Any]]:
        return self._settings.load().messengers
