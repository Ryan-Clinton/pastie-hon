"""The settings the service acts on.

One JSON document, with the messengers' own settings nested under their names -
so a new messenger needs no change here, and an old one's settings survive an
upgrade that does not know about it.

No password ever appears in this file. Those live in
`pastie.service.secrets`, encrypted, and a messenger's own secret - a Hue
application key, a webhook token - is written here only because it is a
capability on your own network rather than an account credential. Anything that
would let somebody into an account goes to the secret store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pastie.core.store import JsonFile

#: How often to ask, when nothing has been pushed. Pushed updates make this a
#: backstop rather than the main mechanism - but it is the backstop that catches
#: a silently dropped subscription, so it is not long.
DEFAULT_POLL_SECONDS = 120

#: How often to fetch statistics. They change once a cycle at most, and they are
#: a separate request, so there is no sense asking every time.
DEFAULT_STATISTICS_EVERY = 10


@dataclass
class Settings:
    """Everything the service reads, with defaults that work out of the box."""

    poll_seconds: int = DEFAULT_POLL_SECONDS
    statistics_every: int = DEFAULT_STATISTICS_EVERY
    #: Per-messenger settings, keyed by messenger name.
    messengers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def messenger(self, name: str) -> dict[str, Any]:
        return self.messengers.setdefault(name, {})

    def to_json(self) -> dict[str, Any]:
        return {
            "poll_seconds": self.poll_seconds,
            "statistics_every": self.statistics_every,
            "messengers": self.messengers,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Settings:
        messengers = data.get("messengers")
        return cls(
            poll_seconds=_positive(data.get("poll_seconds"), DEFAULT_POLL_SECONDS),
            statistics_every=_positive(data.get("statistics_every"), DEFAULT_STATISTICS_EVERY),
            messengers=dict(messengers) if isinstance(messengers, dict) else {},
        )


class SettingsStore:
    """Reads and writes the settings document.

    Read fresh rather than cached, so a change made in the app applies to the
    next alert instead of the next restart - the prototype did this and it is
    the behaviour people expect from a settings screen.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._file = JsonFile(path)

    def load(self) -> Settings:
        return Settings.from_json(self._file.load())

    def save(self, settings: Settings) -> None:
        self._file.save(settings.to_json())

    def update_messenger(self, name: str, values: dict[str, Any]) -> Settings:
        settings = self.load()
        settings.messenger(name).update(values)
        self.save(settings)
        return settings


def _positive(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback
