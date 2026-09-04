#!/usr/bin/env python3
r"""
hue.py - shared Philips Hue helper for the dryer tools.

Bridge details come from .credentials (hue_bridge / hue_key). The alert
appearance lives in hue_alert.json so the GUI and the background notifier
agree on it, and edits take effect without restarting the notifier.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    HERE = Path(__file__).resolve().parent

CONFIG = HERE / "hue_alert.json"

# hue is 0-65535 around the colour wheel
COLOURS = {
    "Green": 25500, "Red": 0, "Orange": 5000, "Yellow": 12750,
    "Blue": 46920, "Purple": 50000, "Pink": 56100, "Cyan": 40000,
}

EFFECTS = {
    "Breathe (15s)": "lselect",
    "Single flash": "select",
    "Solid colour": "none",
}

DEFAULTS = {
    "light": 12,
    "colour": "Green",
    "brightness": 254,
    "effect": "lselect",
    "seconds": 18,
    "restore": True,
    # spoken announcement (see speak.py)
    "speak_enabled": False,
    "speak_device": "Living Room speaker",
    "speak_text": "Tumble dryer finished. Go empty it.",
    "speak_volume": None,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        if CONFIG.exists():
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except Exception:                                      # noqa: BLE001
        pass
    return cfg


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _creds():
    """Bridge IP and key out of .credentials."""
    data = {}
    cred = HERE / ".credentials"
    if cred.exists():
        for line in cred.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip().lower()] = v.strip()
    return data.get("hue_bridge"), data.get("hue_key")


class Bridge:
    def __init__(self):
        ip, key = _creds()
        if not ip or not key:
            raise RuntimeError("hue_bridge / hue_key missing from .credentials")
        self.base = f"http://{ip}/api/{key}"

    def _req(self, path, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def lights(self):
        """[(id, name, supports_colour, reachable)] sorted by id."""
        out = []
        for k, v in self._req("/lights").items():
            st = v.get("state", {})
            out.append((int(k), v.get("name", f"light {k}"),
                        "hue" in st, bool(st.get("reachable"))))
        return sorted(out)

    def state(self, light):
        return self._req(f"/lights/{light}").get("state", {})

    def set(self, light, **kw):
        return self._req(f"/lights/{light}/state", "PUT", kw)

    def alert(self, cfg=None, log=print):
        """Apply the configured alert, then put the light back as it was."""
        cfg = cfg or load_config()
        light = int(cfg.get("light", 12))
        before = self.state(light)

        restore = {"on": before.get("on", False)}
        for k in ("bri", "hue", "sat", "ct", "effect"):
            if k in before:
                restore[k] = before[k]
        if before.get("colormode") == "xy" and "xy" in before:
            restore["xy"] = before["xy"]
            restore.pop("hue", None)
            restore.pop("sat", None)

        payload = {"on": True, "bri": int(cfg.get("brightness", 254))}
        effect = cfg.get("effect", "lselect")
        if effect in ("lselect", "select"):
            payload["alert"] = effect
        # colour only if the bulb can do it - dimmable-only lights reject hue
        if "hue" in before:
            payload["hue"] = COLOURS.get(cfg.get("colour", "Green"), 25500)
            payload["sat"] = 254

        log(f"hue: alerting light {light} ({cfg.get('colour')}, {effect})")
        try:
            self.set(light, **payload)
            time.sleep(int(cfg.get("seconds", 18)))
        finally:
            if cfg.get("restore", True):
                self.set(light, **restore)
                log(f"hue: light {light} restored")
            else:
                log(f"hue: light {light} left as set (restore off)")
