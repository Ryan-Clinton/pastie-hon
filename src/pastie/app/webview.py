"""The window: a web page in a native Windows window, and the bridge it talks to.

docs/UI-SPEC.md section 5. The page (`app/web/`) draws the ScreenState the
presenter builds and does nothing clever; every decision and every word is made
in Python, where it is tested.

**The one trap** (UI-SPEC 5.3, found the hard way): pywebview quietly starts a
local web server for a page given as a path - even an absolute one, even with
`http_server=False`. That would be an unauthenticated network interface, which
SPEC 10 forbids. The page is therefore always given as an explicit `file:///`
URI, and `tests/test_webview.py` proves the window owns no listening socket.

The bridge is called from pywebview's worker threads, several at once, so
every call takes one lock: the presenter and its memory are not thread-safe,
and a status poll racing a Start must not interleave.
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pastie.app import voice
from pastie.app.client import ServiceClient, ServiceUnavailableError
from pastie.app.memory import WindowMemory
from pastie.app.presenter import Presenter
from pastie.messengers.base import OVERRIDES

log = logging.getLogger(__name__)

WEB = Path(__file__).with_name("web")
PAGE = WEB / "index.html"

#: Windows groups taskbar buttons by this. Without it the window counts as
#: pythonw.exe and the taskbar shows Python's icon.
APP_ID = "Pastie.Appliance.Companion"
ICON = Path(__file__).with_name("pastie.ico")

#: The six poses (UI-SPEC 6.2). Owner art at web/poses/<pose>.png replaces the
#: placeholder SVG of the same name, with no code change.
POSES = ("normal", "working", "waiting", "confirmed", "unknown", "fault")

#: Where WebView2 comes from, offered only when the window cannot start.
WEBVIEW2_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/"

#: The only places a link in the page may open, in the default browser.
_LINKS = ("https://github.com/Ryan-Clinton/pastie-hon",)


def page_uri() -> str:
    """The page as an explicit file:/// URI - never a path (see the module docs)."""
    return PAGE.resolve().as_uri()


class Bridge:
    """What the page may ask for. Everything else is out of its reach."""

    def __init__(self, client: ServiceClient, presenter: Presenter) -> None:
        self._client = client
        self._presenter = presenter
        self._lock = threading.Lock()
        self._status: dict[str, Any] | None = None
        #: Set by `run` once the native window exists; None in tests. Private on
        #: purpose: pywebview hands every *public* attribute of the bridge to the
        #: page, and would walk the whole native window object trying to.
        self._window: Any = None

    def _locked(self, work: Callable[[], Any]) -> Any:
        with self._lock:
            return work()

    # ------------------------------------------------------------- reading

    def screen(self) -> dict[str, Any]:
        """The main window. A service that is down is a screen, not an error."""

        def work() -> dict[str, Any]:
            try:
                self._status = self._client.status()
            except ServiceUnavailableError as error:
                log.debug("service unavailable: %s", error)
                self._status = None
            return self._presenter.screen(self._status)

        result: dict[str, Any] = self._locked(work)
        return result

    def history(self) -> dict[str, Any]:
        result: dict[str, Any] = self._locked(lambda: self._presenter.history(self._status))
        return result

    def poses(self) -> dict[str, str]:
        """Which image each pose uses: the owner's art if present, else the placeholder."""
        out = {}
        for pose in POSES:
            art = WEB / "poses" / f"{pose}.png"
            out[pose] = f"poses/{pose}.png" if art.exists() else f"poses/{pose}.svg"
        return out

    def guide(self) -> dict[str, Any]:
        result: dict[str, Any] = self._locked(lambda: self._presenter.guide(self._status))
        return result

    def guide_seen(self, key: str) -> None:
        self._locked(lambda: self._presenter.guide_seen(str(key)))

    def diagnostics(self) -> dict[str, Any]:
        result: dict[str, Any] = self._locked(lambda: self._presenter.diagnostics(self._status))
        return result

    def about(self) -> dict[str, Any]:
        result: dict[str, Any] = self._locked(self._presenter.about)
        return result

    def poke(self) -> str | None:
        result: str | None = self._locked(self._presenter.poke)
        return result

    def appearance(self) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            appearance = self._presenter.appearance
            return {
                "level": appearance.level,
                "theme": appearance.theme,
                "reduce_motion": appearance.reduce_motion,
                "examples": [
                    {"level": level, "title": title, "example": example}
                    for level, title, example in voice.LEVEL_EXAMPLES
                ],
            }

        result: dict[str, Any] = self._locked(work)
        return result

    # ------------------------------------------------------------- choosing

    def set_appearance(self, level: str, theme: str, reduce_motion: str) -> dict[str, Any]:
        self._locked(lambda: self._presenter.set_appearance(level, theme, reduce_motion))
        return self.appearance()

    def title_bar(self, dark: bool) -> None:
        """Match the native title bar to the page's theme (UI-SPEC 11, question 3)."""
        if self._window is not None:
            _dark_title_bar(self._window, bool(dark))

    def pin(self, appliance_id: str) -> None:
        self._locked(lambda: self._presenter.pin(str(appliance_id)))

    # ------------------------------------------------------------- commands

    def start(self, appliance: str, programme: str, options: dict[str, Any]) -> dict[str, Any]:
        extra = {
            key: str(value)
            for key, value in (options or {}).items()
            if key in ("dryLevel", "tempLevel", "dryTimeMM") and value not in (None, "")
        }
        return self._command(lambda: self._client.start(str(appliance), str(programme), **extra))

    def stop(self, appliance: str) -> dict[str, Any]:
        return self._command(lambda: self._client.stop(str(appliance)))

    def _command(self, send: Callable[[], list[str]]) -> dict[str, Any]:
        # Not under the lock: a start waits on Haier, and the status poll must
        # keep running meanwhile so the paper trail moves.
        try:
            return {"ok": True, "lines": send()}
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}

    # ------------------------------------------------------------- settings

    def settings(self) -> dict[str, Any]:
        try:
            values, messengers, account = self._client.settings()
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}
        return {
            "ok": True,
            "values": values,
            "account": account,
            "messengers": [
                {
                    "name": m.name,
                    "label": m.label,
                    "settings": m.settings,
                    "alerts": [{"kind": kind, "label": label} for kind, label in m.alerts],
                }
                for m in messengers
            ],
            "overrides_key": OVERRIDES,
        }

    def save_messenger(self, name: str, values: dict[str, Any]) -> dict[str, Any]:
        try:
            self._client.save_messenger(str(name), dict(values or {}))
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True}

    def test_messenger(self, name: str) -> dict[str, Any]:
        try:
            worked, detail = self._client.test_messenger(str(name))
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}
        aside = self._locked(lambda: self._presenter.messenger_aside(str(name))) if worked else None
        return {"ok": True, "worked": worked, "detail": detail, "aside": aside}

    def discover(self, name: str) -> dict[str, Any]:
        try:
            return {"ok": True, "targets": self._client.discover(str(name))}
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}

    def set_account(self, username: str, password: str) -> dict[str, Any]:
        username, password = str(username).strip(), str(password)
        if not username or not password:
            return {"ok": False, "error": "An email and a password are both needed."}
        try:
            restart = self._client.set_account(username, password)
        except ServiceUnavailableError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "restart_needed": restart}

    # ------------------------------------------------------------- links

    def open_link(self, url: str) -> bool:
        """Open a documentation link in the default browser. Nothing else."""
        url = str(url)
        if not any(url == base or url.startswith(base + "/") for base in _LINKS):
            return False
        webbrowser.open(url)
        return True


