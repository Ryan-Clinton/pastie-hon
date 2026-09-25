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


# ------------------------------------------------------------- contrast (UI-SPEC 10.2)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block))


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_body_text_meets_wcag_aa_in_both_themes(theme: str) -> None:
    css = (WEB / "app.css").read_text(encoding="utf-8")
    dark = _tokens(css[css.index(":root {") : css.index("}", css.index(":root {"))])
    light = {**dark, **_tokens(css[css.index(':root[data-theme="light"]') :].split("}", 1)[0])}
    t = dark if theme == "dark" else light
    pairs = [
        ("text", "bg"),
        ("text", "card"),
        ("text", "card-hi"),
        ("muted", "bg"),
        ("muted", "card"),
        ("gold", "bg"),
        ("gold", "card"),
        ("red", "card"),
        ("ink", "cream"),
        ("ink-soft", "cream"),
    ]
    for fg, bg in pairs:
        ratio = _contrast(t[fg], t[bg])
        assert ratio >= 4.5, f"{theme}: {fg} on {bg} is {ratio:.2f}:1"


# ------------------------------------------------------------- first run (UI-SCREENS 8)


class NoAccount(FakeClient):
    def settings(self) -> tuple[dict[str, Any], list[MessengerDescription], bool]:
        values, messengers, _ = super().settings()
        return values, messengers, False


def test_the_first_run_is_offered_only_without_an_account() -> None:
    assert not bridge().onboarding()["needed"]
    first = Bridge(NoAccount(), Presenter(WindowMemory(None))).onboarding()  # type: ignore[arg-type]
    assert first["needed"]
    assert first["asides"]["messengers"]


def test_the_first_run_is_plain_at_plain_and_never_jokes_about_the_account() -> None:
    presenter = Presenter(WindowMemory(None))
    presenter.set_appearance("plain", "system", "system")
    first = Bridge(NoAccount(), presenter).onboarding()  # type: ignore[arg-type]
    assert first["asides"] == {"appliances": None, "messengers": None, "tested": None}
    assert "account" not in Presenter(WindowMemory(None)).onboarding()


def test_a_service_that_is_down_does_not_start_the_first_run() -> None:
    class Down(FakeClient):
        def settings(self) -> Any:
            raise ServiceUnavailableError("down")

    assert not Bridge(Down(), Presenter(WindowMemory(None))).onboarding()["needed"]  # type: ignore[arg-type]


def test_primary_buttons_are_readable_in_both_themes() -> None:
    css = (WEB / "app.css").read_text(encoding="utf-8")
    dark = _tokens(css[css.index(":root {") : css.index("}", css.index(":root {"))])
    light = {**dark, **_tokens(css[css.index(':root[data-theme="light"]') :].split("}", 1)[0])}
    assert _contrast("#1a1206", dark["gold"]) >= 4.5  # dark text on the dark theme's gold
    assert ':root[data-theme="light"] .btn:not(.secondary):not(.danger) { color: #ffffff; }' in css
    assert _contrast("#ffffff", light["gold"]) >= 4.5  # white text on the light theme's gold
