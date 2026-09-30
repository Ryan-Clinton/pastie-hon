"""Take the README's screenshots of the real window.

    python scripts/screenshots.py            (Windows; writes assets/screenshots/)

It opens the actual window, with the actual presenter, bridge and service
handlers, but gives it a stand-in appliance built from the recorded dryer cycle
in tests/fixtures rather than a live hOn account. That keeps the pictures current
with the code and keeps anybody's bridge address, speaker names and account out
of them. The old screenshots had the bridge address painted out by hand, and
they fell out of date with the redesign.

Run it again whenever the window changes. It takes about fifteen seconds and
leaves the window on screen while it works; don't cover it.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import sys
import tempfile
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import ImageGrab  # noqa: E402

from pastie.app.client import ServiceClient  # noqa: E402
from pastie.app.memory import WindowMemory  # noqa: E402
from pastie.app.personality import PersonalityStore  # noqa: E402
from pastie.app.presenter import Presenter  # noqa: E402
from pastie.app.webview import ICON, Bridge, _claim_taskbar_identity, page_uri  # noqa: E402
from pastie.connector.profiles import TUMBLE_DRYER, Profile  # noqa: E402
from pastie.connector.reading import RawReading  # noqa: E402
from pastie.core.ledger import Ledger  # noqa: E402
from pastie.core.memory import MemoryStore  # noqa: E402
from pastie.core.tracker import Tracker  # noqa: E402
from pastie.messengers import MessengerRunner, SpeechCache, build_registry  # noqa: E402
from pastie.service import main as service_main  # noqa: E402
from pastie.service.config import SettingsStore  # noqa: E402
from pastie.service.protocol import Dispatcher  # noqa: E402
from pastie.service.secrets import Credentials, SecretStore  # noqa: E402
from pastie.service.watcher import Watcher  # noqa: E402

OUTPUT = ROOT / "assets" / "screenshots"
FIXTURE = ROOT / "tests" / "fixtures" / "dryer_cycle.json"

#: Which recorded reading to show: mid-cycle, estimate settled, counting down.
MID_CYCLE = 2


class RecordedDryer:
    """One recorded reading, stamped with the current time on every read."""

    def __init__(self, reading: RawReading) -> None:
        self.reading = reading

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def read(self, *, with_statistics: bool = True) -> list[RawReading]:  # noqa: ARG002
        return [replace(self.reading, observed_at=datetime.now(UTC))]

    def profile(self, appliance_id: str) -> Profile:  # noqa: ARG002
        return TUMBLE_DRYER

    def subscribe(self, callback: Any) -> None: ...

    async def send(self, appliance_id: str, command: str, arguments: dict[str, Any]) -> None: ...


def stand_in_service(folder: Path) -> ServiceClient:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reading = RawReading.from_json(data[MID_CYCLE])
    registry = build_registry(SpeechCache(folder / "speech"))
    settings = SettingsStore(folder / "settings.json")
    service = service_main.Service(
        watcher=Watcher(
            connector=RecordedDryer(reading),
            tracker=Tracker(MemoryStore(), Ledger()),
            messengers=MessengerRunner(registry.messengers),
            settings=settings,
        ),
        dispatcher=Dispatcher(),
        secrets=SecretStore(folder / "account.json"),
        settings=settings,
    )
    service_main.register_handlers(service, registry)
    # An account, so the window skips its first-run screen. Never used.
    service.secrets.save(Credentials("you@example.com", "not-a-real-password"))

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    asyncio.run_coroutine_threadsafe(service.watcher.refresh(), loop).result()

    def transport(line: str) -> str:
        return asyncio.run_coroutine_threadsafe(service.dispatcher.handle_line(line), loop).result()

    return ServiceClient(transport)


def grab(window: Any, name: str) -> None:
    """Capture exactly the window's frame, as Windows draws it."""
    hwnd = int(window.native.Handle.ToInt64())
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(1.2)
    rect = ctypes.wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS: the visible frame, without the invisible
    # resize border GetWindowRect includes.
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    image.save(OUTPUT / name, optimize=True)
    print(f"assets/screenshots/{name}: {image.width}x{image.height}")


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("the window is Windows-only")
    import ctypes.wintypes

    import webview

    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, not scaled ones
    _claim_taskbar_identity()  # Pastie's icon in the title bar, not Python's
    folder = Path(tempfile.mkdtemp(prefix="pastie-screens-"))
    memory = WindowMemory(folder / "window.json")
    memory.state.appearance.level = "departmental"
    memory.state.appearance.theme = "dark"
    presenter = Presenter(memory, personalities=PersonalityStore(folder / "personalities"))
    bridge = Bridge(stand_in_service(folder), presenter)
    window = webview.create_window(
        "Pastie",
        url=page_uri(),
        js_api=bridge,
        width=480,
        height=720,
        background_color="#0f1422",
    )
    bridge._window = window  # noqa: SLF001 - as webview.run does

    def shoot() -> None:
        time.sleep(4)  # the page loads and draws its first status
        grab(window, "appliance.png")
        window.evaluate_js("document.querySelector('.rail-btn[data-view=settings]').click()")
        time.sleep(2)
        # Past the account form, to what Pastie can poke.
        window.evaluate_js("document.getElementById('messenger-cards').scrollIntoView()")
        time.sleep(1)
        grab(window, "settings.png")
        window.destroy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    webview.start(shoot, http_server=False, private_mode=True, icon=str(ICON))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
