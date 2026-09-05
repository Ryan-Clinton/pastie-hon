"""The rules messengers are held to, tested rather than trusted.

Isolation, the flash cap, the one-alert-at-a-time lock and the file server are
all things a contributor could accidentally undo, so each has a test that would
fail if they did.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import timedelta
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from pastie.core.events import Event, EventKind
from pastie.messengers.base import (
    Kind,
    MessengerRunner,
    Result,
    Setting,
    Target,
    redact,
    sample_event,
)
from pastie.messengers.cast import CastMessenger, SpeechCache, SpeechError
from pastie.messengers.fileserve import ServedFile
from pastie.messengers.flash import MAX_SECONDS, TargetLocks, plan
from pastie.messengers.hue import COLOURS, Bridge, HueError, HueMessenger, supports_colour
from pastie.messengers.webhook import WebhookMessenger


@pytest.fixture
def finished() -> Event:
    return sample_event("The tumble dryer has finished.")


# ------------------------------------------------------------- isolation


class Fine:
    name = "fine"
    label = "Fine"

    def __init__(self) -> None:
        self.fired = 0

    def settings(self) -> list[Setting]:
        return []

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:
        return []

    async def test(self, config: Mapping[str, Any]) -> Result:
        return Result.worked()

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        self.fired += 1
        return Result.worked("did the thing")


class Broken(Fine):
    name = "broken"

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        raise RuntimeError("the bridge is unplugged")


class Hangs(Fine):
    name = "hangs"

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        await asyncio.sleep(30)
        return Result.worked()


async def test_a_failing_messenger_does_not_stop_the_others(finished: Event) -> None:
    """A speaker that is switched off must not stop the light flashing."""
    fine, broken = Fine(), Broken()
    runner = MessengerRunner({"fine": fine, "broken": broken})

    delivered = await runner.deliver(
        finished, {"fine": {"enabled": True}, "broken": {"enabled": True}}
    )

    assert fine.fired == 1
    outcomes = {item.messenger: item.result.ok for item in delivered}
    assert outcomes == {"fine": True, "broken": False}


async def test_a_hanging_messenger_is_abandoned_not_waited_for(finished: Event) -> None:
    fine, hangs = Fine(), Hangs()
    runner = MessengerRunner({"fine": fine, "hangs": hangs}, timeout=0.05)

    delivered = await runner.deliver(
        finished, {"fine": {"enabled": True}, "hangs": {"enabled": True}}
    )

    assert fine.fired == 1
    hung = next(item for item in delivered if item.messenger == "hangs")
    assert not hung.result.ok
    assert "timed out" in hung.result.detail


async def test_messengers_that_are_off_are_skipped_silently(finished: Event) -> None:
    fine = Fine()
    runner = MessengerRunner({"fine": fine})
    assert await runner.deliver(finished, {"fine": {"enabled": False}}) == []
    assert fine.fired == 0


async def test_every_delivery_carries_the_event_id_for_the_receiver(finished: Event) -> None:
    """Pastie will not announce twice, but a crash can still fire a light twice."""
    runner = MessengerRunner({"fine": Fine()})
    delivered = await runner.deliver(finished, {"fine": {"enabled": True}})
    assert delivered[0].event_id == finished.id


# ------------------------------------------------------------------ flash


def test_the_flash_rate_is_capped_however_it_is_asked_for() -> None:
    """Flashing light can trigger seizures. This cap is not a preference."""
    pattern = plan(flashes=40, seconds=2)
    assert pattern.rate <= 1.0
    assert pattern.flashes <= 2


def test_the_flash_duration_is_capped_too() -> None:
    assert plan(flashes=1, seconds=600).seconds == MAX_SECONDS


def test_a_single_flash_is_still_allowed() -> None:
    assert plan(flashes=1, seconds=0).flashes == 1


async def test_one_alert_at_a_time_per_target() -> None:
    """Two events must not both snapshot a light and both restore it."""
    locks = TargetLocks()
    order = []

    async def alert(tag: str) -> None:
        async with locks.for_target("light-1"):
            order.append(f"{tag} in")
            await asyncio.sleep(0.01)
            order.append(f"{tag} out")

    await asyncio.gather(alert("a"), alert("b"))

    assert order in (
        ["a in", "a out", "b in", "b out"],
        ["b in", "b out", "a in", "a out"],
    )


def test_the_same_target_gets_the_same_lock() -> None:
    locks = TargetLocks()
    assert locks.for_target("x") is locks.for_target("x")
    assert locks.for_target("x") is not locks.for_target("y")


# ------------------------------------------------------------- file server


def fetch(url: str) -> bytes:
    """Read a URL and close the connection, so no socket outlives the test.

    An HTTPError *is* the response, and closing it is what frees the socket -
    letting it be collected later produces a ResourceWarning attributed to
    whichever unlucky test happens to be running at the time.
    """
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        error.close()
        raise


def test_the_file_is_served_only_at_its_unguessable_path() -> None:
    with ServedFile(b"audio", "audio/mp3", host="127.0.0.1") as url:
        assert fetch(url) == b"audio"

        root = url.rsplit("/", 1)[0] + "/"
        with pytest.raises(urllib.error.HTTPError) as raised:
            fetch(root)
        assert raised.value.code == 404


def test_the_path_is_long_enough_not_to_be_guessed() -> None:
    with ServedFile(b"audio", "audio/mp3", host="127.0.0.1") as url:
        assert len(url.rsplit("/", 1)[1]) >= 20


def test_the_server_is_gone_as_soon_as_the_announcement_is_over() -> None:
    served = ServedFile(b"audio", "audio/mp3", host="127.0.0.1")
    with served as url:
        pass
    with pytest.raises(urllib.error.URLError):
        fetch(url)


def test_an_expired_file_is_no_longer_served() -> None:
    expired = ServedFile(b"audio", "audio/mp3", host="127.0.0.1", ttl=timedelta(seconds=-1))
    with expired as url, pytest.raises(urllib.error.HTTPError) as raised:
        fetch(url)
    assert raised.value.code == 404


# ------------------------------------------------------------------- hue


class FakeBridge:
    """A bridge that records what it was told, so the rules can be checked."""

    def __init__(self, address: str, key: str, *, verify: bool = False, colour: bool = True):
        self.puts: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {
            "id": "light-1",
            "on": {"on": False},
            "dimming": {"brightness": 40.0},
        }
        if colour:
            self.state["color"] = {"xy": {"x": 0.4, "y": 0.4}}

    def lights(self) -> list[dict[str, Any]]:
        return [{**self.state, "metadata": {"name": "Kitchen"}}]

    #: Scripted responses, if a test needs the light to change under Pastie's feet.
    reads: list[dict[str, Any]] | None = None

    def light(self, light_id: str) -> dict[str, Any]:
        if self.reads:
            return self.reads.pop(0)
        return dict(self.state)

    def put(self, light_id: str, body: dict[str, Any]) -> None:
        self.puts.append(body)
        for key in ("on", "dimming", "color"):
            if key in body:
                self.state[key] = body[key]


def hue_with(bridge: FakeBridge) -> HueMessenger:
    return HueMessenger(bridge_factory=lambda *_a, **_k: bridge)


async def test_a_white_only_light_is_pulsed_rather_than_sent_a_colour() -> None:
    """Sending a colour to a dimmable-only bulb makes the call fail."""
    bridge = FakeBridge("bridge", "key", colour=False)
    result = await hue_with(bridge).react(
        sample_event(), {"light": "light-1", "seconds": 0, "colour": "Green"}
    )

    assert result.ok
    assert "color" not in bridge.puts[0]
    assert bridge.puts[0]["dimming"]["brightness"] == 100


async def test_a_colour_light_gets_the_colour_it_was_configured_with() -> None:
    bridge = FakeBridge("bridge", "key")
    await hue_with(bridge).react(
        sample_event(), {"light": "light-1", "seconds": 0, "colour": "Blue"}
    )

    x, y = COLOURS["Blue"]
    assert bridge.puts[0]["color"]["xy"] == {"x": x, "y": y}


def event_of(kind: EventKind) -> Event:
    return Event(
        kind=kind,
        appliance_id="dryer-1",
        at=sample_event().at,
        key=f"{kind.value}-1",
        message=kind.label,
    )


async def test_each_alert_can_have_its_own_colour() -> None:
    """So you can tell what happened from the next room, without going to look."""
    settings = {
        "enabled": True,
        "light": "light-1",
        "seconds": 0,
        "colour": "Green",
        "when": {
            "fault": {"colour": "Red"},
            "needs_emptying": {"colour": "Cyan"},
            "maintenance_due": {"colour": "Blue"},
        },
    }

    seen = {}
    for kind, expected in (
        (EventKind.CYCLE_FINISHED, "Green"),
        (EventKind.FAULT, "Red"),
        (EventKind.NEEDS_EMPTYING, "Cyan"),
        (EventKind.MAINTENANCE_DUE, "Blue"),
    ):
        bridge = FakeBridge("bridge", "key")
        runner = MessengerRunner({"hue": hue_with(bridge)})
        await runner.deliver(event_of(kind), {"hue": settings})
        seen[kind] = bridge.puts[0]["color"]["xy"]
        assert seen[kind] == dict(zip("xy", COLOURS[expected], strict=True))

    assert len(set(map(str, seen.values()))) == 4  # four alerts, four colours


async def test_an_alert_with_no_override_uses_the_usual_colour() -> None:
    bridge = FakeBridge("bridge", "key")
    runner = MessengerRunner({"hue": hue_with(bridge)})

    await runner.deliver(
        event_of(EventKind.CYCLE_FINISHED),
        {"hue": {"enabled": True, "light": "light-1", "seconds": 0, "colour": "Purple"}},
    )

    x, y = COLOURS["Purple"]
    assert bridge.puts[0]["color"]["xy"] == {"x": x, "y": y}


async def test_a_blank_override_means_no_opinion_not_an_empty_answer() -> None:
    """An empty box on the settings screen must not blank the real setting."""
    bridge = FakeBridge("bridge", "key")
    runner = MessengerRunner({"hue": hue_with(bridge)})

    await runner.deliver(
        event_of(EventKind.FAULT),
        {
            "hue": {
                "enabled": True,
                "light": "light-1",
                "seconds": 0,
                "colour": "Orange",
                "when": {"fault": {"colour": ""}},
            }
        },
    )

    x, y = COLOURS["Orange"]
    assert bridge.puts[0]["color"]["xy"] == {"x": x, "y": y}


def test_the_speaker_can_say_something_different_for_each_alert() -> None:
    """A full tank and a finished cycle deserve different sentences."""
    from pastie.messengers.base import for_event

    settings = {
        "text": "The tumble dryer has finished.",
        "when": {"needs_emptying": {"text": "The dryer has stopped - empty the water tank."}},
    }

    finished = for_event(settings, event_of(EventKind.CYCLE_FINISHED))
    tank = for_event(settings, event_of(EventKind.NEEDS_EMPTYING))

    assert finished["text"] == "The tumble dryer has finished."
    assert tank["text"] == "The dryer has stopped - empty the water tank."


def test_what_can_vary_per_alert_is_declared_by_the_messenger() -> None:
    """The settings screen draws these rows; it does not know what a light is."""
    per_event = {setting.key for setting in HueMessenger().settings() if setting.per_event}
    assert per_event == {"colour", "seconds"}


async def test_the_light_is_put_back_the_way_it_was_found() -> None:
    bridge = FakeBridge("bridge", "key")
    await hue_with(bridge).react(sample_event(), {"light": "light-1", "seconds": 0})

    assert bridge.puts[-1] == {
        "on": {"on": False},
        "dimming": {"brightness": 40.0},
        "color": {"xy": {"x": 0.4, "y": 0.4}},
    }


async def test_a_light_somebody_else_touched_is_left_alone() -> None:
    """Restoring blindly overrides the user, which is maddening.

    Somebody switches the light off mid-alert. Pastie must not switch it back on
    and leave it on the colour it had set.
    """
    bridge = FakeBridge("bridge", "key")
    # Second read - the one taken after the alert - shows a light nobody set:
    # off, at a brightness Pastie never asked for.
    bridge.reads = [
        dict(bridge.state),
        {"id": "light-1", "on": {"on": False}, "dimming": {"brightness": 100.0}},
    ]

    result = await hue_with(bridge).react(sample_event(), {"light": "light-1", "seconds": 0})

    assert result.ok
    assert "left alone" in result.detail
    assert len(bridge.puts) == 1  # the alert itself, and no restore


async def test_no_light_chosen_is_a_clear_failure_not_a_crash() -> None:
    result = await hue_with(FakeBridge("b", "k")).react(sample_event(), {})
    assert not result.ok
    assert result.detail == "no light chosen"


async def test_lights_are_listed_with_whether_they_do_colour() -> None:
    targets = await hue_with(FakeBridge("b", "k")).discover({})
    assert targets[0].label == "Kitchen"
    assert targets[0].detail == "colour"


def test_v2_states_colour_support_outright() -> None:
    assert supports_colour({"color": {"xy": {}}})
    assert not supports_colour({"dimming": {"brightness": 100}})


# -------------------------------------------------------------- webhook


async def test_a_webhook_carries_the_event_and_its_id() -> None:
    posted: list[tuple[str, dict[str, Any], str]] = []

    def fake_post(url: str, body: dict[str, Any], token: str) -> int:
        posted.append((url, body, token))
        return 204

    messenger = WebhookMessenger(post=fake_post)
    event = sample_event("The tumble dryer has finished.")
    result = await messenger.react(event, {"url": "https://example.invalid/hook", "token": "abc"})

    assert result.ok
    url, body, token = posted[0]
    assert url == "https://example.invalid/hook"
    assert body["id"] == event.id
    assert body["message"] == "The tumble dryer has finished."
    assert token == "abc"


async def test_a_webhook_without_a_url_says_so() -> None:
    result = await WebhookMessenger(post=lambda *_a: 200).react(sample_event(), {"enabled": True})
    assert not result.ok
    assert result.detail == "no URL set"


# ------------------------------------------------------------------ misc


def test_secrets_are_redacted_before_they_reach_a_log() -> None:
    assert redact("supersecretkey") == "supe**********"
    assert redact("") == "(unset)"
    assert redact("ab") == "**"


def test_every_messenger_describes_its_settings_for_the_screen_to_draw() -> None:
    for messenger in (HueMessenger(), WebhookMessenger()):
        settings = list(messenger.settings())
        assert settings, f"{messenger.name} describes nothing"
        assert all(isinstance(setting.kind, Kind) for setting in settings)
        assert settings[0].key == "enabled"


# ------------------------------------------------------- the bridge itself


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_a_rejected_key_is_reported_as_a_rejected_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """403 means the key, not the network. They need different answers."""

    def refuse(*_a: Any, **_k: Any) -> None:
        raise urllib.error.HTTPError("https://bridge", 403, "Forbidden", Message(), None)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(HueError, match="rejected the application key"):
        Bridge("192.168.1.2", "key").lights()


def test_a_bridge_that_is_not_there_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*_a: Any, **_k: Any) -> None:
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    with pytest.raises(HueError, match="could not reach the bridge"):
        Bridge("192.168.1.2", "key").lights()


def test_a_bridge_needs_both_an_address_and_a_key() -> None:
    with pytest.raises(HueError, match="both required"):
        Bridge("", "")


def test_the_key_goes_in_the_header_the_v2_api_wants(monkeypatch: pytest.MonkeyPatch) -> None:
    """A v1 username in this header is what makes the migration free."""
    seen: dict[str, Any] = {}

    def capture(request: Any, **_k: Any) -> FakeResponse:
        seen["url"] = request.full_url
        seen["headers"] = dict(request.headers)
        return FakeResponse({"data": [{"id": "light-1"}]})

    monkeypatch.setattr(urllib.request, "urlopen", capture)
    assert Bridge("192.168.1.2", "abc123").lights() == [{"id": "light-1"}]
    assert seen["url"] == "https://192.168.1.2/clip/v2/resource/light"
    assert seen["headers"]["Hue-application-key"] == "abc123"


# ---------------------------------------------------------------- webhook


async def test_a_webhook_reports_the_status_code_it_was_given() -> None:
    def refuse(*_a: Any) -> int:
        raise urllib.error.HTTPError("https://example.invalid", 500, "boom", Message(), None)

    result = await WebhookMessenger(post=refuse).react(
        sample_event(), {"url": "https://example.invalid/hook"}
    )
    assert not result.ok
    assert "500" in result.detail


async def test_a_webhook_has_nothing_to_discover() -> None:
    assert await WebhookMessenger().discover({}) == []


# -------------------------------------------------------------- speech


def test_speech_is_rendered_once_and_then_cached(tmp_path: Path) -> None:
    """The render is ~20 seconds and the message rarely changes."""
    renders: list[str] = []

    def render(text: str) -> bytes:
        renders.append(text)
        return b"audio for " + text.encode()

    cache = SpeechCache(tmp_path, renderer=render)
    assert not cache.cached("Dryer done.")
    assert cache.audio("Dryer done.") == b"audio for Dryer done."
    assert cache.audio("Dryer done.") == b"audio for Dryer done."

    assert renders == ["Dryer done."]
    assert cache.cached("Dryer done.")


def test_a_different_phrase_is_a_different_recording(tmp_path: Path) -> None:
    cache = SpeechCache(tmp_path, renderer=lambda text: text.encode())
    assert cache.audio("one") != cache.audio("two")


def test_speech_that_renders_to_nothing_is_an_error_not_silence(tmp_path: Path) -> None:
    cache = SpeechCache(tmp_path, renderer=lambda _text: b"")
    with pytest.raises(SpeechError):
        cache.audio("Dryer done.")


def test_warming_the_cache_never_raises(tmp_path: Path) -> None:
    """It runs while somebody types in a settings box; it must not interrupt them."""

    def broken(_text: str) -> bytes:
        raise RuntimeError("the speech service moved")

    messenger = CastMessenger(SpeechCache(tmp_path, renderer=broken))
    assert messenger.warm("Dryer done.") is False


def test_warming_the_cache_reports_success(tmp_path: Path) -> None:
    messenger = CastMessenger(SpeechCache(tmp_path, renderer=lambda text: text.encode()))
    assert messenger.warm("Dryer done.") is True


async def test_an_announcement_with_no_speaker_chosen_says_so(tmp_path: Path) -> None:
    messenger = CastMessenger(SpeechCache(tmp_path, renderer=lambda text: text.encode()))
    result = await messenger.react(sample_event(), {})
    assert not result.ok
    assert result.detail == "no speaker chosen"


async def test_a_speaker_that_cannot_be_reached_is_reported(tmp_path: Path) -> None:
    messenger = CastMessenger(
        SpeechCache(tmp_path, renderer=lambda text: text.encode()),
        connect=lambda _name, _address: None,
    )
    result = await messenger.react(sample_event(), {"device": "Kitchen speaker"})
    assert not result.ok
    assert "could not reach 'Kitchen speaker'" in result.detail


# ------------------------------------------------------------- registry


def test_the_registry_holds_every_messenger_this_build_knows_about(tmp_path: Path) -> None:
    from pastie.messengers import build_registry

    registry = build_registry(SpeechCache(tmp_path))

    assert {messenger.name for messenger in registry} == {"hue", "cast", "webhook"}
    assert registry.get("hue") is not None
    assert registry.get("nothing-like-this") is None
    assert len(registry) == 3
