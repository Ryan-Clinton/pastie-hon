#!/usr/bin/env python3
r"""
dryer_gui.py - Pastie Tumble Dryer control panel.

Live status plus a Start button for the Haier HD90. The hOn cloud is polled on a
background thread so the window never freezes waiting on the network.

Credentials come from .credentials, same as the other scripts.

Run:    .venv\Scripts\pythonw.exe dryer_gui.py
"""
import asyncio
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from pyhon import Hon

from discover import load_credentials
from hue import COLOURS, EFFECTS, Bridge, load_config, save_config
from speak import announce, is_cached, list_speakers, prerender

POLL_SECONDS = 10

# ---- palette: warm, crusty, pastie ---------------------------------------
BG       = "#13161b"
CARD     = "#1d2129"
CARD_HI  = "#272c36"
CRUST    = "#e0a03c"
TEXT     = "#eef1f6"
MUTED    = "#8994a5"
GREEN    = "#7fc96b"
BLUE     = "#6fb4d8"
AMBER    = "#e0a03c"
RED      = "#e2664f"
FIELD    = "#eef1f6"   # dropdown fill - light, for contrast
INK      = "#171a20"   # text on light fields

# All confirmed from Andre0512/hon const.py - see memory notes.
MACH_MODE = {
    "0": "Ready", "1": "Ready", "2": "Running", "3": "Paused",
    "4": "Scheduled", "5": "Scheduled", "6": "ERROR",
    "7": "Finished", "8": "Test", "9": "Stopping",
}
MODE_COLOUR = {
    "Running": GREEN, "Finished": BLUE, "ERROR": RED,
    "Paused": AMBER, "Scheduled": AMBER,
}
PR_PHASE = {
    "0": "Ready", "1": "Heating", "2": "Drying", "3": "Cooldown",
    "11": "Ready", "13": "Cooldown", "14": "Heating", "15": "Heating",
    "16": "Cooldown", "18": "Tumbling", "19": "Drying", "20": "Drying",
}
DRY_LEVEL = {12: "Iron dry", 13: "Cupboard dry", 14: "Ready to wear"}
TEMP_LEVEL = {1: "Cool", 2: "Low", 3: "Middle", 4: "High"}

PROGRAMS = [
    ("Mixed load", "iot_dry_mixed"),
    ("Cotton", "iot_dry_cotton"),
    ("Bed linen", "iot_dry_bed_linen"),
    ("Towels", "hqd_towel"),
    ("Synthetics", "iot_dry_synthetics"),
    ("Delicates", "iot_dry_delicates"),
    ("Wool", "hqd_wool"),
    ("Rapid 30", "iot_dry_rapid_30"),
    ("Rapid 59", "iot_dry_rapid_59"),
    ("Shirts", "iot_dry_shirts"),
    ("Duvet", "iot_dry_duvet"),
    ("Night dry", "hqd_night_dry"),
]


