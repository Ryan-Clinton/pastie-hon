"""The window builds and draws, without a service behind it.

Not a test of what it looks like - that is what eyes are for. It is a test that
the thing constructs, that a status reply reaches the widgets, and that the
generated settings screens can be built from a messenger description, because
all three break silently: a tkinter widget that fails to configure raises on the
window's own thread and the window simply stops updating.

Skipped where there is no display, which is most Linux CI runners.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest

from pastie.app.client import ServiceClient
from pastie.service.protocol import Reply

# Not a plain import: tkinter is missing on plenty of Linux installations, and a
# missing module at the top of a test file is a collection error - which stops
# the whole suite rather than skipping one file of it. GitHub's runners happen
# to ship tkinter, so this only bites somebody who clones the repo.
tkinter = pytest.importorskip("tkinter", reason="tkinter is not installed")


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
            {
                "key": "light",
                "label": "Light",
                "kind": "target",
                "default": None,
                "choices": [],
                "help": "",
            },
        ],
    }
]

SAVED = {"messengers": {"hue": {"enabled": True, "colour": "Red", "light": "uuid-b"}}}

TARGETS = [
    {"id": "uuid-a", "label": "Hall Ceiling back", "detail": "white only", "available": True},
    {"id": "uuid-b", "label": "Living room light", "detail": "colour", "available": True},
]


def fake_transport(line: str) -> str:
    """Answer whatever the window asks, without a service or a pipe."""
    if '"status"' in line:
        return Reply.worked(**STATUS).to_line()
    if '"settings.get"' in line:
        return Reply.worked(settings=SAVED, account=True, messengers=MESSENGERS).to_line()
    if '"messenger.discover"' in line:
        return Reply.worked(targets=TARGETS).to_line()
    return Reply.worked().to_line()


def settle(window: Any, until: Callable[[], bool], seconds: float = 5.0) -> bool:
    """Pump the window until a worker's answer has been applied, or time runs out.

    The window does its asking on worker threads and applies the answers from a
    queue on a timer, so a test has to let that machinery actually turn.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        window.update()
        window._drain()
        if until():
            return True
        time.sleep(0.05)
    return False


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


def test_a_service_that_is_not_running_is_shown_in_the_header(window: Any) -> None:
    from pastie.app.main import Answer

    window._apply(Answer("status", error="Pastie's background service is not running."))

    assert "not running" in window.health_label.cget("text")


# ------------------------------------------------- the settings actually load


def test_the_window_asks_for_the_settings_and_draws_them(window: Any) -> None:
    """The regression: the drawing worked, and nothing ever called it.

    An earlier version tested `_draw_messengers` directly, so the Settings tab
    shipped empty - the code was right and unreachable. This asks the question
    a user asks: after the window opens, are my settings on the screen?
    """
    assert settle(window, lambda: bool(window._fields)), "settings never arrived"

    fields = window._fields["hue"]
    assert set(fields) == {"enabled", "key", "colour", "light"}
    assert fields["enabled"].get() is True  # and populated from what was saved
    assert fields["colour"].get() == "Red"


def test_a_saved_account_is_reported_without_showing_the_password(window: Any) -> None:
    assert settle(window, lambda: bool(window.account_note.cget("text")))
    assert window.account_note.cget("text") == "An account is saved."


def test_a_light_is_chosen_by_name_not_by_its_id(window: Any) -> None:
    """Nobody should have to know their light is 1ec425b7-2340-457f-91bc-...."""
    assert settle(window, lambda: bool(window._target_boxes.get("hue", None)))
    assert settle(
        window,
        lambda: "uuid-b" in getattr(window._target_boxes["hue"], "names", {}).values(),
    ), "the light list never arrived"

    picker = window._target_boxes["hue"]
    assert list(picker.names) == ["Hall Ceiling back  (white only)", "Living room light  (colour)"]
    # The saved id is shown as its name, not as the id.
    assert picker.box.get() == "Living room light  (colour)"
    assert picker.variable.get() == "uuid-b"


def test_choosing_a_different_light_stores_its_id(window: Any) -> None:
    assert settle(
        window,
        lambda: "uuid-a" in getattr(window._target_boxes.get("hue", None), "names", {}).values(),
    )

    picker = window._target_boxes["hue"]
    picker.box.set("Hall Ceiling back  (white only)")
    window._target_chosen("hue", None)

    assert picker.variable.get() == "uuid-a"


def test_the_settings_page_says_why_it_is_empty_when_the_service_is_down(
    window: Any,
) -> None:
    """A modal on startup would be infuriating; a line on the page is not."""
    from pastie.app.main import Answer

    window._apply(Answer("settings", error="Pastie's background service is not running."))

    texts = [
        child.cget("text")
        for child in window._messenger_cards.winfo_children()
        if child.winfo_class() == "Label"
    ]
    assert any("not running" in text for text in texts)
    assert any("Start the service" in text for text in texts)


def test_the_settings_are_asked_for_again_once_the_service_answers() -> None:
    """The window opens before the service has finished connecting.

    Settings are requested once at startup. If that request fails - which it
    does whenever the window wins the race, and connecting to Haier takes about
    fifteen seconds - nothing used to ask again, so the Settings tab said "the
    service is not running" for ever while the header said everything was fine.
    """
    from pastie.app.main import Answer, App

    answers: list[str] = []

    def transport(line: str) -> str:
        if '"settings.get"' in line:
            answers.append("settings")
            if len(answers) == 1:
                return Reply.failed("Pastie's background service is not running.").to_line()
            return Reply.worked(settings=SAVED, account=True, messengers=MESSENGERS).to_line()
        return Reply.worked(**STATUS).to_line()

    app = App(ServiceClient(transport))
    app.withdraw()
    try:
        # The first request failed, exactly as it does in the race.
        app._apply(Answer("settings", error="Pastie's background service is not running."))
        assert not app._fields

        # A status arriving proves the service is up - so ask again.
        assert settle(app, lambda: bool(app._fields), seconds=8), "the settings were never retried"
        assert "hue" in app._fields
    finally:
        app.destroy()
