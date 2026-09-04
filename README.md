# Pastie

Tells you what your Haier appliance is doing, and does something about it —
flashes a Hue light, says it out loud on a Google Home, starts an already-armed
cycle from your desk.

The phone app already sends a notification when a cycle ends. Pastie's point
isn't the notification. It's **doing something across the rest of your kit**.

> **Unofficial.** Not affiliated with, endorsed by, or supported by Haier. It
> talks to Haier's hOn service through an unofficial, community-maintained
> client, which means Haier could change something tomorrow and break it. MIT
> licensed. Nobody's paid.

Built for, and tested against, a **Haier HD90-A2959R-UK tumble dryer**. Every
other appliance type Haier's system covers is detected and shown, but not
interpreted — see [Trust](#trust) for why that distinction is the whole design.

```
$ pastie status
Working normally

Tumble dryer  (HD90-A2959R-UK)
  state       running
  programme   Mixed load
  remaining   about 120 min (still estimating)
```

---

## What it does

- **Tells you a cycle finished** — Hue light, spoken announcement, webhook, or
  all three at once
- **Tells you when it finished while you weren't watching**, and says so
  honestly rather than pretending it just happened
- **Tells you about faults**, which the phone app does not
- **Starts a cycle** that has been armed at the machine, and tells you whether
  the machine actually started rather than whether the server accepted the request
- **Tells you when the filter needs cleaning** — the appliance keeps its own
  service schedule and nobody had noticed

## What it isn't

- **Not a replacement for Home Assistant.** If you run Home Assistant already it
  does far more than this ever will. Pastie is for people who want a light to
  flash without installing a home-automation platform.
- **Not a way round safety features.** Where an appliance requires somebody
  present, that's the design, not a bug.

---

## The three problems worth reading about

Most of this project is ordinary. These three are not, and they're why it is
built the way it is.

### "The dryer finished" is harder than it looks

The obvious version — *if the machine says finished, announce it* — is wrong in
both directions. It shouts about a load that was put away on Tuesday, and it
says nothing about the one that finished while the PC was rebooting.

So **unknown is a real state**. The first reading of a session sets a baseline
and announces nothing. Anything that changed since last time is reported as a
gap, not as news:

> The tumble dryer finished while Pastie wasn't running (one cycle, some time
> after 20:10).

That sentence can say *one cycle* because the appliance keeps a counter of
completed programmes, in a statistics endpoint separate from its live state. If
the counter moved, a cycle finished — and the counter is also what tells a
completed cycle apart from a cancelled one. Without it, Pastie says the vaguer,
truthful thing instead.

Every announcement is written down before it goes out, so a restart can't fire
it twice. ([`core/tracker.py`](src/pastie/core/tracker.py))

### "Accepted" doesn't mean "done"

Sending a command to Haier's servers returns success as soon as they've taken
the message. We proved that means nothing: a stop command returned success while
the machine sat there ignoring it.

So every command has three parts — an id, a state that would prove it worked,
and a deadline — and you're shown which of them actually happened:

```
Start requested         20:41:02
Accepted by Haier       20:41:03
Machine confirmed       20:41:06   OK
```

or

```
Accepted by Haier, but the machine didn't react within 20 seconds
```

Success is never reported off the back of a server response.
([`core/commands.py`](src/pastie/core/commands.py))

### Trust

Haier's system covers sixteen appliance types. We own a dryer.

Guessing what a number means on a dryer wastes a load of washing. Guessing on an
oven or an induction hob is a different matter. So an appliance type is either
**verified** — somebody owns one and has confirmed what its numbers mean — or it
is not, and an unverified one gets:

| Unverified | Verified |
|---|---|
| Detected, named, model shown | Everything on the left, plus: |
| Raw values, labelled as raw | Proper state: running, finished, faulted |
| **No interpreted state** | Progress and time remaining |
| **No fault alerts** | Fault alerts |
| **No commands at all** | Commands that have been tested |

Verification is per-mapping, not per-appliance. If you own a Haier washing
machine, confirming what "running" looks like on it is one line in
[`connector/profiles.py`](src/pastie/connector/profiles.py) and the most useful
contribution anyone could make.

---

## How it fits together

```
Haier's servers
      |
  connector      the only code that knows Haier's field names
      |
    core         what state it's in, what changed, what that means
      |
  +---+-----------------+
  |                     |
messengers            app
(Hue, speakers,       (window, settings)
 webhooks)
```

`core` imports nothing from the layers around it and no third-party client — no
network, no Windows, no Haier. That's what makes the awkward parts testable
against recorded sequences instead of against an appliance: restarts, duplicate
updates, readings arriving out of order, a cycle that finished while the PC was
off.

If `machMode` ever appears outside `connector`, that's a rejected pull request —
not because the name is ugly, but because it's the difference between Haier
changing something costing one file and costing the whole codebase. They did
change something, in June 2026, and everything broke until the community client
caught up.

