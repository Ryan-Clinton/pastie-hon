"""The service: one connection, one brain, and a channel the app talks over.

The watcher is driven here with a stand-in connector, which is the only way to
test the parts that matter - a dropped connection, a command the machine
ignores, statistics being fetched on their own schedule - without an appliance
and an hour of waiting.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pastie.connector.profiles import TUMBLE_DRYER, Profile
from pastie.connector.reading import RawReading
from pastie.core.commands import CommandOutcome, start_programme, stop_programme
from pastie.core.events import EventKind
from pastie.core.health import Health
from pastie.core.ledger import Ledger
from pastie.core.memory import MemoryStore
from pastie.core.tracker import Tracker
from pastie.messengers.base import MessengerRunner
from pastie.service.config import Settings, SettingsStore
from pastie.service.protocol import Dispatcher, Reply, Request
from pastie.service.secrets import Credentials, SecretStore, SecretsUnavailableError
from pastie.service.watcher import Watcher

FIXTURES = Path(__file__).parent / "fixtures"


def readings() -> list[RawReading]:
    data = json.loads((FIXTURES / "dryer_cycle.json").read_text(encoding="utf-8"))
    return [RawReading.from_json(item) for item in data]


class FakeConnector:
    """A connector that hands out a scripted sequence of readings."""

    def __init__(self, script: list[RawReading], *, fail_connect: int = 0) -> None:
        self.script = list(script)
        self.connects = 0
        self.closes = 0
        self.sent: list[tuple[str, str, dict[str, Any]]] = []
        self.subscribed: Callable[[], None] | None = None
        self.statistics_asked: list[bool] = []
        self.fail_connect = fail_connect
        self.fail_read: Exception | None = None
        self.reject: Exception | None = None

    async def connect(self) -> None:
        self.connects += 1
        if self.connects <= self.fail_connect:
            raise TimeoutError("read timed out")

    async def close(self) -> None:
        self.closes += 1

    async def read(self, *, with_statistics: bool = True) -> list[RawReading]:
        self.statistics_asked.append(with_statistics)
        if self.fail_read is not None:
            raise self.fail_read
        if not self.script:
            return []
        return [self.script.pop(0)]

    def profile(self, appliance_id: str) -> Profile:
        return TUMBLE_DRYER

    def subscribe(self, callback: Callable[[], None]) -> None:
        self.subscribed = callback

    async def send(self, appliance_id: str, command: str, arguments: dict[str, Any]) -> None:
        if self.reject is not None:
            raise self.reject
        self.sent.append((appliance_id, command, arguments))


def build_watcher(connector: FakeConnector, **settings: Any) -> Watcher:
    store = SettingsStore()
    if settings:
        store.save(Settings(**settings))
    return Watcher(
        connector=connector,
        tracker=Tracker(MemoryStore(), Ledger()),
        messengers=MessengerRunner({}),
        settings=store,
    )


# ------------------------------------------------------------------ reading


async def test_a_recorded_cycle_is_watched_all_the_way_through() -> None:
    connector = FakeConnector(readings())
    watcher = build_watcher(connector)

    announced = []
    for _ in range(4):
        announced.extend(await watcher.refresh())

    assert [event.kind for event in announced] == [
        EventKind.CYCLE_STARTED,
        EventKind.CYCLE_FINISHED,
    ]
    assert watcher.health is Health.OK


async def test_statistics_are_fetched_on_their_own_schedule() -> None:
    """They change once a cycle at most, and they are a separate request."""
    connector = FakeConnector(readings())
    watcher = build_watcher(connector, statistics_every=3)

    for _ in range(4):
        await watcher.refresh()

    assert connector.statistics_asked == [True, False, False, True]


async def test_the_status_reply_says_what_the_machine_is_doing() -> None:
    connector = FakeConnector(readings())
    watcher = build_watcher(connector)
    await watcher.refresh()
    await watcher.refresh()

    status = watcher.status().to_json()

    assert status["health"] == "ok"
    appliance = status["appliances"][0]
    assert appliance["state"] == "running"
    assert appliance["programme"] == "Mixed load"
    assert appliance["remaining"] == "about 120 min (still estimating)"
    assert appliance["trust"] == "verified"


async def test_recent_announcements_are_kept_for_the_window() -> None:
    watcher = build_watcher(FakeConnector(readings()))
    for _ in range(4):
        await watcher.refresh()

    recent = watcher.status().recent
    assert recent[0]["message"] == "The tumble dryer has finished."


# --------------------------------------------------------------- failures


async def test_a_failure_is_classified_into_something_a_user_can_act_on() -> None:
    connector = FakeConnector(readings())
    connector.fail_read = PermissionError("401 Unauthorized")

    stop = asyncio.Event()
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        stop.set()

    watcher = Watcher(
        connector=connector,
        tracker=Tracker(MemoryStore(), Ledger()),
        messengers=MessengerRunner({}),
        settings=SettingsStore(),
        sleep=sleep,
    )
    await watcher.run(stop)

    assert watcher.health is Health.AUTH
    assert slept == [5]  # and it backs off rather than hammering


async def test_the_watcher_reconnects_after_a_failure() -> None:
    connector = FakeConnector(readings(), fail_connect=2)
    stop = asyncio.Event()
    attempts: list[float] = []

    async def sleep(seconds: float) -> None:
        attempts.append(seconds)
        if len(attempts) >= 2:
            stop.set()

    watcher = Watcher(
        connector=connector,
        tracker=Tracker(MemoryStore(), Ledger()),
        messengers=MessengerRunner({}),
        settings=SettingsStore(),
        sleep=sleep,
    )
    await watcher.run(stop)

    assert connector.connects == 2
    assert attempts == [5, 10]  # backing off, not hammering


async def test_a_cycle_that_finished_during_an_outage_is_reported_as_a_gap() -> None:
    """The MQTT session replays nothing, so the reconnect re-baselines."""
    recorded = readings()
    connector = FakeConnector([recorded[1]])  # running
    watcher = build_watcher(connector)
    assert [event.kind for event in await watcher.refresh()] == []

    # The connection drops, and the cycle finishes while nobody is watching.
    watcher.connection_dropped()  # what a reconnect does, without the network
    connector.script = [recorded[3]]  # finished, counter moved

    events = await watcher.refresh()

    assert [event.kind for event in events] == [EventKind.CYCLE_FINISHED_WHILE_AWAY]
    assert "while Pastie wasn't running" in events[0].message


# ---------------------------------------------------------------- commands


async def test_a_start_is_refused_when_the_machine_is_not_armed() -> None:
    recorded = readings()
    connector = FakeConnector([recorded[3]])  # finished, and so disarmed
    watcher = build_watcher(connector)
    await watcher.refresh()

    progress = await watcher.send(
        recorded[3].appliance_id, start_programme("Mixed"), "startProgram", {}
    )

    assert progress.outcome is CommandOutcome.REFUSED
    assert connector.sent == []  # nothing was sent to Haier at all


async def test_an_accepted_command_is_not_reported_as_done_until_the_machine_agrees() -> None:
    recorded = readings()
    connector = FakeConnector([recorded[0]])  # idle, armed
    watcher = build_watcher(connector)
    await watcher.refresh()

    progress = await watcher.send(
        recorded[0].appliance_id, start_programme("Mixed"), "startProgram", {"program": "Mixed"}
    )
    lifecycle = [progress.outcome]
    assert connector.sent[0][1] == "startProgram"

    connector.script = [recorded[1]]  # the machine starts running
    await watcher.refresh()
    lifecycle.append(progress.outcome)

    assert lifecycle == [CommandOutcome.ACCEPTED, CommandOutcome.CONFIRMED]


async def test_a_rejection_from_haier_is_passed_back_in_words() -> None:
    recorded = readings()
    connector = FakeConnector([recorded[1]])
    connector.reject = RuntimeError("Haier refused the stopProgram command")
    watcher = build_watcher(connector)
    await watcher.refresh()

    progress = await watcher.send(recorded[1].appliance_id, stop_programme(), "stopProgram", {})

    assert progress.outcome is CommandOutcome.REJECTED
    assert progress.reason is not None
    assert "refused" in progress.reason


# ---------------------------------------------------------------- protocol


async def test_an_unknown_request_is_refused_by_name() -> None:
    dispatcher = Dispatcher()
    reply = Reply.parse(await dispatcher.handle_line('{"action": "launch_missiles"}'))

    assert not reply.ok
    assert "launch_missiles" in reply.error


async def test_a_request_that_is_not_json_does_not_end_the_session() -> None:
    dispatcher = Dispatcher()
    reply = Reply.parse(await dispatcher.handle_line("not json at all"))
    assert not reply.ok


async def test_a_handler_that_throws_becomes_an_error_reply() -> None:
    dispatcher = Dispatcher()

    async def explode(_arguments: dict[str, Any]) -> Reply:
        raise RuntimeError("the bridge is on fire")

    dispatcher.on("boom", explode)
    reply = Reply.parse(await dispatcher.handle_line('{"action": "boom"}'))

    assert not reply.ok
    assert "on fire" in reply.error


async def test_a_request_and_its_reply_survive_the_round_trip() -> None:
    dispatcher = Dispatcher()

    async def echo(arguments: dict[str, Any]) -> Reply:
        return Reply.worked(**arguments)

    dispatcher.on("echo", echo)
    line = Request("echo", {"appliance": "dryer-1"}).to_line()
    reply = Reply.parse(await dispatcher.handle_line(line))

    assert reply.ok
    assert reply.data == {"appliance": "dryer-1"}


def test_the_channel_is_locked_down_to_named_accounts() -> None:
    """Created without this, Windows lets everyone - anonymous included - read it."""
    from pastie.service.channel import SECURITY_DESCRIPTOR

    assert SECURITY_DESCRIPTOR.startswith("D:P")  # protected: nothing inherited
    for account in ("SY", "BA", "IU"):  # system, administrators, the person here
        assert f";;;{account})" in SECURITY_DESCRIPTOR
    assert ";;;WD)" not in SECURITY_DESCRIPTOR  # never Everyone
    assert ";;;AN)" not in SECURITY_DESCRIPTOR  # never anonymous


# ----------------------------------------------------------------- secrets


def test_a_password_survives_being_saved_and_read_back(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "account.json")
    store.save(Credentials("someone@example.com", "hunter2"))

    loaded = store.load()

    assert loaded == Credentials("someone@example.com", "hunter2")


def test_the_password_is_not_readable_in_the_file(tmp_path: Path) -> None:
    path = tmp_path / "account.json"
    SecretStore(path).save(Credentials("someone@example.com", "hunter2"))

    assert "hunter2" not in path.read_text(encoding="utf-8")


def test_a_password_never_appears_in_a_repr() -> None:
    """A stack trace or a debug print must not leak it."""
    assert "hunter2" not in repr(Credentials("someone@example.com", "hunter2"))


def test_no_saved_account_is_not_an_error(tmp_path: Path) -> None:
    assert SecretStore(tmp_path / "nothing.json").load() is None


def test_an_unreadable_account_file_says_what_to_do(tmp_path: Path) -> None:
    path = tmp_path / "account.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(SecretsUnavailableError):
        SecretStore(path).load()


def test_forgetting_an_account_removes_the_file(tmp_path: Path) -> None:
    path = tmp_path / "account.json"
    store = SecretStore(path)
    store.save(Credentials("someone@example.com", "hunter2"))
    store.forget()

    assert not store.exists()


# ---------------------------------------------------------------- settings


def test_settings_come_back_with_working_defaults() -> None:
    settings = SettingsStore().load()
    assert settings.poll_seconds > 0
    assert settings.messengers == {}


def test_a_messenger_keeps_its_own_settings(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.update_messenger("hue", {"enabled": True, "light": "light-1"})
    store.update_messenger("webhook", {"enabled": False})

    reloaded = SettingsStore(tmp_path / "settings.json").load()

    assert reloaded.messenger("hue") == {"enabled": True, "light": "light-1"}
    assert reloaded.messenger("webhook") == {"enabled": False}


def test_nonsense_in_the_settings_file_falls_back_to_a_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"poll_seconds": "soon-ish"}), encoding="utf-8")

    assert SettingsStore(path).load().poll_seconds > 0


def test_settings_are_read_fresh_so_a_change_applies_to_the_next_alert(
    tmp_path: Path,
) -> None:
    """The prototype did this, and it is what people expect of a settings screen."""
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.save(Settings(poll_seconds=60))

    SettingsStore(path).save(Settings(poll_seconds=30))

    assert store.load().poll_seconds == 30


def test_a_snapshot_is_available_by_appliance() -> None:
    watcher = build_watcher(FakeConnector(readings()))
    assert watcher.snapshot("nothing-here") is None


def test_the_service_never_offers_a_way_to_read_a_password_back() -> None:
    """There is no 'account.get'. One goes in, and nothing returns one."""
    from pastie.service import main

    class FakeRegistry:
        def __iter__(self) -> Any:
            return iter(())

        def get(self, name: str) -> None:
            return None

    service = main.Service(
        watcher=build_watcher(FakeConnector([])),
        dispatcher=Dispatcher(),
        secrets=SecretStore(Path("unused")),
        settings=SettingsStore(),
    )
    main.register_handlers(service, FakeRegistry())

    assert "account.set" in service.dispatcher.actions
    assert not any(action.startswith("account.get") for action in service.dispatcher.actions)


# ---------------------------------------------------------------- migrating


def test_a_prototype_folder_is_brought_across(tmp_path: Path) -> None:
    """Nobody should have to find their Hue key a second time."""
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    (folder / ".credentials").write_text(
        "# the prototype's file\nuser=someone@example.com\npassword=hunter2\n"
        "hue_bridge=192.168.1.2\nhue_key=abc123\n",
        encoding="utf-8",
    )
    (folder / "hue_alert.json").write_text(
        json.dumps(
            {
                "light": 12,
                "colour": "Green",
                "seconds": 18,
                "speak_enabled": True,
                "speak_device": "Living Room speaker",
                "speak_text": "Tumble dryer finished.",
            }
        ),
        encoding="utf-8",
    )
    (folder / "cast_hosts.json").write_text(
        json.dumps({"Living Room speaker": "192.168.1.50"}), encoding="utf-8"
    )

    secrets = SecretStore(tmp_path / "account.json")
    settings = SettingsStore(tmp_path / "settings.json")

    def no_bridge(address: str, key: str, number: str) -> tuple[str, dict[str, str]]:
        raise OSError("no bridge in a test")

    result = migrate.apply(folder, secrets, settings, lookup=no_bridge)

    assert secrets.load() == Credentials("someone@example.com", "hunter2")
    saved = settings.load()
    assert saved.messenger("hue")["address"] == "192.168.1.2"
    assert saved.messenger("hue")["key"] == "abc123"
    assert saved.messenger("cast")["address"] == "192.168.1.50"
    assert saved.messenger("cast")["text"] == "Tumble dryer finished."
    # A v1 light number means nothing to v2. With no bridge to ask, it is left
    # empty rather than guessed at, and the user is told what to do.
    assert saved.messenger("hue")["light"] == ""
    assert any("did not answer" in note for note in result.notes)


def test_migrating_an_empty_folder_does_nothing_and_says_so(tmp_path: Path) -> None:
    from pastie.service import migrate

    result = migrate.apply(
        tmp_path, SecretStore(tmp_path / "account.json"), SettingsStore(tmp_path / "s.json")
    )
    assert not result.anything


def test_the_prototype_credentials_file_is_left_alone(tmp_path: Path) -> None:
    """Deleting somebody's credentials file for them is not our decision."""
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    original = "user=someone@example.com\npassword=hunter2\n"
    (folder / ".credentials").write_text(original, encoding="utf-8")

    migrate.apply(folder, SecretStore(tmp_path / "a.json"), SettingsStore(tmp_path / "s.json"))

    assert (folder / ".credentials").read_text(encoding="utf-8") == original


