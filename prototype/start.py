#!/usr/bin/env python3
r"""
start.py - start a drying cycle on the Haier dryer.

Refuses to send anything unless the machine reports remoteCtrValid = 1, so it
can't try to start an appliance that hasn't been armed at the panel.

Usage:  .venv\Scripts\python.exe start.py
        .venv\Scripts\python.exe start.py --program iot_dry_cotton --dry 14
"""
import argparse
import asyncio
import sys

from pyhon import Hon

from discover import load_credentials


def attr(appliance, key):
    params = appliance.attributes.get("parameters", {}) or {}
    a = params.get(key)
    return getattr(a, "value", a) if a is not None else None


def try_set(appliance, key, value):
    """Set a startProgram setting if this machine exposes it."""
    full = f"startProgram.{key}"
    if full not in appliance.settings:
        print(f"    {key:<14} not exposed - skipped")
        return False
    try:
        appliance.settings[full].value = value
        print(f"    {key:<14} = {value}")
        return True
    except Exception as exc:                              # noqa: BLE001
        print(f"    {key:<14} REJECTED: {exc}")
        return False


async def main(args):
    user, password, _ = load_credentials()
    if not user:
        print("no credentials")
        return 1

    hon = await Hon(user, password).create()
    try:
        if not hon.appliances:
            print("no appliances found")
            return 3
        a = hon.appliances[0]

        await a.update()
        remote = attr(a, "remoteCtrValid")
        mode = attr(a, "machMode")
        door = attr(a, "doorStatus")
        print(f"{a.nick_name}")
        print(f"  remoteCtrValid = {remote}   machMode = {mode}   doorStatus = {door}")

        if str(remote) != "1":
            print("\nREFUSING TO START: remoteCtrValid is not 1.")
            print("Power the machine on and set the dial to the remote position.")
            return 4

        print(f"\n  setting up '{args.program}':")
        try_set(a, "program", args.program)
        try_set(a, "dryLevel", args.dry)
        try_set(a, "tempLevel", args.temp)
        try_set(a, "energyLabel", args.energy)

        print("\n  sending startProgram ...")
        ok = await a.commands["startProgram"].send()
        print(f"  result: {ok}")

        # confirm it actually took
        for i in range(4):
            await asyncio.sleep(12)
            await a.update()
            print(f"  +{(i + 1) * 12:>3}s  machMode={attr(a, 'machMode')} "
                  f"prPhase={attr(a, 'prPhase')} "
                  f"remaining={attr(a, 'remainingTimeMM')} "
                  f"programme={a.attributes.get('programName')}")
    finally:
        await hon.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--program", default="iot_dry_mixed")
    p.add_argument("--dry", type=int, default=13)
    p.add_argument("--temp", type=int, default=3)
    p.add_argument("--energy", type=int, default=5)
    sys.exit(asyncio.run(main(p.parse_args())))
