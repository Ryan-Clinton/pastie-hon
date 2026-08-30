#!/usr/bin/env python3
r"""
probe.py - read the dryer state twice: as-connected, then after an explicit
update(), to see whether pyhOn is handing back stale data.

Read-only. Sends no commands.
"""
import asyncio
import sys

from pyhon import Hon

from discover import load_credentials

WATCH = ["machMode", "remoteCtrValid", "doorStatus", "prPhase",
         "remainingTimeMM", "onOffStatus", "errors", "prCode"]


def snap(appliance):
    params = appliance.attributes.get("parameters", {}) or {}
    out = {}
    for k in WATCH:
        a = params.get(k)
        out[k] = getattr(a, "value", a) if a is not None else None
    out["programName"] = appliance.attributes.get("programName")
    return out


async def main():
    user, password, _ = load_credentials()
    if not user:
        print("no credentials")
        return 1

    hon = await Hon(user, password).create()
    try:
        for a in hon.appliances:
            before = snap(a)

            # force a refresh from the cloud
            try:
                await a.update()
                note = "update() ok"
            except Exception as exc:                       # noqa: BLE001
                note = f"update() failed: {type(exc).__name__}: {exc}"

            after = snap(a)

            print(f"{a.nick_name}   [{note}]")
            print(f"  {'field':<18} {'as-connected':<16} {'after update()':<16} changed")
            print("  " + "-" * 62)
            for k in list(before):
                b, c = before[k], after[k]
                flag = "  <-- CHANGED" if str(b) != str(c) else ""
                print(f"  {k:<18} {str(b):<16} {str(c):<16}{flag}")
    finally:
        await hon.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