# ------------------------------------------------------------------- paths


def test_the_service_and_the_app_keep_their_files_apart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The service does not run as you, so its files cannot live in your profile."""
    from pastie.service import paths

    monkeypatch.delenv("PASTIE_DATA_DIR", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "machine"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))

    assert paths.service_dir() == tmp_path / "machine" / "Pastie"
    assert paths.app_dir() == tmp_path / "user" / "Pastie"
    assert paths.settings_file().parent == paths.service_dir()
    assert paths.memory_file().parent == paths.service_dir()
    assert paths.ledger_file().parent == paths.service_dir()


def test_one_environment_variable_moves_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Which is how the tests, and a portable copy on a memory stick, both work."""
    from pastie.service import paths

    monkeypatch.setenv("PASTIE_DATA_DIR", str(tmp_path / "anywhere"))

    assert paths.service_dir() == tmp_path / "anywhere"
    assert paths.app_dir() == tmp_path / "anywhere" / "user"
    assert paths.log_file() == tmp_path / "anywhere" / "pastie.log"


def test_hue_brightness_is_converted_from_the_v1_scale(tmp_path: Path) -> None:
    """v1 counts brightness to 254; v2 is a percentage. 254 is not 254%."""
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    (folder / ".credentials").write_text(
        "user=a@b.c\npassword=x\nhue_bridge=192.168.1.2\nhue_key=abc\n", encoding="utf-8"
    )
    (folder / "hue_alert.json").write_text(json.dumps({"brightness": 254}), encoding="utf-8")

    settings = SettingsStore(tmp_path / "settings.json")
    migrate.apply(folder, SecretStore(tmp_path / "a.json"), settings)

    assert settings.load().messenger("hue")["brightness"] == 100.0


