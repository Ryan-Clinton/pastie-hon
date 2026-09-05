"""What a messenger is, and the rules every one of them follows.

A messenger is anything Pastie can poke when something happens: a light, a
speaker, a webhook, a phone notification. Writing one means writing a single
file and sending a pull request - not writing any interface code, because a
messenger *describes* its settings and the settings screen draws itself from
that description.

The rules below are enforced here rather than trusted to each messenger,
because "please remember to" does not survive a dozen contributors:

* **A messenger failing must not take anything else down.** They run
  concurrently, each with its own timeout, each isolated from the others. A
  speaker that is switched off must not stop the light flashing.
* **Don't strobe.** Flash rate and duration are capped centrally, in
  `pastie.messengers.flash`, and no messenger can go round it.
* **One alert at a time per target.** Two events landing together must not both
  snapshot a light's state and both restore it, or they trample each other.
* **Never write a password, key or token to a log.** `redact` exists so there is
  no excuse.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pastie.core.events import Event, EventKind

log = logging.getLogger(__name__)

#: How long any one messenger gets before it is abandoned. Generous enough for a
#: speaker to render and play, short enough that a hung one is not a hung Pastie.
DEFAULT_TIMEOUT = 60.0


class Kind(Enum):
    """The kinds of setting a messenger can ask for.

    The settings screen knows how to draw each of these and nothing else, which
    is the deal: a messenger that needs a widget nobody has built is a
    conversation, not a surprise.
    """

    TEXT = "text"
    SECRET = "secret"  # never logged, never shown back
    NUMBER = "number"
    BOOL = "bool"
    CHOICE = "choice"  # fixed list
    TARGET = "target"  # filled from discover(): which light, which speaker


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    kind: Kind = Kind.TEXT
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str = ""
    #: Whether this setting can differ per alert - a colour per event, a
    #: different sentence for a full tank than for a finished cycle. The
    #: settings screen draws an extra row per alert for anything marked, and
    #: `MessengerRunner` applies the override. The messenger itself is none the
    #: wiser: it receives one config and does as it is told.
    per_event: bool = False


@dataclass(frozen=True)
class Target:
    """One thing a messenger could poke: a light, a speaker, a device."""

    id: str
    label: str
    detail: str = ""
    #: Whether this target is reachable right now. Shown, not enforced - a light
    #: that is switched off at the wall is a fact about the house, not an error.
    available: bool = True


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str = ""
    messenger: str = ""

    @classmethod
    def worked(cls, detail: str = "") -> Result:
        return cls(True, detail)

    @classmethod
    def failed(cls, detail: str) -> Result:
        return cls(False, detail)


@runtime_checkable
class Messenger(Protocol):
    """Everything a messenger must be able to do.

    Four things, and only the last one is about the event: describe its
    settings, find things, fire once on demand, and react.
    """

    name: str
    label: str

    def settings(self) -> Iterable[Setting]:
        """What to ask the user for. The settings screen is drawn from this."""

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:
        """The lights, speakers or devices available to this messenger."""

    async def test(self, config: Mapping[str, Any]) -> Result:
        """Fire once, now, so the user can see whether it works."""

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        """Do the thing."""


def sample_event(message: str = "This is a test from Pastie.") -> Event:
    """A stand-in event, so `test()` is the same code path as a real alert.

    A test button that takes a different route through the code tests the wrong
    thing - it is the paths a real alert takes that need proving.
    """
    return Event(
        kind=EventKind.CYCLE_FINISHED,
        appliance_id="test",
        at=datetime.now(UTC),
        key="test",
        message=message,
    )


#: Where a messenger's per-alert overrides live inside its settings.
OVERRIDES = "when"


def for_event(config: Mapping[str, Any], event: Event) -> dict[str, Any]:
    """A messenger's settings as they apply to *this* alert.

    Overrides live under `when`, keyed by event kind:

        {"colour": "Green", "when": {"fault": {"colour": "Red"}}}

    Merged here rather than in each messenger, for the same reason the flash cap
    is: a rule every author has to remember is a rule that gets forgotten. A
    messenger receives one flat config and cannot tell the difference.
    """
    overrides = config.get(OVERRIDES)
    if not isinstance(overrides, dict):
        return dict(config)
    wanted = overrides.get(event.kind.value)
    if not isinstance(wanted, dict):
        return dict(config)
    # An override that is blank means "no opinion, use the usual one" - which is
    # what an empty box on the settings screen should mean.
    return {**config, **{key: value for key, value in wanted.items() if value not in (None, "")}}


def redact(value: str | None, keep: int = 4) -> str:
    """A key or token as it may appear in a log: enough to recognise, not to use."""
    if not value:
        return "(unset)"
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep)}"


@dataclass
class Delivery:
    """One messenger's attempt at one event."""

    messenger: str
    result: Result
    event_id: str = ""


class MessengerRunner:
    """Runs the configured messengers for an event, isolated from each other.

    Isolation is the whole job. Every messenger here is talking to hardware or a
    third party over a network - a bridge that has rebooted, a speaker that is
    unplugged, an undocumented speech endpoint that has changed - and any of
    them can hang. None of them may take the others with it.
    """

    def __init__(self, messengers: Mapping[str, Messenger], timeout: float = DEFAULT_TIMEOUT):
        self._messengers = dict(messengers)
        self._timeout = timeout

    async def deliver(
        self, event: Event, configs: Mapping[str, Mapping[str, Any]]
    ) -> list[Delivery]:
        """Fire every enabled messenger at once. Returns what each one managed.

        Configs are keyed by messenger name; a messenger with no config, or one
        turned off, is skipped silently. Enabling something you have not set up
        is not an error worth an alert.
        """
        jobs = [
            self._run(messenger, event, for_event(configs[name], event))
            for name, messenger in self._messengers.items()
            if configs.get(name, {}).get("enabled")
        ]
        if not jobs:
            return []
        return list(await asyncio.gather(*jobs))

    async def _run(self, messenger: Messenger, event: Event, config: Mapping[str, Any]) -> Delivery:
        try:
            async with asyncio.timeout(self._timeout):
                result = await messenger.react(event, config)
        except TimeoutError:
            log.warning("%s timed out after %.0fs", messenger.name, self._timeout)
            result = Result.failed(f"timed out after {self._timeout:.0f}s")
        except Exception as error:  # noqa: BLE001 - isolation is the entire point
            log.warning("%s failed: %s", messenger.name, error)
            result = Result.failed(f"{type(error).__name__}: {error}")
        return Delivery(messenger=messenger.name, result=result, event_id=event.id)


@dataclass
class Registry:
    """The messengers this build knows about.

    Contributions go in the main codebase rather than separate plugin packages,
    for a boring reason: the packaged .exe can only contain code that existed
    when it was built.
    """

    messengers: dict[str, Messenger] = field(default_factory=dict)

    def add(self, messenger: Messenger) -> None:
        self.messengers[messenger.name] = messenger

    def get(self, name: str) -> Messenger | None:
        return self.messengers.get(name)

    def __iter__(self) -> Any:
        return iter(self.messengers.values())

    def __len__(self) -> int:
        return len(self.messengers)
