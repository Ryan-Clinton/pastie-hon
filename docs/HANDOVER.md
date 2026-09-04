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

**Nothing has been pushed.** This is the live blocker and the explanation for
the licence gap below. `github.com/Ryan-Clinton/pastie-hon` exists, is described
and has topics, and is **empty** — the initial push is refused because the OAuth
token lacks the `workflow` scope and the history contains `.github/workflows/`.
Nothing else can be judged until this is resolved: grant `workflow` to the token
(or `gh auth refresh -s workflow`) and push.

**~~GitHub does not detect the licence.~~** Not line endings and not indexing
lag: GitHub cannot detect a licence in a repository with no files in it. It will
resolve itself with the first successful push. Worth re-checking then.

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

**The service does not start at login.** It runs while somebody runs it. This is
the last unanswered question from `SPEC.md` section 14, experiment 4, and it
needs an elevated prompt: register a scheduled task under the service identity,
connect MQTT, and confirm `Lifecycle Connection Success` appears. Until that is
seen, treat service-mode MQTT as unverified — the prototype's notifier runs as
SYSTEM but only ever *polled*, and MQTT is what drags in the Amazon networking
components that are fussy about how they are started.

**The Start menu shortcut points at the old prototype `.exe`.** Anyone clicking
it gets the August build with its plaintext credentials file, not this. Either
repoint it at `pastie-app`, or package the new app and service properly — the
latter is what `SPEC.md` section 11 asks for, and it is a real job now there are
two processes and PyInstaller has to be talked through the Amazon components.

**No pushed MQTT message has ever been observed.** Connection and subscription
are proven against the real appliance; delivery is not, because the machine has
been idle every time it was tested. Neither is recovery after a long
disconnection, nor what happens when credentials expire mid-cycle.

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
