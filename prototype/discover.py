#!/usr/bin/env python3
r"""
discover.py - enumerate Haier hOn appliances and dump everything they expose.

Credentials are NEVER passed on the command line (that leaks them into process
listings and shell history). They come from, in order of preference:
  1. environment variables  HON_USER / HON_PASS
  2. a file named .credentials next to this script:
         user=you@example.com
         password=yourpassword

Usage:  .venv\Scripts\python.exe discover.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from pyhon import Hon

# When frozen by PyInstaller, __file__ points into the temp extraction
# directory, not where the .exe actually lives - so .credentials would
# never be found. Resolve from the executable instead.
if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    HERE = Path(__file__).resolve().parent
OUT = HERE / "dump"


def load_credentials():
    user = os.environ.get("HON_USER")
    password = os.environ.get("HON_PASS")
    if user and password:
        return user, password, "environment"

    cred = HERE / ".credentials"
    if cred.exists():
        data = {}
        for line in cred.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip().lower()] = v.strip()
        if data.get("user") and data.get("password"):
            return data["user"], data["password"], str(cred)

    return None, None, None


def jsonable(obj):
    """Best-effort conversion so we can dump whatever the library hands back."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {str(k): jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [jsonable(v) for v in obj]
        return repr(obj)


async def main():
    user, password, source = load_credentials()
    if not user:
        print("ERROR: no credentials found.\n")
        print("Create a file called .credentials in this folder containing:")
        print("    user=your-hon-email@example.com")
        print("    password=your-hon-password")
        print("\nor set HON_USER and HON_PASS as environment variables.")
        return 1

    print(f"credentials source : {source}")
    print(f"account            : {user}")
    print("connecting to hOn cloud...\n")

    try:
        hon = await Hon(user, password).create()
    except Exception as exc:                      # noqa: BLE001 - report anything
        print(f"LOGIN FAILED: {type(exc).__name__}: {exc}")
        print("\nIf this is an auth error, check the account works in the hOn phone app.")
        print("If it's a parsing/HTTP error, Haier's API has likely moved and pyhOn")
        print("(last released 2024) needs the newer client from mmalolepszy/hon-revived.")
        return 2

    try:
        appliances = list(hon.appliances)
        print(f"appliances found: {len(appliances)}\n")
        if not appliances:
            print("None. Is the dryer registered in the hOn app and on Wi-Fi?")
            return 3

        OUT.mkdir(exist_ok=True)

        for i, a in enumerate(appliances, 1):
            print("=" * 70)
            print(f"[{i}] {getattr(a, 'nick_name', '?')}")
            for field in ("appliance_type", "brand", "model_name", "model_id",
                          "appliance_model_id", "mac_address", "unique_id", "zone"):
                print(f"    {field:20} {getattr(a, field, '(n/a)')}")

            blob = {}
            for section in ("data", "attributes", "settings", "available_settings",
                            "commands", "command_parameters", "statistics",
                            "additional_data", "options", "info"):
                try:
                    blob[section] = jsonable(getattr(a, section, None))
                except Exception as exc:          # noqa: BLE001
                    blob[section] = f"<error reading: {exc!r}>"

            cmds = blob.get("commands")
            if isinstance(cmds, dict) and cmds:
                print(f"\n    commands ({len(cmds)}):")
                for name in sorted(cmds):
                    print(f"      - {name}")

            settings = blob.get("settings")
            if isinstance(settings, dict) and settings:
                print(f"\n    settings ({len(settings)}), first 25:")
                for name in sorted(settings)[:25]:
                    print(f"      - {name} = {settings[name]}")

            safe = "".join(c if c.isalnum() or c in "-_" else "_"
                           for c in str(getattr(a, "nick_name", f"appliance{i}")))
            path = OUT / f"{safe}.json"
            path.write_text(json.dumps(blob, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n    full dump -> {path}")

        print("\n" + "=" * 70)
        print(f"Done. JSON written to {OUT}")
    finally:
        await hon.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