# =================================================================== window


def _claim_taskbar_identity() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        set_app_id = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id(APP_ID)
    except (AttributeError, OSError) as error:
        log.warning("could not set the taskbar identity: %s", error)


def _dark_title_bar(window: Any, dark: bool) -> None:
    """Ask Windows for a dark or light title bar (UI-SPEC 11, question 3). Cosmetic."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        hwnd = int(window.native.Handle.ToInt64())
        value = ctypes.c_int(1 if dark else 0)
        dwm = ctypes.WinDLL("dwmapi")
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on current builds, 19 on older ones.
        for attribute in (20, 19):
            if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4) == 0:
                break
    except Exception as error:  # noqa: BLE001 - a light title bar is not a failure
        log.debug("dark title bar unavailable: %s", error)


def _no_webview2(error: Exception) -> None:
    """Say what is missing in the plainest window Windows has (UI-SPEC 5.4)."""
    log.error("the window could not start: %s", error)
    message = (
        "The Pastie window needs Microsoft Edge WebView2, and it could not start.\n\n"
        "The background service is unaffected, and alerts still work.\n\n"
        "Open Microsoft's WebView2 download page now?"
    )
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        if messagebox.askyesno("Pastie", message, icon="error"):
            webbrowser.open(WEBVIEW2_DOWNLOAD)
        root.destroy()
    except Exception:  # noqa: BLE001 - last resort: the log has it
        print(message, file=sys.stderr)


def run(client: ServiceClient, memory: WindowMemory) -> None:
    """Open the window and block until it is closed."""
    import webview

    _claim_taskbar_identity()
    presenter = Presenter(memory)
    bridge = Bridge(client, presenter)
    window = webview.create_window(
        "Pastie",
        url=page_uri(),
        js_api=bridge,
        width=480,
        height=720,
        min_size=(420, 560),
        background_color="#0f1422",
        text_select=True,
    )
    bridge._window = window  # noqa: SLF001 - see Bridge.__init__
    try:
        webview.start(
            http_server=False,
            private_mode=True,
            icon=str(ICON) if ICON.exists() else None,
        )
    except Exception as error:  # noqa: BLE001 - WebView2 missing, or broken
        _no_webview2(error)
    finally:
        memory.save()
