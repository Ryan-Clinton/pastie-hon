# Handover

For whoever picks this project up next, human or agent. Read this before
touching anything. `docs/SPEC.md` is the authority on design and on every
hardware fact; this file is orientation, current state and the rules that are
easy to break by accident.

Written 2026-09-05 against v0.2.0.

---

## What it is

Pastie tells you what your Haier appliance is doing and does something about it:
flashes a Hue light, speaks on a Google Home, calls a webhook, starts a cycle
that was already armed at the machine.

The phone app already sends a notification when a cycle ends. **That is not the
point of this project.** The point is acting across the rest of the kit, and
saying honestly what is and is not known.

Unofficial. It talks to Haier's hOn service through `pyhon-revived`, a
community-maintained client. Haier can break it at any time, and did in June
2026.

## Current state

v0.2.0. Feature complete for what the spec describes: connector, domain layer,
messengers, service, app, CLI, migration from the prototype, CI on Windows and
Linux across Python 3.11 and 3.12.

`prototype/` is kept deliberately. It is the record of what was actually
measured against the hardware, not dead code to tidy away.

Nothing has been released. The changelog dates are when work landed.

## Commands

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

pytest -q --cov=pastie --cov-report=term-missing
ruff check .
ruff format --check src tests scripts
mypy
python scripts/third_party_notices.py --check
```

Those five checks are exactly what CI runs. Run them before claiming anything
works.

```powershell
pastie login       # hOn credentials, encrypted with DPAPI
pastie service     # background half, leave running
pastie status      # another window
pastie where       # where settings and state live
pastie-app         # the window
```

---

## The rules that must not be broken

These are not style preferences. Each one exists because breaking it produces a
failure that looks like something else.

**`machMode` never appears outside `connector/`.** Nor does any other Haier
field name. The connector is the only code that knows Haier's vocabulary. This
is what makes a Haier-side change cost one file instead of the codebase. A pull
request that leaks a raw field name upward is rejected on that basis alone.

**`core` imports nothing from the layers around it, and no third-party client.**
No network, no Windows, no Haier. This is what makes restarts, duplicate
updates, out-of-order readings and cycles-that-finished-while-off testable
against recorded sequences rather than against an appliance. The Linux leg of
the CI matrix exists purely to prove this stays true; if `core` ever needs
Windows, the Linux job fails and that is the design working.

**Unknown is a real state.** The first reading of a session sets a baseline and
announces nothing. Anything that changed since last time is reported as a gap,
not as news. Announcing a load that was put away on Tuesday is as much a bug as
missing one that finished during a reboot.

**Every announcement is written to the ledger before it goes out.** A restart
must not fire it twice.

**Accepted is not done.** Haier's servers return success as soon as they have
taken the message. This was measured: a stop command returned success while the
machine ignored it. Every command carries an id, a state that would prove it
worked, and a deadline, and the user is shown which of those actually happened.
Never report success off the back of a server response.

**Unverified appliance types get no interpreted state, no fault alerts and no
commands.** Haier's system covers sixteen appliance types and this project owns
a dryer. Guessing what a number means on a dryer wastes a wash; guessing on an
oven or a hob is a different category of mistake. Verification is per-mapping in
`connector/profiles.py`, and adding one requires somebody who owns that
appliance to confirm it, not somebody who reasoned about it.

**The service holds the only connection.** The app asks over a Windows named
pipe rather than opening its own. Two connections can disagree about what the
machine is doing. Nothing listens on a network address a browser could reach.

**Credentials are DPAPI-encrypted under the service's own Windows identity, and
there is deliberately no way to read one back out.** The app hands a new
password to the service and never stores or reads one. Do not add a "show
password" affordance, and do not move credential storage under the user profile:
the service does not run as the user and could not read it.

## Dependencies are pinned exactly, on purpose

Two people cloning a month apart must get the same software. Without that,
"works on mine" means nothing and an upstream change to a reverse-engineered
client is indistinguishable from a local bug.

`awsiotsdk` and `awscrt` are pinned **together**. A mismatched pair has already
broken `pyhon-revived` once.

`THIRD_PARTY_NOTICES.txt` is generated from the pinned set by
`scripts/third_party_notices.py`, never edited by hand, and CI checks it on
Windows because the notices describe what ships inside the Windows .exe and the
dependency set differs by platform.

---

## Known gaps

In the order they are worth fixing. The first four in the original version of
this file are done; what they turned into is recorded here because the reasoning
is worth keeping.

**~~Nothing has been pushed.~~** Done, and the licence gap went with it.
`github.com/Ryan-Clinton/pastie-hon` now holds the history, CI is green on
Windows and Linux across 3.11 and 3.12, and GitHub detects the MIT licence. It
could not before because a repository with no files in it has no licence to
detect - not line endings, and not indexing lag.

The initial push needed a token with `workflow` scope, because the history
contains `.github/workflows/`. A `repo`-only token is refused, and the refusal
names the file rather than the scope, which is a confusing thirty seconds.

**~~No images anywhere.~~** Done. `assets/screenshots/` holds the appliance and
settings tabs, both live against the real service, and the README opens with
them. The bridge address is painted out — the project keeps LAN layout out of
the repository and a screenshot is no exception to that.

**~~No way to run it without the appliance.~~** Done, as `pastie demo`. Five
scenarios through the real connector, brain and command tracker. Each one's
claims are pinned by tests in `tests/test_demo.py`, deliberately: a
demonstration that drifts away from the code is worse than none, because it is a
confident lie. Add a scenario whenever a new piece of behaviour is easier to
show than to describe.

**~~No repository topics set.~~** Done.

**~~The Start menu shortcut points at the old prototype `.exe`.~~** Done.
`scripts/install-shortcuts.ps1` points the Start menu and the Desktop at the
window and puts the service in Startup, and takes the prototype's shortcuts off
the menus. The prototype's build is still on disk in `prototype/`, because
deleting somebody's working fallback is not a script's decision.

**Experiment 4 is still unanswered, and the login task is not the answer.** The
service now starts at login *as the user*, which is what makes a single shortcut
work. That is not the same as running under a service identity, and the question
`SPEC.md` section 14 asks — whether the Haier libraries connect MQTT when
started that way — remains open. It needs an elevated prompt: register a
scheduled task under the service identity and confirm `Lifecycle Connection
Success` appears. The prototype's notifier ran as SYSTEM but only ever *polled*,
and MQTT is what drags in the Amazon networking components that are fussy about
how they are started. Do not let the login task make this look finished.

**Packaging.** There is still no `.exe` for the current build. `SPEC.md` section
11 asks for the packaged artefact to be tested rather than just the code, and it
is a real job now: two processes, and PyInstaller has to be talked through the
Amazon networking components.

**~~No pushed MQTT message has ever been observed.~~** Observed, 2026-09-06,
during a real cycle. They arrive as parameter deltas rather than whole readings:

    appliancestatus/update - {'parameters': [{'parName': 'remainingTimeMM',
    'parOldVal': '197', 'parNewVal': '196'}], 'applianceTypeName': 'TD', ...}

Note the shape. Pastie currently uses a push only as a nudge to re-read
everything, which is correct and wasteful: the delta says exactly what changed.
Using it directly would be an optimisation, and would need care - at-least-once
delivery means duplicates, and a delta applied twice is not always harmless.

**Still unproven:** recovery after a long disconnection, and what happens when
credentials expire mid-cycle. Both need hours of running rather than minutes.

**~~The full water tank has a phase number nobody has written down.~~** Found,
2026-09-11 at 22:07:45 - and it was not a phase. One pushed update, the moment
the machine's own alarm sounded:

    pause 0 -> 1,  message 0 -> 4,  machMode 2 -> 3      (prPhase stayed at 19)

And it cleared ten minutes later, the moment the tank was emptied and the dryer
restarted - the exact mirror, again in a single push:

    pause 1 -> 0,  message 4 -> 0,  machMode 3 -> 2

`message` is the dryer's notification channel: 4 is the full tank, and 1 -
arriving together with `ironingStatus 1` - is "lightweight items are dry". The
reasoning from Haier's `PHASE_ERROR_FULL_TANK` string to the community's
"unknown" phases 8, 12 and 17 was plausible and wrong, which is the whole
argument for recording before interpreting. The tank now raises
`NEEDS_EMPTYING`; see `connector/profiles.py` for the observation it rests on.

Two lessons worth keeping. **The journal built to catch this missed it.**
`message` was not on the privacy allow-list, so it was scrubbed before the
journal ever saw it, and the service recorded only "paused". It was caught
because the client library happens to log raw pushes. Anything left off the
allow-list is also something the journal cannot see - add fields there with that
in mind. And **it is worth sending upstream**: `pyhOn` has no mapping for
`message` on tumble dryers, and the phases it lists as "unknown" are still
unknown.

## Conventions

Commit subjects are lowercase, typed, scoped where it helps:
`feat(connector):`, `fix:`, `docs:`, `test:`. The existing log is the reference.

The changelog is maintained per change, newest first, loosely Keep a Changelog.

Prose in this repo explains *why*, not *what*. The comments in `pyproject.toml`
and `ci.yml` are the house style: each states the reason a decision was made,
usually a failure that happened. Match that. A comment that only restates the
code is noise.

## What not to do

Do not relax the disclosure of uncertainty to make output tidier. The vaguer,
truthful sentence beats the specific, guessed one, and that judgement is
load-bearing throughout.

Do not add a way round an appliance safety feature. Where a machine requires
somebody present, that is the design.

Do not turn this into a Home Assistant competitor. If someone runs Home
Assistant, it already does more. Pastie is for people who want a light to flash
without installing a home automation platform, and the scope discipline is what
keeps it finishable.