def test_migrating_twice_does_not_dim_the_light_each_time(tmp_path: Path) -> None:
    """A value already on the v2 scale is left alone."""
    from pastie.service.migrate import _brightness_to_v2

    assert _brightness_to_v2(254) == 100.0
    assert _brightness_to_v2(127) == 50.0
    assert _brightness_to_v2(100) == 100.0
    assert _brightness_to_v2(40) == 40.0
    assert _brightness_to_v2(0) == 1.0  # v2 has no "off" brightness; off is `on`
    assert _brightness_to_v2("nonsense") == 100.0


def test_the_prototypes_hue_light_is_matched_to_its_v2_id(tmp_path: Path) -> None:
    """Both APIs know the light by name, so the upgrade needs no re-picking."""
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    (folder / ".credentials").write_text(
        "user=a@b.c\npassword=x\nhue_bridge=192.168.1.2\nhue_key=abc\n", encoding="utf-8"
    )
    (folder / "hue_alert.json").write_text(json.dumps({"light": 12}), encoding="utf-8")

    def lookup(address: str, key: str, number: str) -> tuple[str, dict[str, str]]:
        assert (address, key, number) == ("192.168.1.2", "abc", "12")
        return "Living room light", {
            "uuid-a": "Hall Ceiling back",
            "uuid-b": "Living room light",
        }

    settings = SettingsStore(tmp_path / "settings.json")
    result = migrate.apply(folder, SecretStore(tmp_path / "a.json"), settings, lookup=lookup)

    assert settings.load().messenger("hue")["light"] == "uuid-b"
    assert any("matched to 'Living room light'" in note for note in result.notes)


