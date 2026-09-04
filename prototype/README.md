# The prototype

The scripts this project was built from, kept exactly as they were.

They are **not** the current version — that is `src/pastie`, and it does
everything these do plus the things these got wrong. These are here for two
reasons:

1. **They are the record of what was measured.** Everything the specification
   says about Haier's system - that `machMode 7` is the finish signal, that
   `remoteCtrValid` disarms after every completed cycle, that a stop command can
   be accepted and ignored - was observed by running these against a real
   Haier HD90-A2959R-UK. Rewriting them would lose the provenance.
2. **They still work.** If the framework breaks and you need the light to flash
   tonight, `python notify.py` will do it.

They are excluded from linting and type checking on purpose. Held to the
framework's standards they would need changing, and changing them would defeat
the point of keeping them.

## What is here

| Script | What it does |
|---|---|
| `discover.py` | Enumerate appliances and dump everything they expose |
| `status.py` | Print the live state of the dryer |
| `notify.py` | Poll, and flash a Hue light when a cycle ends |
| `dryer_gui.py` | The original window |
| `hue.py`, `speak.py` | Hue v1 and Chromecast announcements |
| `start.py`, `trystop.py` | Start and stop a cycle |
| `probe.py`, `allattrs.py`, `rate.py` | Poking at the API to see what came back |
| `exp_counter.py`, `exp_mqtt.py` | The experiments that answered the questions in `docs/SPEC.md` section 14 |

## Moving to the current version

```
pastie migrate --folder prototype
```

That brings your account across into the encrypted store and your Hue and
speaker settings into the new settings file. Your existing Hue bridge key still
works - there is no button to press.

`.credentials` still holds your password in plain text. Delete it once you are
happy the new version works; that is the whole reason the new one exists.
