#!/usr/bin/env python3
r"""
notify.py - watch the Haier dryer and flash a Hue light when a cycle finishes.

Polls the hOn cloud for machine state; when a running cycle ends it saves the
target Hue light's current state, breathes it green, then puts it back exactly
as it was. Hue is local (no cloud), so only the dryer half touches the internet.

Config comes from .credentials (same file as discover.py):
    user=            hOn account email
    password=        hOn account password
    hue_bridge=      bridge IP
    hue_key=         bridge API key
    hue_light=       light id to flash

Usage:  .venv\Scripts\python.exe notify.py
        .venv\Scripts\python.exe notify.py --test      flash once, don't poll
        .venv\Scripts\python.exe notify.py --interval 60
"""
import argparse
import asyncio
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from pyhon import Hon

from discover import load_credentials
from hue import Bridge, load_config
from speak import announce, prerender

HERE = Path(__file__).resolve().parent
LOG = HERE / "notify.log"

# machMode values, confirmed from Andre0512/hon const.py MACH_MODE:
#   0/1 ready  2 running(EXECUTION)  3 pause  4/5 scheduled
#   6 error    7 ready(END_MODE)     8 test   9 ending(STOP)
# Fire on entering END_MODE specifically. Triggering on "left running"
# would false-alert on pause (3), which is not the end of anything.
END_MODE = "7"
MACH_MODE = {
    "0": "ready", "1": "ready", "2": "running", "3": "pause",
    "4": "scheduled", "5": "scheduled", "6": "error",
    "7": "END (finished)", "8": "test", "9": "ending",
}
HUE_GREEN = 25500          # hue value, 0-65535
ALERT_SECONDS = 18         # lselect breathes for ~15s


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


async def poll_loop(hue, interval):
    user, password, _ = load_credentials()
    if not user:
        log("ERROR: no hOn credentials")
        return 1

    previous = None
    while True:
        try:
            hon = await Hon(user, password).create()
            try:
                for a in hon.appliances:
                    params = a.attributes.get("parameters", {}) or {}
                    raw = params.get("machMode")
                    mode = str(getattr(raw, "value", raw))
                    remaining = params.get("remainingTimeMM")
                    remaining = getattr(remaining, "value", remaining)
                    prog = a.attributes.get("programName", "?")

                    if mode != previous:
                        name = MACH_MODE.get(mode, "unknown")
                        log(f"machMode {previous} -> {mode} ({name})   "
                            f"programme={prog}  remaining={remaining}")
                        if mode == END_MODE and previous != END_MODE:
                            log("CYCLE FINISHED (END_MODE) - firing Hue alert")
                            hue.alert()
                        elif mode == "6":
                            log("MACHINE REPORTS ERROR - firing Hue alert")
                            hue.alert()
                        previous = mode
            finally:
                await hon.close()
        except Exception as exc:                       # noqa: BLE001
            log(f"poll error: {type(exc).__name__}: {exc}")

        await asyncio.sleep(interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=120, help="seconds between polls")
    ap.add_argument("--test", action="store_true", help="flash the light once and exit")
    args = ap.parse_args()

    try:
        hue = Bridge()
    except Exception as exc:                               # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    # Read fresh each time so edits in the GUI apply without a restart.
    class Alerter:
        def alert(self):
            cfg = load_config()
            # Fire the announcement on its own thread - the light breathes for
            # ~18s and there is no reason to wait for it before speaking.
            if cfg.get("speak_enabled"):
                threading.Thread(
                    target=announce,
                    args=(cfg.get("speak_text", "Tumble dryer finished."),
                          cfg.get("speak_device", "Living Room speaker")),
                    kwargs={"volume": cfg.get("speak_volume"), "log": log},
                    daemon=True).start()
            hue.alert(cfg, log=log)

    alerter = Alerter()

    if args.test:
        log("--test: firing alert once")
        alerter.alert()
        return 0

    cfg = load_config()
    log(f"watching dryer, polling every {args.interval}s, "
        f"alert = light {cfg['light']} / {cfg['colour']} / {cfg['effect']}")
    # Warm the TTS cache now so the real alert does not pay the ~20s render.
    if cfg.get("speak_enabled"):
        threading.Thread(target=prerender,
                         args=(cfg.get("speak_text", "Tumble dryer finished."),),
                         kwargs={"log": log}, daemon=True).start()
    try:
        return asyncio.run(poll_loop(alerter, args.interval))
    except KeyboardInterrupt:
        log("stopped")
        return 130


if __name__ == "__main__":
    sys.exit(main())