def test_a_light_that_has_since_been_renamed_is_reported_not_guessed(tmp_path: Path) -> None:
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    (folder / ".credentials").write_text(
        "user=a@b.c\npassword=x\nhue_bridge=192.168.1.2\nhue_key=abc\n", encoding="utf-8"
    )
    (folder / "hue_alert.json").write_text(json.dumps({"light": 12}), encoding="utf-8")

    def renamed(address: str, key: str, number: str) -> tuple[str, dict[str, str]]:
        return "Old name", {"uuid-a": "Something else entirely"}

    settings = SettingsStore(tmp_path / "settings.json")
    result = migrate.apply(folder, SecretStore(tmp_path / "a.json"), settings, lookup=renamed)

    assert settings.load().messenger("hue")["light"] == ""
    assert any("no light on the bridge has that name" in note for note in result.notes)


def test_an_unreachable_bridge_does_not_fail_the_migration(tmp_path: Path) -> None:
    """The migration is mostly about the password; a bridge on a shelf is not fatal."""
    from pastie.service import migrate

    folder = tmp_path / "prototype"
    folder.mkdir()
    (folder / ".credentials").write_text(
        "user=a@b.c\npassword=x\nhue_bridge=192.168.1.2\nhue_key=abc\n", encoding="utf-8"
    )
    (folder / "hue_alert.json").write_text(json.dumps({"light": 12}), encoding="utf-8")

    def unreachable(address: str, key: str, number: str) -> tuple[str, dict[str, str]]:
        raise OSError("no route to host")

    settings = SettingsStore(tmp_path / "settings.json")
    result = migrate.apply(folder, SecretStore(tmp_path / "a.json"), settings, lookup=unreachable)

    assert result.account == "a@b.c"  # the important half still happened
    assert settings.load().messenger("hue")["light"] == ""
    assert any("did not answer" in note for note in result.notes)
