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

from pastie.app import personality, voice
from pastie.app.client import ServiceClient, ServiceUnavailableError
from pastie.app.memory import WindowMemory
from pastie.app.personality import Meter, PersonalityStore, Pool, Sheet
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

    # ------------------------------------------------------------- first run

    def onboarding(self) -> dict[str, Any]:
        """Whether the first-run steps are needed, and their supporting lines."""
        try:
            _, _, account = self._client.settings()
        except ServiceUnavailableError:
            return {"needed": False, "reason": "service"}
        asides = self._locked(self._presenter.onboarding)
        return {"needed": not account, "asides": asides}

    # ------------------------------------------------------------- personalities

    def personalities(self) -> dict[str, Any]:
        """The cast: every appliance type seen, the Household and Pastie (UI-SPEC 7.9)."""

        def work() -> dict[str, Any]:
            store = self._presenter.personalities
            cards = []
            seen: set[str] = set()
            for appliance in (self._status or {}).get("appliances") or []:
                key = personality.key_for(str(appliance.get("name") or ""))
                if key in seen:
                    continue
                seen.add(key)
                cards.append(
                    self._card(
                        key,
                        str(appliance.get("name") or key).capitalize(),
                        verified=appliance.get("trust") == "verified",
                    )
                )
            for key in store.members():
                if key not in seen and key not in (personality.HOUSEHOLD, personality.PASTIE):
                    cards.append(self._card(key, key.replace("-", " ").capitalize(), verified=True))
            cards.append(self._card(personality.HOUSEHOLD, "The Household", verified=True))
            cards.append(self._card(personality.PASTIE, "Pastie", verified=True))
            return {
                "cards": cards,
                "temperaments": list(voice.TEMPERAMENTS),
                "stances": list(voice.STANCES),
                "levels": list(personality.LEVELS),
                "curves": list(personality.CURVES),
                "states": list(PREVIEW_STATES),
            }

        result: dict[str, Any] = self._locked(work)
        return result

    def _card(self, key: str, title: str, *, verified: bool) -> dict[str, Any]:
        store = self._presenter.personalities
        sheet = store.sheet(key)
        pools = []
        for pool in personality._pools_for(key):  # noqa: SLF001 - same package
            changes = sheet.pools.get(pool) or Pool()
            pools.append(
                {
                    "pool": pool,
                    "label": POOL_LABELS.get(pool, pool),
                    "shipped": len(personality.shipped(pool)),
                    "yours": len(changes.added),
                    "disabled": len(changes.disabled),
                    "replace": changes.replace,
                }
            )
        return {
            "key": key,
            "title": title,
            "kind": key if key in (personality.HOUSEHOLD, personality.PASTIE) else "appliance",
            "customised": store.get(key) is not None,
            "verified": verified,
            "name": sheet.name,
            "temperament": sheet.temperament,
            "stance": sheet.stance,
            "level": sheet.level,
            "speech": sheet.speech,
            "meters": [{"label": m.label, "curve": m.curve} for m in sheet.meters],
            "pools": pools,
        }

    def personality_pool(self, key: str, pool: str) -> dict[str, Any]:
        sheet = self._presenter.personalities.sheet(str(key))
        changes = sheet.pools.get(str(pool)) or Pool()
        return {
            "label": POOL_LABELS.get(str(pool), str(pool)),
            "shipped": [
                {"text": line, "disabled": line in changes.disabled}
                for line in personality.shipped(str(pool))
            ],
            "added": list(changes.added),
            "replace": changes.replace,
        }

    def check_line(self, pool: str, text: str) -> dict[str, Any]:
        check = personality.check_line(str(pool), str(text))
        return {"ok": check.ok, "refused": check.refused, "warnings": check.warnings}

    def save_personality(self, key: str, data: dict[str, Any]) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            store = self._presenter.personalities
            sheet = store.sheet(str(key))
            name = str(data.get("name") or "").strip()
            sheet.name = name[:60] or personality.default_sheet(sheet.key).name
            if data.get("temperament") in voice.TEMPERAMENTS:
                sheet.temperament = str(data["temperament"])
            if data.get("stance") in voice.STANCES:
                sheet.stance = str(data["stance"])
            if data.get("level") in personality.LEVELS:
                sheet.level = str(data["level"])
            meters = []
            for item in data.get("meters") or []:
                label = str(item.get("label") or "").strip()[:40]
                if label and item.get("curve") in personality.CURVES:
                    meters.append(Meter(label, str(item["curve"])))
            sheet.meters = meters[:3]
            store.save(sheet)
            return self._card(sheet.key, str(data.get("title") or sheet.key), verified=True)

        result: dict[str, Any] = self._locked(work)
        return result

    def save_pool(
        self, key: str, pool: str, disabled: list[str], added: list[str], replace: bool
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            store = self._presenter.personalities
            sheet = store.sheet(str(key))
            if str(pool) not in personality._pools_for(sheet.key):  # noqa: SLF001
                return {"ok": False, "refused": [f"{pool} has no lines to edit"]}
            shipped = set(personality.shipped(str(pool)))
            refused = []
            kept = []
            for line in added or []:
                check = personality.check_line(str(pool), str(line))
                if check.ok:
                    kept.append(str(line).strip())
                else:
                    refused.append(f"{line!r}: {check.refused}")
            sheet.pools[str(pool)] = Pool(
                disabled=[str(x) for x in disabled or [] if str(x) in shipped],
                added=kept,
                replace=bool(replace),
            )
            store.save(sheet)
            return {"ok": True, "refused": refused}

        result: dict[str, Any] = self._locked(work)
        return result

    def reset_personality(self, key: str, pool: str | None = None) -> None:
        self._locked(lambda: self._presenter.personalities.reset(str(key), pool or None))

    def export_pack(self, key: str) -> dict[str, Any]:
        """Save one sheet as a TOML file the owner chooses, to share or keep."""
        import webview

        sheet = self._presenter.personalities.sheet(str(key))
        if self._window is None:
            return {"ok": False, "error": "There's no window to ask where to save it."}
        chosen = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=f"pastie-{sheet.key}.toml"
        )
        if not chosen:
            return {"ok": False, "cancelled": True}
        target = Path(chosen if isinstance(chosen, str) else chosen[0])
        target.write_text(personality.to_toml(sheet), encoding="utf-8")
        return {"ok": True, "path": str(target)}

    def import_pack(self, key: str) -> dict[str, Any]:
        """Load a shared sheet into this card, keeping what is valid."""
        import webview

        if self._window is None:
            return {"ok": False, "error": "There's no window to ask which file."}
        chosen = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Personality packs (*.toml)",)
        )
        if not chosen:
            return {"ok": False, "cancelled": True}
        text = Path(chosen[0]).read_text(encoding="utf-8")
        return self.import_text(str(key), text)

    def import_text(self, key: str, text: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            try:
                sheet, dropped = self._presenter.personalities.import_pack(str(text), str(key))
            except ValueError as error:
                return {"ok": False, "error": str(error)}
            return {"ok": True, "dropped": dropped, "name": sheet.name}

        result: dict[str, Any] = self._locked(work)
        return result

    def preview(self, key: str, state: str, level: str, data: dict[str, Any]) -> dict[str, Any]:
        """The hero as it would look with this sheet, before anything is saved."""

        def work() -> dict[str, Any]:
            store = self._presenter.personalities
            draft = PersonalityStore(None)
            for other in store.members():
                existing = store.get(other)
                if existing is not None:
                    draft.save(existing)
            sheet = store.sheet(str(key))
            trial = Sheet(
                key=sheet.key,
                name=str(data.get("name") or sheet.name),
                temperament=str(data.get("temperament") or sheet.temperament),
                stance=str(data.get("stance") or sheet.stance),
                level=str(level) if level in personality.LEVELS else sheet.level,
                meters=[
                    Meter(str(m.get("label")), str(m.get("curve")))
                    for m in data.get("meters") or []
                    if m.get("label") and m.get("curve") in personality.CURVES
                ][:3],
                pools=sheet.pools,
            )
            draft.save(trial)
            return _preview_hero(draft, trial, str(state))

        result: dict[str, Any] = self._locked(work)
        return result

    # ------------------------------------------------------------- links

    def open_link(self, url: str) -> bool:
        """Open a documentation link in the default browser. Nothing else."""
        url = str(url)
        if not any(url == base or url.startswith(base + "/") for base in _LINKS):
            return False
        webbrowser.open(url)
        return True


#: Human names for the editable pools, in the order the editor lists them.
POOL_LABELS = {
    "idle": "Idle",
    "armed": "Idle, and armed for remote start",
    "estimating": "Running, before an estimate settles",
    "running_early": "Early in a cycle",
    "running_middle": "Middle of a cycle",
    "running_late": "Late in a cycle",
    "paused": "Paused",
    "scheduled": "Scheduled",
    "finished": "Finished",
    "estimate_unsettled": "Remark: the estimate is still settling",
    "estimate_rose": "Remark: the estimate went up",
    "start_confirmed": "Remark: a start the machine confirmed",
    "remote_not_armed": "Remark: remote start needs a visit",
    "gap_recovered": "Remark: a cycle recovered after Pastie was away",
    "unknown_state": "Remark: a value with no verified meaning",
    "maintenance_due": "Remark: maintenance is due",
    "finished_aside": "Remark: finished",
    "dryer_offline": "Remark: not reporting (Dry)",
    "where_dryer_silent": "Remark: not reporting (Departmental)",
    "reconnect_quiet": "Remark: nothing happened while away",
    "messenger_ok": "Remark: a messenger test worked",
    "household": "The Household's own lines (join idle and finished)",
    "poked": "Pastie's signature lines (the three-click remark)",
}

#: Sample states the preview can render (UI-SCREENS 7.3).
PREVIEW_STATES = ("idle", "armed", "running", "estimating", "finished", "paused")


# =================================================================== window


def _preview_hero(store: PersonalityStore, sheet: Sheet, state: str) -> dict[str, Any]:
    """Render one sample state with a draft store, in a presenter of its own."""
    from datetime import UTC, datetime

    name = "tumble dryer"
    if sheet.key not in (personality.HOUSEHOLD, personality.PASTIE):
        name = sheet.key.replace("-", " ")
    now = datetime.now(UTC).isoformat()
    appliance: dict[str, Any] = {
        "id": "preview",
        "name": name,
        "model": "",
        "state": "idle",
        "trust": "verified",
        "updated_at": now,
        "programme": None,
        "remaining_minutes": None,
        "remaining_settled": False,
        "progress": None,
        "remote_allowed": state == "armed",
        "attention": None,
        "fault_code": None,
        "cycle_count": 1,
        "maintenance": [],
        "programmes": [],
        "commands": ["startProgram", "stopProgram"],
    }
    shapes: dict[str, dict[str, Any]] = {
        "running": {
            "state": "running",
            "programme": "Mixed load",
            "remaining_minutes": 47,
            "remaining_settled": True,
            "progress": 0.54,
        },
        "estimating": {
            "state": "running",
            "programme": "Mixed load",
            "remaining_minutes": 120,
            "remaining_settled": False,
            "progress": None,
        },
        "finished": {"state": "finished", "programme": "Mixed load", "progress": 1.0},
        "paused": {
            "state": "paused",
            "programme": "Mixed load",
            "progress": 0.4,
            "remaining_minutes": 60,
            "remaining_settled": True,
        },
    }
    appliance.update(shapes.get(state, {}))
    level = sheet.level if sheet.level != "follow" else "departmental"
    presenter = Presenter(WindowMemory(None), personalities=store)
    presenter.set_level(level)
    reply = {"health": "ok", "appliances": [appliance], "recent": [], "command": []}
    presenter.screen(reply)  # past the connecting stage
    screen = presenter.screen(reply)
    hero: dict[str, Any] = screen["hero"]
    if sheet.key == personality.PASTIE:
        hero["aside"] = presenter.poke() or hero["aside"]
    return hero


# The Windows-only bodies below sit *inside* the platform check rather than
# after an early return: mypy on the Linux CI leg treats code after
# `if sys.platform != "win32": return` as unreachable and fails the build.


def _claim_taskbar_identity() -> None:
    if sys.platform == "win32":
        import ctypes

        try:
            set_app_id = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
            set_app_id.argtypes = [ctypes.c_wchar_p]
            set_app_id(APP_ID)
        except (AttributeError, OSError) as error:
            log.warning("could not set the taskbar identity: %s", error)


def _dark_title_bar(window: Any, dark: bool) -> None:
    """Ask Windows for a dark or light title bar (UI-SPEC 11, question 3). Cosmetic."""
    if sys.platform == "win32":
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
        "The background watcher is unaffected, and alerts still work.\n\n"
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


def run(
    client: ServiceClient, memory: WindowMemory, personalities: PersonalityStore | None = None
) -> None:
    """Open the window and block until it is closed."""
    import webview

    _claim_taskbar_identity()
    presenter = Presenter(memory, personalities=personalities)
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
