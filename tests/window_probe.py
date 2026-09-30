"""Open the real window against a stand-in service and report what it did.

Run as a separate process by tests/test_webview.py (A7), because pywebview owns
the process's main thread. Prints one line of JSON:

    {"started": bool, "href": str, "listening": [...], "error": str}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any

result: dict[str, Any] = {"started": False, "href": "", "listening": [], "error": ""}


class StandIn:
    """Enough of a service for the page to draw a screen."""

    def status(self) -> dict[str, Any]:
        return {
            "health": "ok",
            "appliances": [],
            "recent": [],
            "command": [],
            "command_detail": None,
        }


def listening_sockets() -> list[dict[str, Any]]:
    """TCP sockets in the listening state owned by this process or its children."""
    pid = os.getpid()
    script = (
        f"$ids = @({pid}) + (Get-CimInstance Win32_Process | Where-Object ParentProcessId -eq {pid}"
        " | ForEach-Object ProcessId);"
        " @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue"
        " | Where-Object { $ids -contains $_.OwningProcess }"
        " | Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Compress"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not out:
        return []
    parsed = json.loads(out)
    return parsed if isinstance(parsed, list) else [parsed]


def main() -> None:
    try:
        import webview

        from pastie.app.memory import WindowMemory
        from pastie.app.presenter import Presenter
        from pastie.app.webview import Bridge, page_uri

        bridge = Bridge(StandIn(), Presenter(WindowMemory(None)))  # type: ignore[arg-type]
        window = webview.create_window(
            "probe", url=page_uri(), js_api=bridge, width=400, height=300
        )
        if window is None:
            raise RuntimeError("pywebview did not create a window")

        def inspect() -> None:
            try:
                time.sleep(4)
                result["started"] = True
                result["href"] = str(window.evaluate_js("document.location.href"))
                result["listening"] = listening_sockets()
            except Exception as error:  # noqa: BLE001 - reported, not raised
                result["error"] = repr(error)
            finally:
                window.destroy()

        threading.Thread(target=inspect, daemon=True).start()
        webview.start(http_server=False, private_mode=True)
    except Exception as error:  # noqa: BLE001 - reported, not raised
        result["error"] = repr(error)
    print(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