The **service** holds the only connection to Haier. The **app** doesn't open its
own — it asks the service over a Windows named pipe, so the two can't disagree
about what the machine is doing, and nothing listens on a network address that a
web page in your browser could reach.

---

## Running it

Windows, Python 3.11 or newer.

```powershell
git clone https://github.com/REPLACE-ME/pastie
cd pastie
python -m venv .venv
.venv\Scripts\pip install -e .

.venv\Scripts\pastie login      # hOn email and password, encrypted with DPAPI
.venv\Scripts\pastie service    # the background half - leave it running
.venv\Scripts\pastie status     # in another window
```

Then `pastie-app` for the window, where the messengers are set up.

Already running the old prototype? `pastie migrate --folder prototype` brings
your account and your Hue and speaker settings across. **Your existing Hue key
keeps working** — no button to press on the bridge.

### Where things live

`pastie where` prints it. In short: settings, credentials and what Pastie
remembers live in `%PROGRAMDATA%\Pastie`, because the service doesn't run as you
and anything under your profile would be unreadable to it.

### Your hOn password

Encrypted with DPAPI under the service's own Windows identity — a copy of the
file is useless on another account or another machine. The app hands a new
password to the service and never stores or reads one; there is deliberately no
way to read one back out.

An hOn account created with Google sign-in has no password, and the client can't
do OAuth. Set a password on the same address separately, or use hOn's Family
Sharing to add a second, password-based account.

---

## Adding a light, a speaker, or anything

This is the bit most people will want. A messenger is anything Pastie can poke
when something happens: write one file, add one line to
[`messengers/__init__.py`](src/pastie/messengers/__init__.py), send a pull
request.

You don't write any interface code. A messenger *describes* its settings and the
settings screen draws itself from that description.

```python
class MyLight:
    name = "mylight"
    label = "My Light"

    def settings(self):        # the settings screen is built from this
        return [Setting("enabled", "Flash my light", Kind.BOOL, default=False)]

    async def discover(self, config): ...   # list what's available
    async def test(self, config): ...       # fire once, on demand
    async def react(self, event, config): ...
```

Four rules, enforced centrally in
[`messengers/base.py`](src/pastie/messengers/base.py) rather than trusted to
each author:

- **A messenger failing must not take anything else down.** They run
  concurrently, isolated, each with its own timeout. A speaker that's switched
  off must not stop the light flashing.
- **Don't strobe.** Flashing light can trigger seizures in people with
  photosensitive epilepsy, and Philips's own terms put that on the application.
  Flash rate and duration are capped centrally and no messenger can go round it.
- **One alert at a time per target**, or two events will both snapshot a light's
  state and both restore it.
- **Never log a password, key or token.**

Genuinely useful ones nobody has written yet: LIFX, WiZ and Nanoleaf (all talk
directly over your network, no accounts), ntfy or Telegram for phone
notifications, and a plain Windows desktop notification.

---

## Developing

```powershell
pip install -e ".[dev]"
pytest          # 131 tests, no appliance required
ruff check .
mypy
```

The tests check **what Pastie announced**, not what it parsed — a dependency
update that quietly changes how a field is decoded shows up as a missing or
duplicated announcement, which is the thing a user would actually notice. Every
scenario in [the specification](docs/SPEC.md)'s "what has to be tested" section
has a test named after it.

**Recorded test data is stripped by keeping only fields known to be safe**, never
by removing the bad ones one at a time — Haier's responses carry the appliance's
GPS coordinates, MAC address and serial number, and they can add new fields
whenever they like. The allow-list is
[`connector/scrub.py`](src/pastie/connector/scrub.py). The same applies to
anything you attach to a bug report.

- [`docs/SPEC.md`](docs/SPEC.md) — the design, in plain English, including
  everything we know about Haier's system that isn't written down anywhere else
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to send a change
- [`SECURITY.md`](SECURITY.md) — how to report a security problem (please not a
  public issue)
- [`prototype/`](prototype/) — the working scripts this was built from, kept
  verbatim as the record of what was actually measured against the hardware

## Searching the build history

Most of what's known about this dryer was worked out in conversation, and the
reasoning behind a decision is often only in the transcript.
`scripts/history_search.py` searches this project's Claude Code transcripts:

```
python scripts\history_search.py "remote control"
python scripts\history_search.py "machMode" --role all --context 200
```

It searches the live transcript directory *and* an archive copy, and prints the
date window it actually covered — so "no matches" can be told apart from "that
session has been pruned". `scripts/claude-transcript-archive.ps1` keeps the
archive fed; it mirrors and never deletes. Neither script sends anything
anywhere, and the transcripts live outside the repository.

## Licence

MIT. Do what you like with it.