def asset(name):
    """Assets live next to the script, or in _MEIPASS when frozen."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def attr(appliance, key):
    params = appliance.attributes.get("parameters", {}) or {}
    a = params.get(key)
    return getattr(a, "value", a) if a is not None else None


class Worker(threading.Thread):
    """Owns the asyncio loop and the hOn session."""

    def __init__(self, out_q, cmd_q):
        super().__init__(daemon=True)
        self.out = out_q
        self.cmds = cmd_q

    def say(self, kind, payload):
        self.out.put((kind, payload))

    def run(self):
        asyncio.run(self.main())

    async def main(self):
        user, password, _ = load_credentials()
        if not user:
            self.say("log", "No credentials found in .credentials")
            self.say("state", None)
            return

        hon = None
        while True:
            try:
                if hon is None:
                    self.say("log", "connecting to hOn ...")
                    hon = await Hon(user, password).create()
                    self.say("log", "connected")
                    self.say("conn", "connected")

                a = hon.appliances[0]
                await a.update()
                self.say("state", {
                    "name": a.nick_name,
                    "model": a.model_name,
                    "machMode": str(attr(a, "machMode")),
                    "prPhase": str(attr(a, "prPhase")),
                    "remaining": attr(a, "remainingTimeMM"),
                    "total": attr(a, "dryTimeMM"),
                    "remote": str(attr(a, "remoteCtrValid")),
                    "door": str(attr(a, "doorStatus")),
                    "errors": str(attr(a, "errors")),
                    "programme": a.attributes.get("programName"),
                })

                try:
                    cmd = self.cmds.get_nowait()
                except queue.Empty:
                    cmd = None
                if cmd:
                    await self.do_start(a, cmd)

            except Exception as exc:                       # noqa: BLE001
                self.say("log", f"error: {type(exc).__name__}: {exc}")
                try:
                    if hon:
                        await hon.close()
                except Exception:                          # noqa: BLE001
                    pass
                hon = None

            await asyncio.sleep(POLL_SECONDS)

    async def do_start(self, a, cmd):
        if str(attr(a, "remoteCtrValid")) != "1":
            self.say("log", "REFUSED - remote control not armed at the machine")
            return
        self.say("log", f"starting {cmd['program']} "
                        f"(dry {cmd['dry']}, temp {cmd['temp']}) ...")
        for key, val in (("program", cmd["program"]),
                         ("dryLevel", cmd["dry"]),
                         ("tempLevel", cmd["temp"])):
            full = f"startProgram.{key}"
            if full in a.settings:
                try:
                    a.settings[full].value = val
                except Exception as exc:                   # noqa: BLE001
                    self.say("log", f"  {key} rejected: {exc}")
        try:
            ok = await a.commands["startProgram"].send()
            self.say("log", f"cloud accepted={ok} - watch the status to confirm")
        except Exception as exc:                           # noqa: BLE001
            self.say("log", f"start failed: {type(exc).__name__}: {exc}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pastie Tumble Dryer")
        self.configure(bg=BG)
        self.geometry("980x740")
        self.minsize(920, 700)
        try:
            self.iconbitmap(asset("pastie.ico"))
        except tk.TclError:
            pass

        self.out_q, self.cmd_q = queue.Queue(), queue.Queue()
        self.peak_remaining = 0

        self._style()
        self._header()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=7)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._status(left)
        self._speak_panel(left)
        self._controls(right)
        self._hue_panel(right)
        self._activity(left)

        Worker(self.out_q, self.cmd_q).start()
        self.after(300, self.drain)

    # ---- chrome -----------------------------------------------------------
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        # A readonly Combobox ignores configure() for its field colours - the
        # readonly state has to be targeted with map() or it renders muddy.
        st.configure("P.TCombobox", padding=7, borderwidth=0,
                     arrowsize=16, arrowcolor=BG)
        st.map("P.TCombobox",
               fieldbackground=[("readonly", FIELD), ("!disabled", FIELD)],
               background=[("readonly", CRUST), ("!disabled", CRUST)],
               foreground=[("readonly", INK), ("!disabled", INK)],
               selectbackground=[("readonly", FIELD)],
               selectforeground=[("readonly", INK)],
               arrowcolor=[("readonly", BG)])
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", CRUST)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.option_add("*TCombobox*Listbox.font", "{Segoe UI} 10")

    def _card(self, parent=None, expand=False, **kw):
        f = tk.Frame(parent or self, bg=CARD, **kw)
        f.pack(fill="both" if expand else "x", expand=expand, padx=7, pady=6)
        return f

    def _header(self):
        h = tk.Frame(self, bg=BG)
        h.pack(fill="x", padx=14, pady=(14, 2))

        self.pastie_img = None
        try:
            from PIL import Image, ImageTk
            im = Image.open(asset("pastie.jpg")).convert("RGB")
            w, hh = im.size
            side = min(w, hh)
            im = im.crop(((w - side) // 2, (hh - side) // 2,
                          (w - side) // 2 + side, (hh - side) // 2 + side))
            im = im.resize((78, 78), Image.LANCZOS)
            self.pastie_img = ImageTk.PhotoImage(im)
            tk.Label(h, image=self.pastie_img, bg=BG, bd=0).pack(side="left")
        except Exception:                                  # noqa: BLE001
            tk.Label(h, text="🥟", font=("Segoe UI Emoji", 34),
                     bg=BG, fg=CRUST).pack(side="left")

        t = tk.Frame(h, bg=BG)
        t.pack(side="left", padx=14)
        tk.Label(t, text="PASTIE", bg=BG, fg=CRUST,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(t, text="TUMBLE DRYER", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.sub = tk.Label(t, text="connecting...", bg=BG, fg=MUTED,
                            font=("Segoe UI", 9))
        self.sub.pack(anchor="w", pady=(2, 0))
        self._connected = False

    def _status(self, parent=None):
        c = self._card(parent)

        # status pill - small badge, colour carries the meaning
        pill_row = tk.Frame(c, bg=CARD)
        pill_row.pack(fill="x", padx=16, pady=(14, 0))
        self.pill = tk.Label(pill_row, text="  ...  ", bg=CARD_HI, fg=MUTED,
                             font=("Segoe UI", 10, "bold"), padx=12, pady=4)
        self.pill.pack(side="left")

        # HERO - time left, the thing you actually want to know
        hero = tk.Frame(c, bg=CARD)
        hero.pack(fill="x", padx=16, pady=(10, 0))
        self.hero = tk.Label(hero, text="--", bg=CARD, fg=CRUST,
                             font=("Segoe UI", 68, "bold"))
        self.hero.pack(side="left")
        cap = tk.Frame(hero, bg=CARD)
        cap.pack(side="left", padx=(12, 0), pady=(26, 0))
        self.hero_unit = tk.Label(cap, text="MINUTES", bg=CARD, fg=TEXT,
                                  font=("Segoe UI", 13, "bold"))
        self.hero_unit.pack(anchor="w")
        self.hero_cap = tk.Label(cap, text="pastie dryer time left", bg=CARD,
                                 fg=MUTED, font=("Segoe UI", 9))
        self.hero_cap.pack(anchor="w")

        self.bar_bg = tk.Frame(c, bg=CARD_HI, height=10)
        self.bar_bg.pack(fill="x", padx=16, pady=(14, 6))
        self.bar = tk.Frame(self.bar_bg, bg=CRUST, height=10, width=0)
        self.bar.place(x=0, y=0, relheight=1.0)

        self.phase = tk.Label(c, text="", bg=CARD, fg=MUTED,
                              font=("Segoe UI", 10))
        self.phase.pack(anchor="w", padx=16)

        grid = tk.Frame(c, bg=CARD)
        grid.pack(fill="x", padx=16, pady=(12, 16))
        self.rows = {}
        for key, label in (("programme", "Programme"), ("door", "Door"),
                           ("remote", "Remote"), ("errors", "Errors")):
            r = tk.Frame(grid, bg=CARD)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, width=12, anchor="w", bg=CARD, fg=MUTED,
                     font=("Segoe UI", 9)).pack(side="left")
            v = tk.Label(r, text="-", anchor="w", bg=CARD, fg=TEXT,
                         font=("Segoe UI", 10, "bold"))
            v.pack(side="left")
            self.rows[key] = v

    def _controls(self, parent=None):
        c = self._card(parent)
        tk.Label(c, text="START THE PASTIE DRYER", bg=CARD, fg=CRUST,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 6))

        self.prog = self._combo(c, "Programme", [p[0] for p in PROGRAMS], 0)
        self.dry = self._combo(c, "Dryness",
                               [f"{v}" for v in DRY_LEVEL.values()], 2)
        self.temp = self._combo(c, "Temperature",
                                [f"{v}" for v in TEMP_LEVEL.values()], 1)

        self.start_btn = tk.Button(
            c, text="START THE PASTIE DRYER", command=self.on_start, state="disabled",
            bg=CRUST, fg=BG, activebackground=TEXT, activeforeground=BG,
            font=("Segoe UI", 13, "bold"), bd=0, relief="flat",
            disabledforeground=MUTED, cursor="hand2", pady=9)
        self.start_btn.pack(fill="x", padx=16, pady=(10, 6))

        self.hint = tk.Label(c, text="", bg=CARD, fg=AMBER, wraplength=390,
                             justify="left", font=("Segoe UI", 9))
        self.hint.pack(anchor="w", padx=16, pady=(0, 12))

    def _combo(self, parent, label, values, default):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", padx=16, pady=3)
        tk.Label(r, text=label, width=12, anchor="w", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        cb = ttk.Combobox(r, values=values, state="readonly", width=24,
                          style="P.TCombobox",
                          font=("Segoe UI", 10, "bold"))
        cb.current(default)
        cb.pack(side="left", fill="x", expand=True)
        return cb

    def _hue_panel(self, parent=None):
        c = self._card(parent)
        tk.Label(c, text="PASTIE ALERT (PHILIPS HUE)", bg=CARD, fg=CRUST,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 6))

        self.hue_cfg = load_config()
        try:
            self.bridge = Bridge()
            lights = [(i, n, col, ok) for i, n, col, ok in self.bridge.lights() if ok]
        except Exception as exc:                           # noqa: BLE001
            self.bridge = None
            lights = []
            tk.Label(c, text=f"bridge unavailable: {exc}", bg=CARD, fg=RED,
                     wraplength=440, justify="left",
                     font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 12))

        self._light_ids = [i for i, _, _, _ in lights]
        labels = [f"{n}{'' if col else '  (white only)'}" for _, n, col, _ in lights]
        idx = self._light_ids.index(self.hue_cfg["light"])             if self.hue_cfg["light"] in self._light_ids else 0

        self.hue_light = self._combo(c, "Light", labels or ["none found"], idx if labels else 0)
        self.hue_colour = self._combo(c, "Colour", list(COLOURS),
                                      list(COLOURS).index(self.hue_cfg["colour"])
                                      if self.hue_cfg["colour"] in COLOURS else 0)
        eff_names = list(EFFECTS)
        cur_eff = next((k for k, v in EFFECTS.items()
                        if v == self.hue_cfg["effect"]), eff_names[0])
        self.hue_effect = self._combo(c, "Effect", eff_names, eff_names.index(cur_eff))
        self.hue_bri = self._combo(c, "Brightness",
                                   ["Dim", "Medium", "Bright", "Full"], 3)

        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", padx=16, pady=(8, 4))
        self.hue_restore = tk.BooleanVar(value=self.hue_cfg.get("restore", True))
        tk.Checkbutton(row, text="put the light back afterwards",
                       variable=self.hue_restore, command=self.save_hue,
                       bg=CARD, fg=MUTED, selectcolor=CARD_HI,
                       activebackground=CARD, activeforeground=TEXT,
                       font=("Segoe UI", 9), bd=0,
                       highlightthickness=0).pack(side="left")

        btns = tk.Frame(c, bg=CARD)
        btns.pack(fill="x", padx=16, pady=(4, 14))
        tk.Button(btns, text="TEST ALERT", command=self.test_hue,
                  bg=CARD_HI, fg=TEXT, activebackground=CRUST,
                  activeforeground=BG, font=("Segoe UI", 10, "bold"),
                  bd=0, relief="flat", cursor="hand2",
                  pady=7).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(btns, text="SAVE", command=self.save_hue,
                  bg=CRUST, fg=BG, activebackground=TEXT,
                  activeforeground=BG, font=("Segoe UI", 10, "bold"),
                  bd=0, relief="flat", cursor="hand2",
                  pady=7).pack(side="left", expand=True, fill="x", padx=(4, 0))

        for cb in (self.hue_light, self.hue_colour, self.hue_effect, self.hue_bri):
            cb.bind("<<ComboboxSelected>>", lambda _e: self.save_hue())

    def current_hue_cfg(self):
        bri = {"Dim": 60, "Medium": 140, "Bright": 210, "Full": 254}
        light = (self._light_ids[self.hue_light.current()]
                 if self._light_ids else self.hue_cfg["light"])
        return {
            "light": light,
            "colour": self.hue_colour.get(),
            "effect": EFFECTS[self.hue_effect.get()],
            "brightness": bri.get(self.hue_bri.get(), 254),
            "seconds": 18,
            "restore": bool(self.hue_restore.get()),
            "speak_enabled": bool(self.speak_on.get()),
            "speak_device": self.speak_dev.get(),
            "speak_text": self.speak_txt.get().strip() or "Tumble dryer finished.",
            "speak_volume": None,
        }

    def save_hue(self):
        cfg = self.current_hue_cfg()
        save_config(cfg)
        self.hue_cfg = cfg
        self.write(f"light alert saved: {cfg['colour']} on light {cfg['light']}")
        if cfg.get("speak_enabled"):
            threading.Thread(
                target=prerender, args=(cfg["speak_text"],),
                kwargs={"log": lambda m: self.out_q.put(("log", m))},
                daemon=True).start()

    def test_hue(self):
        if not self.bridge:
            self.write("no Hue bridge")
            return
        cfg = self.current_hue_cfg()
        save_config(cfg)
        self.write("testing alert ...")
        threading.Thread(
            target=lambda: self.bridge.alert(cfg, log=lambda m: self.out_q.put(("log", m))),
            daemon=True).start()

    def _speak_panel(self, parent=None):
        c = self._card(parent)
        tk.Label(c, text="SPEAK IT (GOOGLE HOME)", bg=CARD, fg=CRUST,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 6))

        cfg = load_config()
        self.speak_on = tk.BooleanVar(value=cfg.get("speak_enabled", False))
        tk.Checkbutton(c, text="announce when the cycle finishes",
                       variable=self.speak_on, command=self.save_hue,
                       bg=CARD, fg=MUTED, selectcolor=CARD_HI,
                       activebackground=CARD, activeforeground=TEXT,
                       font=("Segoe UI", 9), bd=0,
                       highlightthickness=0).pack(anchor="w", padx=14)

        # discovery takes ~8s, so do it off the UI thread and fill in after
        self.speak_dev = self._combo(c, "Speaker",
                                     [cfg.get("speak_device", "searching...")], 0)
        threading.Thread(target=self._find_speakers, daemon=True).start()

        r = tk.Frame(c, bg=CARD)
        r.pack(fill="x", padx=16, pady=3)
        tk.Label(r, text="Says", width=12, anchor="w", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.speak_txt = tk.Entry(r, bg=FIELD, fg=INK, insertbackground=INK,
                                  relief="flat", font=("Segoe UI", 10))
        self.speak_txt.insert(0, cfg.get("speak_text",
                                         "Tumble dryer finished. Go empty it."))
        self.speak_txt.pack(side="left", fill="x", expand=True, ipady=5)
        # Warm the cache ~2s after typing stops so TEST never pays the render.
        self._speak_after = None
        self.speak_txt.bind("<KeyRelease>", self._speak_typed)

        btns = tk.Frame(c, bg=CARD)
        btns.pack(fill="x", padx=16, pady=(8, 14))
        tk.Button(btns, text="TEST", command=self.test_speak,
                  bg=CARD_HI, fg=TEXT, activebackground=CRUST,
                  activeforeground=BG, font=("Segoe UI", 10, "bold"),
                  bd=0, relief="flat", cursor="hand2",
                  pady=7).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(btns, text="SAVE", command=self.save_speak,
                  bg=CRUST, fg=BG, activebackground=TEXT,
                  activeforeground=BG, font=("Segoe UI", 10, "bold"),
                  bd=0, relief="flat", cursor="hand2",
                  pady=7).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _speak_typed(self, _event=None):
        if self._speak_after:
            self.after_cancel(self._speak_after)
        self._speak_after = self.after(2000, self._warm_speech)

    def _warm_speech(self):
        text = self.speak_txt.get().strip()
        if not text or is_cached(text):
            return
        self.write("caching new announcement audio ...")
        threading.Thread(
            target=prerender, args=(text,),
            kwargs={"log": lambda m: self.out_q.put(("log", m))},
            daemon=True).start()

    def _find_speakers(self):
        try:
            names = [n for n, _m, _t in list_speakers()]
        except Exception as exc:                           # noqa: BLE001
            self.out_q.put(("log", f"speaker search failed: {exc}"))
            return
        if not names:
            return
        cur = load_config().get("speak_device")
        self.speak_dev.configure(values=names)
        self.speak_dev.current(names.index(cur) if cur in names else 0)
        self.out_q.put(("log", f"speakers found: {', '.join(names)}"))

    def save_speak(self):
        cfg = self.current_hue_cfg()
        save_config(cfg)
        self.hue_cfg = cfg
        state = "on" if cfg["speak_enabled"] else "off"
        self.write(f"announcement saved ({state}): \"{cfg['speak_text']}\"")
        if cfg["speak_enabled"] and not is_cached(cfg["speak_text"]):
            self._warm_speech()

    def test_speak(self):
        self.save_hue()
        cfg = load_config()
        if is_cached(cfg["speak_text"]):
            self.write("testing announcement ...")
        else:
            self.write("new message - rendering it first, takes about 20s ...")
        threading.Thread(
            target=lambda: announce(cfg["speak_text"], cfg["speak_device"],
                                    volume=cfg.get("speak_volume"),
                                    log=lambda m: self.out_q.put(("log", m))),
            daemon=True).start()

    def _activity(self, parent=None):
        c = self._card(parent, expand=True)
        tk.Label(c, text="PASTIE DRYER ACTIVITY", bg=CARD, fg=CRUST,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.log = tk.Text(c, height=5, wrap="word", bg=CARD_HI, fg=MUTED,
                           font=("Consolas", 9), bd=0, relief="flat",
                           insertbackground=TEXT)
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.log.configure(state="disabled")

    # ---- behaviour --------------------------------------------------------
    def write(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_start(self):
        self.cmd_q.put({
            "program": PROGRAMS[self.prog.current()][1],
            "dry": list(DRY_LEVEL)[self.dry.current()],
            "temp": list(TEMP_LEVEL)[self.temp.current()],
        })
        self.write(f"queued: {self.prog.get()}")

    def drain(self):
        try:
            while True:
                kind, payload = self.out_q.get_nowait()
                if kind == "log":
                    self.write(payload)
                elif kind == "conn":
                    self.sub.configure(text=payload, fg=GREEN)
                else:
                    self.apply(payload)
        except queue.Empty:
            pass
        self.after(400, self.drain)

    def apply(self, s):
        if not s:
            self.pill.configure(text="  NO DATA  ", fg=RED, bg=CARD_HI)
            return

        mode = MACH_MODE.get(s["machMode"], f"mode {s['machMode']}")
        colour = MODE_COLOUR.get(mode, TEXT)
        self.pill.configure(text=f"  {mode.upper()}  ", fg=BG, bg=colour)

        ph = PR_PHASE.get(s["prPhase"], f"phase {s['prPhase']}")
        self.phase.configure(text=f"pastie dryer phase  ·  {ph}")

        running = mode in ("Running", "Paused")
        rem = s["remaining"]
        rem = int(rem) if str(rem).isdigit() else 0

        if running and rem:
            # dryTimeMM is the whole programme length, so progress is correct
            # even if the app was opened halfway through a cycle. Fall back to
            # the highest remaining we've seen only if the machine doesn't
            # report a sane total.
            total = s.get("total")
            total = int(total) if str(total).isdigit() else 0
            if total < rem:
                self.peak_remaining = max(self.peak_remaining, rem)
                total = self.peak_remaining
            done = (total - rem) / total if total else 0
            self.hero.configure(text=str(rem), fg=CRUST)
            self.hero_unit.configure(text="MINUTES")
            self.hero_cap.configure(text="pastie dryer time left")
        elif mode == "Finished":
            self.peak_remaining = 0
            done = 1.0
            self.hero.configure(text="DONE", fg=BLUE)
            self.hero_unit.configure(text="")
            self.hero_cap.configure(text="go and empty it")
        else:
            self.peak_remaining = 0
            done = 0.0
            self.hero.configure(text="--", fg=MUTED)
            self.hero_unit.configure(text="")
            self.hero_cap.configure(text="not running")

        self.bar_bg.update_idletasks()
        self.bar.configure(
            bg=colour if running or mode == "Finished" else CARD_HI,
            width=int(self.bar_bg.winfo_width() * max(0.0, min(1.0, done))))

        self.rows["programme"].configure(text=s["programme"] or "-")
        self.rows["door"].configure(text="closed" if s["door"] == "0" else "open")
        self.rows["remote"].configure(
            text="armed" if s["remote"] == "1" else "not armed",
            fg=GREEN if s["remote"] == "1" else MUTED)
        self.rows["errors"].configure(
            text=s["errors"],
            fg=RED if s["errors"] not in ("0", "None") else TEXT)

        armed = s["remote"] == "1"
        can_start = armed and not running
        self.start_btn.configure(state="normal" if can_start else "disabled",
                                 bg=CRUST if can_start else CARD_HI,
                                 fg=BG if can_start else MUTED)
        if running:
            self.hint.configure(text="")
        elif not armed:
            self.hint.configure(
                text="Remote not armed. At the machine: power on and set the dial "
                     "to the remote position. It switches off after every cycle, "
                     "so this is needed for each load.")
        else:
            self.hint.configure(text="")


if __name__ == "__main__":
    App().mainloop()
