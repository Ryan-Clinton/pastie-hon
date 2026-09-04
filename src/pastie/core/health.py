"""How Pastie itself is doing.

"It's not working" is a useless error message. Each of these needs a different
response from the person reading it, so they are different states rather than
different wordings of one:

    OK          working normally
    SLOW        working, but updates are late
    AUTH        can't log in - check the password
    SCHEMA      can't understand Haier's response - something changed, needs a fix
    OFFLINE     can't reach the internet

SCHEMA is the one worth having. It is the difference between a user changing
their password for no reason and an issue that says "Haier moved something".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class Health(Enum):
    OK = "ok"
    SLOW = "slow"
    AUTH = "auth"
    SCHEMA = "schema"
    OFFLINE = "offline"

    @property
    def is_working(self) -> bool:
        return self in (Health.OK, Health.SLOW)


#: What each state means, in the words the user should see.
DESCRIPTIONS = {
    Health.OK: "Working normally",
    Health.SLOW: "Working, but updates are slow",
    Health.AUTH: "Can't log in - check your hOn password",
    Health.SCHEMA: "Can't understand Haier's response - something has changed and needs a fix",
    Health.OFFLINE: "Can't reach the internet",
}


@dataclass(frozen=True, slots=True)
class HealthReport:
    state: Health
    since: datetime | None
    detail: str = ""

    @property
    def message(self) -> str:
        base = DESCRIPTIONS[self.state]
        return f"{base} - {self.detail}" if self.detail else base


class HealthMonitor:
    """Turns what happened into one of the five states.

    Classification is by *what the caller can do about it*, not by exception
    type. Anything unrecognised is SCHEMA rather than a generic failure,
    deliberately: an unexpected shape in Haier's response is the failure this
    project should expect most, and the one a user can most usefully report.
    """

    def __init__(self, stale_after: timedelta = timedelta(minutes=10)) -> None:
        self._stale_after = stale_after
        self._state = Health.OK
        self._since: datetime | None = None
        self._detail = ""

    @property
    def report(self) -> HealthReport:
        return HealthReport(self._state, self._since, self._detail)

    def ok(self, at: datetime) -> HealthReport:
        return self._set(Health.OK, at, "")

    def degraded(self, at: datetime, last_update: datetime | None) -> HealthReport:
        """Nothing has arrived for a while, but nothing has failed either."""
        if last_update is not None and at - last_update > self._stale_after:
            minutes = int((at - last_update).total_seconds() // 60)
            return self._set(Health.SLOW, at, f"nothing new for {minutes} min")
        return self.report

    def failed(self, at: datetime, error: BaseException) -> HealthReport:
        state, detail = classify(error)
        return self._set(state, at, detail)

    def _set(self, state: Health, at: datetime, detail: str) -> HealthReport:
        if state is not self._state or detail != self._detail:
            self._state = state
            self._since = at
            self._detail = detail
        return self.report


_AUTH_WORDS = ("auth", "credential", "password", "login", "unauthor", "forbidden", "401", "403")
_OFFLINE_WORDS = (
    "connection",
    "timed out",
    "timeout",
    "unreachable",
    "resolve",
    "dns",
    "network",
    "ssl",
)


def classify(error: BaseException) -> tuple[Health, str]:
    """Map a failure onto a health state and a short, honest detail line.

    Matching on the text of an error is not elegant. It is, however, what a
    reverse-engineered client leaves available: its exceptions are mostly plain
    `Exception`, and the alternative is to call every failure "unknown", which
    tells the user nothing at all. When the client grows real exception types,
    this is the one function that has to change.
    """
    name = type(error).__name__.lower()
    text = f"{name} {error}".lower()

    if isinstance(error, TimeoutError) or any(word in text for word in _OFFLINE_WORDS):
        return Health.OFFLINE, "network unreachable"
    if any(word in text for word in _AUTH_WORDS):
        return Health.AUTH, "the account was rejected"
    if isinstance(error, KeyError | ValueError | TypeError | AttributeError | IndexError):
        return Health.SCHEMA, f"unexpected response ({type(error).__name__})"
    return Health.SCHEMA, f"{type(error).__name__}"
