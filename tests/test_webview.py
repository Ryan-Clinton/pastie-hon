"""The window: the bridge the page talks to, and the page itself (UI-SPEC 5, A7, A8)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pastie.app.client import MessengerDescription, ServiceUnavailableError
from pastie.app.memory import WindowMemory
from pastie.app.presenter import Presenter
from pastie.app.webview import POSES, WEB, Bridge, page_uri


class FakeClient:
    def __init__(self, status: dict[str, Any] | None = None, *, down: bool = False) -> None:
        self._status = status or {
            "health": "ok",
            "appliances": [],
            "recent": [],
            "command": [],
            "command_detail": None,
        }
        self.down = down
        self.started: list[tuple[str, str, dict[str, Any]]] = []
        self.saved: list[tuple[str, dict[str, Any]]] = []

    def status(self) -> dict[str, Any]:
        if self.down:
            raise ServiceUnavailableError("the service is not running")
        return self._status

    def start(self, appliance: str, programme: str, **extra: Any) -> list[str]:
        self.started.append((appliance, programme, extra))
        return ["Start requested"]

    def stop(self, appliance: str) -> list[str]:
        return ["Stop requested"]

    def settings(self) -> tuple[dict[str, Any], list[MessengerDescription], bool]:
        hue = MessengerDescription(
            name="hue",
            label="Philips Hue",
            settings=[{"key": "enabled", "label": "Flash a light", "kind": "bool"}],
            alerts=[("cycle_finished", "Finished")],
        )
        return {"hue": {"enabled": True}}, [hue], True

    def save_messenger(self, name: str, values: dict[str, Any]) -> None:
        self.saved.append((name, values))

    def test_messenger(self, name: str) -> tuple[bool, str]:
        return True, "Sent."

    def discover(self, name: str) -> list[dict[str, Any]]:
        return [{"id": "uuid-b", "label": "Living room light", "detail": "colour"}]

    def set_account(self, username: str, password: str) -> bool:
        return False


def bridge(client: FakeClient | None = None, level: str = "dry") -> Bridge:
    presenter = Presenter(WindowMemory(None))
    presenter.set_appearance(level, "system", "system")
    return Bridge(client or FakeClient(), presenter)  # type: ignore[arg-type]


# ------------------------------------------------------------- the bridge


def test_a_service_that_is_down_is_a_screen_not_an_error() -> None:
    screen = bridge(FakeClient(down=True)).screen()
    assert screen["header"]["health"] == "down"
    assert screen["connecting"]["stage"] == "service"


def test_the_page_can_reach_methods_only() -> None:
    """pywebview hands every public attribute to the page, so there must be none."""
    b = bridge()
    public = [name for name in dir(b) if not name.startswith("_")]
    assert public
    assert all(callable(getattr(b, name)) for name in public)


def test_a_start_passes_on_only_the_settings_the_service_knows() -> None:
    client = FakeClient()
    bridge(client).start(
        "dryer-1", "hqd_duvet", {"dryTimeMM": "90", "evil": "rm -rf", "tempLevel": ""}
    )
    assert client.started == [("dryer-1", "hqd_duvet", {"dryTimeMM": "90"})]


def test_links_open_only_for_the_project() -> None:
    b = bridge()
    assert not b.open_link("https://example.com/")
    assert not b.open_link("file:///C:/Windows/System32/calc.exe")
    assert not b.open_link("https://github.com/Ryan-Clinton/pastie-hon.evil.com/")


def test_settings_come_through_in_a_shape_the_page_can_draw() -> None:
    settings = bridge().settings()
    assert settings["ok"]
    assert settings["messengers"][0]["alerts"] == [{"kind": "cycle_finished", "label": "Finished"}]
    assert settings["overrides_key"]


def test_an_account_needs_both_halves() -> None:
    assert not bridge().set_account("", "secret")["ok"]
    assert not bridge().set_account("me@example.com", "")["ok"]


def test_appearance_offers_an_example_for_every_level() -> None:
    examples = bridge().appearance()["examples"]
    assert [e["level"] for e in examples] == ["plain", "dry", "departmental"]


def test_every_pose_has_an_image() -> None:
    poses = bridge().poses()
    assert set(poses) == set(POSES)
    for path in poses.values():
        assert (WEB / path).is_file()


def test_a_messenger_test_carries_its_aside_only_above_plain() -> None:
    assert bridge(level="plain").test_messenger("hue")["aside"] is None
    assert bridge(level="dry").test_messenger("hue")["aside"]


# ------------------------------------------------------------- the page


def test_the_page_is_a_file_uri_never_a_path() -> None:
    assert page_uri().startswith("file:///")


def test_the_page_forbids_the_network() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    policy = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)
    assert policy, "the page has no Content-Security-Policy"
    assert "connect-src 'none'" in policy.group(1)
    assert "object-src 'none'" in policy.group(1)


def test_the_bundle_contains_no_web_address() -> None:
    """A8: nothing in the page may load from, or link to, the network."""
    for path in WEB.rglob("*"):
        if path.suffix in (".html", ".css", ".js", ".svg"):
            text = path.read_text(encoding="utf-8")
            found = re.findall(r"https?://(?!www\.w3\.org/2000/svg)[^\s\"')]+", text)
            assert not found, f"{path.name}: {found}"


# ------------------------------------------------------------- the real window


@pytest.mark.skipif(sys.platform != "win32", reason="the window is Windows-only")
def test_the_window_opens_no_listening_socket() -> None:
    """A7: the one trap in pywebview (UI-SPEC 5.3), checked on a real window."""
    probe = Path(__file__).with_name("window_probe.py")
    done = subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True, timeout=120, check=False
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    assert lines, f"the probe printed nothing: {done.stderr[-2000:]}"
    report = json.loads(lines[-1])
    if not report["started"]:
        pytest.skip(f"WebView2 could not start here: {report['error']}")
    assert report["listening"] == [], f"the window is listening: {report['listening']}"
    assert report["href"].startswith("file:///")
