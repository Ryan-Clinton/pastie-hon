"""The window builds and draws, without a service behind it.

Not a test of what it looks like - that is what eyes are for. It is a test that
the thing constructs, that a status reply reaches the widgets, and that the
generated settings screens can be built from a messenger description, because
all three break silently: a tkinter widget that fails to configure raises on the
window's own thread and the window simply stops updating.

Skipped where there is no display, which is most Linux CI runners.
"""

from __future__ import annotations

import tkinter
from typing import Any

import pytest

from pastie.app.client import ServiceClient
from pastie.service.protocol import Reply


def _has_display() -> bool:
    try:
        root = tkinter.Tk()
    except tkinter.TclError:
        return False
    root.destroy()
    return True


pytestmark = pytest.mark.skipif(not _has_display(), reason="no display available")

STATUS: dict[str, Any] = {
    "health": "ok",
    "health_message": "Working normally",
    "appliances": [
        {
            "id": "dryer-1",
            "name": "tumble dryer",
            "model": "HD90-A2959R-UK",
            "state": "running",
            "trust": "verified",
            "updated_at": "2026-09-04T20:05:00+00:00",
            "programme": "Mixed load",
            "remaining": "45 min",
            "progress": 0.5,
            "remote_allowed": True,
            "maintenance": [{"name": "a filter clean", "due": True}],
            "programmes": [{"id": "iot_dry_mixed", "label": "Mixed load"}],
            "dry_levels": [{"id": "13", "label": "Cupboard dry"}],
            "temperatures": [{"id": "3", "label": "Middle"}],
            "commands": ["startProgram", "stopProgram"],
        }
    ],
    "recent": [{"kind": "cycle_started", "at": "2026-09-04T20:05:00+00:00", "message": "Started."}],
    "command": [],
}

MESSENGERS: list[dict[str, Any]] = [
    {
        "name": "hue",
        "label": "Philips Hue",
        "settings": [
            {
                "key": "enabled",
                "label": "Flash a light",
                "kind": "bool",
                "default": False,
                "choices": [],
                "help": "",
            },
            {
                "key": "key",
                "label": "Application key",
                "kind": "secret",
                "default": None,
                "choices": [],
                "help": "Your existing key works",
            },
            {
                "key": "colour",
                "label": "Colour",
                "kind": "choice",
                "default": "Green",
                "choices": ["Green", "Red"],
                "help": "",
            },
        ],
    }
]


def fake_transport(line: str) -> str:
    """Answer whatever the window asks, without a service or a pipe."""
    if '"status"' in line:
        return Reply.worked(**STATUS).to_line()
    if '"settings.get"' in line:
        return Reply.worked(
            settings={"messengers": {}}, account=False, messengers=MESSENGERS
        ).to_line()
    return Reply.worked().to_line()


@pytest.fixture(scope="module")
def window() -> Any:
    """One window for the whole module.

    Deliberately not one per test: creating and destroying several Tk roots in a
    single process is unreliable - on Windows the third or fourth one fails to
    find its own Tcl library - and the tests here only call methods on it, so a
    shared window costs nothing.
    """
    from pastie.app.main import App

    app = App(ServiceClient(fake_transport))
    app.withdraw()  # built, but never actually shown to whoever is running the tests
    try:
        yield app
    finally:
        app.destroy()


def test_the_window_builds(window: Any) -> None:
    assert window.title() == "Pastie"


def test_a_status_reply_reaches_the_widgets(window: Any) -> None:
    window._show_status(STATUS)

    assert window.name_label.cget("text") == "Tumble dryer"
    assert window.state_label.cget("text") == "RUNNING"
    assert "Mixed load" in window.detail_label.cget("text")
    assert "45 min" in window.detail_label.cget("text")
    assert "a filter clean" in window.detail_label.cget("text")
    assert window.health_label.cget("text") == "Working normally"


def test_an_unverified_appliance_cannot_be_started_and_says_why(window: Any) -> None:
    unverified: dict[str, Any] = {
        **STATUS,
        "appliances": [{**STATUS["appliances"][0], "trust": "unverified", "commands": []}],
    }
    window._show_status(unverified)

    assert "unverified" in window.state_label.cget("text")
    assert str(window.start_button.cget("state")) == "disabled"
    assert "will not send it commands" in window.armed_label.cget("text")


def test_a_machine_that_is_not_armed_explains_the_dial(window: Any) -> None:
    not_armed: dict[str, Any] = {
        **STATUS,
        "appliances": [{**STATUS["appliances"][0], "remote_allowed": False}],
    }
    window._show_status(not_armed)

    assert str(window.start_button.cget("state")) == "disabled"
    assert "dial to the remote position" in window.armed_label.cget("text")


def test_settings_screens_are_generated_from_a_messenger_description(window: Any) -> None:
    """The payoff: no widget in this file knows what a Hue bridge is."""
    from pastie.app.client import MessengerDescription

    window._draw_messengers(
        [MessengerDescription(name="hue", label="Philips Hue", settings=MESSENGERS[0]["settings"])],
        {"hue": {"enabled": True, "colour": "Red"}},
    )

    fields = window._fields["hue"]
    assert set(fields) == {"enabled", "key", "colour"}
    assert fields["enabled"].get() is True
    assert fields["colour"].get() == "Red"


def test_a_service_that_is_not_running_is_shown_in_the_header(window: Any) -> None:
    from pastie.app.main import Answer

    window._apply(Answer("status", error="Pastie's background service is not running."))

    assert "not running" in window.health_label.cget("text")
