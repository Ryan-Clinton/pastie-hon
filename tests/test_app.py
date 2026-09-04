"""The app talking to the service, all the way through.

No window and no pipe: the client is pointed straight at the real `Dispatcher`
with the real handlers behind it, so what is tested is the actual conversation -
request line, dispatch, handler, reply line - rather than a mock of it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from pastie.app.client import ServiceClient, ServiceUnavailableError
from pastie.connector.profiles import TUMBLE_DRYER, Profile
from pastie.connector.reading import RawReading
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.tracker import Tracker
from pastie.messengers import MessengerRunner, Registry
from pastie.messengers.base import Kind, Result, Setting
from pastie.service import main as service_main
from pastie.service.config import SettingsStore
from pastie.service.protocol import Dispatcher
from pastie.service.secrets import SecretStore
from pastie.service.watcher import Watcher

FIXTURES = Path(__file__).parent / "fixtures"


class StubConnector:
    def __init__(self, script: list[RawReading]) -> None:
        self.script = list(script)

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def read(self, *, with_statistics: bool = True) -> list[RawReading]:
        return [self.script.pop(0)] if self.script else []

    def profile(self, appliance_id: str) -> Profile:
        return TUMBLE_DRYER

    def subscribe(self, callback: Any) -> None: ...

    async def send(self, appliance_id: str, command: str, arguments: dict[str, Any]) -> None: ...


class Lamp:
    """A messenger that describes two settings and remembers being fired."""

    name = "lamp"
    label = "A Lamp"

    def __init__(self) -> None:
        self.tested = 0

    def settings(self) -> list[Setting]:
        return [
            Setting("enabled", "Flash the lamp", Kind.BOOL, default=False),
            Setting("colour", "Colour", Kind.CHOICE, default="Green", choices=("Green", "Red")),
        ]

    async def discover(self, config: Any) -> list[Any]:
        return []

    async def test(self, config: Any) -> Result:
        self.tested += 1
        return Result.worked("the lamp flashed")

    async def react(self, event: Any, config: Any) -> Result:
        return Result.worked()


def readings() -> list[RawReading]:
    data = json.loads((FIXTURES / "dryer_cycle.json").read_text(encoding="utf-8"))
    return [RawReading.from_json(item) for item in data]


@pytest.fixture
def service(tmp_path: Path) -> service_main.Service:
    registry = Registry()
    registry.add(Lamp())
    settings = SettingsStore(tmp_path / "settings.json")
    built = service_main.Service(
        watcher=Watcher(
            connector=StubConnector(readings()),
            tracker=Tracker(MemoryStore(), Ledger()),
            messengers=MessengerRunner(registry.messengers),
            settings=settings,
        ),
        dispatcher=Dispatcher(),
        secrets=SecretStore(tmp_path / "account.json"),
        settings=settings,
    )
    service_main.register_handlers(built, registry)
    return built


@pytest.fixture
def client(service: service_main.Service) -> ServiceClient:
    """A client wired straight to the dispatcher, with no transport in between."""

    def transport(line: str) -> str:
        return asyncio.run(service.dispatcher.handle_line(line))

    return ServiceClient(transport)


def test_the_window_can_ask_what_the_appliance_is_doing(
    client: ServiceClient, service: service_main.Service
) -> None:
    asyncio.run(service.watcher.refresh())
    asyncio.run(service.watcher.refresh())

    status = client.status()

    assert status["appliances"][0]["state"] == "running"
    assert status["appliances"][0]["programme"] == "Mixed load"


def test_the_settings_screen_is_drawn_from_what_the_messenger_says_it_needs(
    client: ServiceClient,
) -> None:
    """The payoff: a new messenger needs no interface code at all."""
    _, messengers, _ = client.settings()

    lamp = next(item for item in messengers if item.name == "lamp")
    assert lamp.label == "A Lamp"
    assert [setting["key"] for setting in lamp.settings] == ["enabled", "colour"]
    assert lamp.settings[1]["choices"] == ["Green", "Red"]


def test_settings_saved_from_the_window_come_back_next_time(client: ServiceClient) -> None:
    client.save_messenger("lamp", {"enabled": True, "colour": "Red"})

    values, _, _ = client.settings()

    assert values["messengers"]["lamp"] == {"enabled": True, "colour": "Red"}


def test_the_test_button_fires_the_real_messenger(
    client: ServiceClient, service: service_main.Service
) -> None:
    ok, detail = client.test_messenger("lamp")

    assert ok
    assert detail == "the lamp flashed"


def test_a_password_goes_in_and_nothing_comes_back_out(
    client: ServiceClient, service: service_main.Service
) -> None:
    client.set_account("someone@example.com", "hunter2")

    values, _, has_account = client.settings()

    assert has_account
    assert "hunter2" not in json.dumps(values)
    with pytest.raises(ServiceUnavailableError):
        client._ask("account.get")


def test_an_incomplete_account_is_refused_with_a_sentence(client: ServiceClient) -> None:
    with pytest.raises(ServiceUnavailableError, match="email address and a password"):
        client.set_account("", "")


def test_starting_a_cycle_reports_the_steps_that_actually_happened(
    client: ServiceClient, service: service_main.Service
) -> None:
    asyncio.run(service.watcher.refresh())  # idle, and armed

    lines = client.start("a1b2c3d4e5f6", "iot_dry_mixed")

    assert lines[0].startswith("Start requested")
    assert lines[1].startswith("Accepted by Haier")
    assert not any("confirmed" in line.lower() for line in lines)  # not yet, and not claimed


def test_a_service_that_is_not_running_is_reported_as_a_sentence() -> None:
    def dead(_line: str) -> str:
        raise OSError("the pipe is not there")

    with pytest.raises(ServiceUnavailableError, match="pipe is not there"):
        ServiceClient(dead).status()


def test_a_reply_that_is_not_json_is_reported_rather_than_crashing() -> None:
    with pytest.raises(ServiceUnavailableError, match="nonsense"):
        ServiceClient(lambda _line: "<html>404</html>").status()


def test_the_command_line_parses_what_it_documents() -> None:
    from pastie.cli import build_parser

    parser = build_parser()
    for command in ("status", "login", "where", "service"):
        assert parser.parse_args([command]).command == command
    assert parser.parse_args(["test", "hue"]).messenger == "hue"
