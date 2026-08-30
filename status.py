#!/usr/bin/env python3
r"""
status.py - print the live state of the Haier dryer.

Same credential handling as discover.py (env vars or .credentials).

Usage:  .venv\Scripts\python.exe status.py
"""
import asyncio
import sys

from pyhon import Hon

from discover import load_credentials

# the attributes actually worth looking at on a tumble dryer
INTERESTING = [
    ("machMode",             "machine mode"),
    ("prPhase",              "phase"),
    ("programName",          "programme"),
    ("remainingTimeMM",      "remaining (min)"),
    ("delayTime",            "delay start (min)"),
    ("remainingStandbyTime", "standby remaining"),
    ("doorStatus",           "door"),
    ("dryLevel",             "dry level"),
    ("tempLevel",            "temperature level"),
    ("texture",              "fabric"),
    ("antiCreaseTime",       "anti-crease (min)"),
    ("onOffStatus",          "on/off"),
    ("pause",                "paused"),
    ("lockStatus",           "child lock"),
    ("buzzerDisabled",       "buzzer disabled"),
    ("remoteCtrValid",       "remote control allowed"),
    ("errors",               "errors"),
]

MACH_MODE = {
    "0": "idle / off", "1": "idle", "2": "running", "3": "paused",
    "4": "scheduled", "5": "finished", "6": "error", "7": "standby",
}


def val(attributes, key):
    """Attributes may be plain values or HonAttribute objects."""
    a = attributes.get(key)
    if a is None:
        return None
    return getattr(a, "value", a)


async def main():
    user, password, source = load_credentials()
    if not user:
        print("ERROR: no credentials (see discover.py header).")
        return 1

    hon = await Hon(user, password).create()
    try:
        if not hon.appliances:
            print("no appliances on this account")
            return 3

        for a in hon.appliances:
            print(f"{a.nick_name}   ({a.model_name})")
            print("-" * 52)

            params = a.attributes.get("parameters", {}) or {}

            for key, label in INTERESTING:
                v = val(params, key)
                if v is None:
                    v = a.attributes.get(key)
                if v is None:
                    continue
                if key == "machMode":
                    v = f"{v}  ({MACH_MODE.get(str(v), 'unknown')})"
                print(f"  {label:24} {v}")

            # top-level flags discover.py showed as plain values
            for key in ("programName", "active", "pause"):
                if key in a.attributes:
                    print(f"  {key:24} {a.attributes[key]}")

            print()
    finally:
        await hon.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
