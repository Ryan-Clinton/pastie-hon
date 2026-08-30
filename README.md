# Pastie Tumble Dryer

Desktop control panel and finish-notifier for a **Haier HD90-A2959R-UK** heat pump
tumble dryer, driven through the hOn cloud API via
[pyhOn](https://github.com/Andre0512/pyhOn).

Live status and remote start from a Windows app, a Philips Hue light that flashes
when the cycle ends, and a spoken announcement on a Google Home speaker.

> Unofficial and unaffiliated with Haier. `pyhOn` is reverse-engineered and can
> stop working whenever Haier change their API.

## What it does

| | |
|---|---|
| `dryer_gui.py` | The app: live status, progress, remote start, alert settings |
| `notify.py` | Background watcher — flashes a Hue light and speaks when a cycle ends |
| `discover.py` | Dumps every command, setting and programme the appliance exposes |
| `status.py` / `probe.py` | Live state; `probe.py` reads twice around `update()` to prove data isn't stale |
| `start.py` | Start a cycle from the command line |
| `hue.py` / `speak.py` | Philips Hue and Google Cast helpers |

## Setup

1. Register the appliance in the **hOn** phone app first — the API only sees
   appliances already bound to your account.
2. `python -m venv .venv && .venv\Scripts\pip install pyhOn pychromecast gTTS pillow`
3. Copy `.credentials.example` to `.credentials` and fill in your hOn login,
   plus your Hue bridge IP and API key if you want the light alert.
4. `\.venv\Scripts\python.exe discover.py` to confirm it can see the machine.

Optionally copy `cast_hosts.example.json` to `cast_hosts.json` with your speaker's
IP address — mDNS discovery is unreliable when running as a scheduled task.

## Findings

Notes from working this out against a real machine. Some of it isn't documented
anywhere I could find, and one part contradicts the community mapping.

### Remote start is gated at the appliance

`startProgram` is refused unless `remoteCtrValid == 1`, which needs **both**:

1. the machine powered on (`onOffStatus == 1`), and
2. the panel dial physically set to the **remote** position

Selecting a normal programme on the dial does not arm it — it actively *dis*arms
it. On the remote position `programName` reads `No Program`, which is correct:
programme selection passes to the API. There is no Wi-Fi button on this model.

**It disarms itself after every cycle**, by design — Haier's documentation states
the remote control turns off once a cycle completes. So remote start is
semi-attended: you must arm it at the machine for each load. Useful for delayed
starts, not for starting the laundry from work.

### Value mappings

Confirmed against [Andre0512/hon](https://github.com/Andre0512/hon)'s `const.py`,
which is the authoritative source and saves a lot of guessing:

```
machMode    0,1 ready   2 running   3 pause   4,5 scheduled
            6 error     7 END_MODE (finished)   8 test   9 stopping

dryLevel    12 iron dry   13 cupboard dry   14 ready to wear   15 extra dry
            (this model's range is 12-14, so 14 is the driest available)

tempLevel   1 cool   2 low   3 middle   4 high
```

### Timing fields

- **`dryTimeMM`** is the total programme length and stays constant — use it for
  progress.
- **`remainingTimeMM`** is minutes remaining, but is unreliable during the early
  sensing phase, where it swings around and can go *up*. It settles once the
  machine moves into its main drying phase.

### prPhase appears to be inverted on this model

The community mapping has `19 = drying` and `15 = heat_stroke`. On this machine
the observed behaviour is the opposite way round: **19 is the early unsettled
phase** (erratic time estimate) and **15 is the main drying run** (clean
countdown at ~1 min/min). Same signature across every cycle observed. Treat the
labels with suspicion on an HD90.

### Other gotchas

- A command's `.send()` returning `True` means Haier's **cloud** accepted the
  request, not that the machine acted on it. Always confirm with a state readback
  — `stopProgram` returns `True` and does nothing when the machine is idle.
- `energyLabel` (1–5) is metadata describing the programme's energy class, not a
  control. Setting it does nothing.
- An hOn account created with **Google sign-in has no password**, and `pyhOn`
  cannot use OAuth. Set a password on the same address separately, or use hOn's
  Family Sharing to add a second, password-based account.
- The appliance is **cloud-only** — a port scan of the device on the LAN found no
  listening services. It connects outbound to AWS IoT.
- `discover.py` output contains the appliance's registered **GPS coordinates**,
  MAC address and serial number. `dump/` is gitignored for that reason.

## Speed

A spoken announcement was taking ~28 seconds. Profiling showed where it went:

```
gTTS render      21.5s   <- 77% of it
connect           0.1s
casting           1.3s
playback          4.5s
```

Rendered speech is now cached by content hash, taking a repeat announcement to
about 9 seconds, most of which is the message playing. The cache is warmed in the
background as you type, so changing the message doesn't cost you the render.

## Licence

MIT. Do what you like with it.
