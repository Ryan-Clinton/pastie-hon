# Reverse-engineering hOn without guessing

*A short write-up of how Pastie learns what an appliance's numbers mean. The
rules are in [SPEC.md](SPEC.md) §9; the mappings are in
[`connector/profiles.py`](../src/pastie/connector/profiles.py).*

Haier's hOn service reports an appliance as a bag of small numbers: `machMode`
2, `prPhase` 19, `message` 4. The community has shared tables of what they mean.
Those tables are a good start and a bad authority. On the one machine this
project owns, a Haier HD90-A2959R-UK dryer, two of them turned out to be wrong in
ways that mattered.

- **Mode 7 is "ready" in the shared constants.** On this dryer, 7 is what the
  machine sits in after a *completed* cycle: the finish signal. Believing the
  table would mean never noticing a load had finished.
- **The full water tank.** Haier's own app has a "full tank" string, and the
  community's phase table has three phases marked "unknown". The obvious guess
  was that the tank is one of those phases. It isn't a phase at all. When the
  tank alarm sounded, one pushed update changed `pause` 0→1, `message` 0→4 and
  `machMode` 2→3, and `prPhase` stayed where it was. Ten minutes later, when the
  tank was emptied, the exact mirror came through.

The guess was plausible, well reasoned, and wrong. That's the argument for the
rules below.

## Rule 1: record before interpreting

The service writes a journal line for every raw value that changes between
readings. Nobody has to sit watching a dryer to find out what a number does:
you run the machine normally and read the journal afterwards. The tank was
identified that way, to the second.

## Rule 2: keep what's known to be safe, not remove what's known to be bad

hOn's replies include the appliance's registered **GPS coordinates**, its MAC
address and its serial number. Anything recorded, shared as test data, or
attached to a bug report has to lose those. Pastie uses an **allow-list**
([`connector/scrub.py`](../src/pastie/connector/scrub.py)): a field survives only
if somebody has looked at it and put it on the list. Removing known-bad fields
one at a time fails the day Haier adds a new one.

There's a cost, and it caught us. The tank's `message` field wasn't on the list
when the tank first filled, so the journal built to catch exactly that event
recorded only "paused". The fix was the list, not the approach. It's also why
a new appliance's fields go on the list *before* it arrives, as the washing
machine's have.

## Rule 3: verified per mapping, by someone who owns one

An appliance type is **verified** or it isn't, and verification means somebody
who owns one has watched the numbers do what the mapping says. Reasoning about a
translation file doesn't count. An unverified appliance gets its name, its model
and its raw values, labelled as raw, and nothing else: no "running", no
"finished", no fault alerts, no commands. Mode 6 means a fault on this dryer.
That's no reason to tell somebody their oven has failed.

Verification is per mapping, not per appliance. Confirm what "running" looks
like, flip that one flag, and leave the rest raw until somebody gets to it.

## Own a Haier, Candy or Hoover appliance?

That's the most useful contribution there is, and it needs no code. Run Pastie,
use the machine normally, and
[tell us what the numbers did](https://github.com/Ryan-Clinton/pastie-hon/issues/new?template=appliance.md).
Quote individual fields, and never paste a raw dump.
