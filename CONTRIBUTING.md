# Contributing to Pastie

Contributions welcome. This is a hobby project — nobody's paid, nothing's
urgent, and if you're waiting on a review it's because someone's at work.

Read [`docs/SPEC.md`](docs/SPEC.md) first. It explains how the thing is put
together and, more importantly, what we've learned about Haier's system that
isn't documented anywhere. It'll save you hours.

## Getting set up

Python 3.11 or newer (PyChromecast needs it).

```
git clone <this repo>
cd pastie
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```

Dependencies and their exact versions live in `pyproject.toml`. Please don't
`pip install` things ad hoc — if two of us clone this a month apart we need to be
running the same software, or "works on mine" becomes meaningless.

Copy `.credentials.example` to `.credentials` and fill in your Haier login.
Then check it can see your appliance:

```
.venv\Scripts\python.exe discover.py
```

If that lists your machine, you're ready.

## The most useful things you could do

**Own a Haier appliance that isn't a tumble dryer?** That's the single most
valuable contribution available. Pastie has been tested on exactly one machine.
Run `discover.py`, open an issue with the output, and we can work out what the
numbers mean together.

**Want your brand of light supported?** Section 8 of the spec is the walkthrough.
LIFX, WiZ and Nanoleaf all talk directly over your home network with no accounts
involved, so they're approachable.

**Just want to help?** Fault alerting and getting passwords out of the plain
text file are both worth doing and neither is difficult.

## Before you open a pull request

Please do:

- **Keep Haier's field names in the connector.** Their data is full of things
  like `machMode` and `remoteCtrValid`. Those names must not leak into the rest
  of the code. When Haier change something — and they do — we want one file to
  fix, not fifty.
- **Verify commands by watching the machine, not the response.** Haier's servers
  return success when they've *received* your command, which is not the same as
  the machine doing it. We've watched a stop command return success and be
  ignored.
- **Put lights back how you found them.** Save the state, do your thing, restore
  it.
- **Check a light supports colour before sending one.** White-only bulbs reject
  colour commands outright.
- **Say if something is untested.** "I think this is right but I don't own one"
  is a genuinely useful pull request. Pretending to be sure isn't.

Please don't:

- **Work around a safety interlock.** On the dryer we've tested, remote start is
  refused unless someone armed it at the panel, and it disarms again after every
  cycle. Other appliances may differ — but the rule is universal: **Pastie never
  bypasses or weakens a safety interlock an appliance exposes.**
- **Interpret an unverified appliance's numbers.** An untested type gets its raw
  values shown as diagnostics and nothing more — no "running", no "finished", no
  fault alerts, no commands. If a new oven reports mode 6, we don't announce a
  fault just because that's what 6 means on a dryer. Verification is per-mapping:
  confirm what one value means, mark that one verified, leave the rest raw.
- **Add strobing or rapid flashing.** Flashing lights can trigger seizures in
  people with photosensitive epilepsy. Pastie limits flash rate and duration
  centrally — don't add anything that bypasses it.
- **Log passwords, keys or tokens.** Ever, including in error messages.
- **Commit your own credentials.** `.credentials` is gitignored. So is `dump/` —
  the appliance data Haier return includes your machine's **GPS coordinates**,
  MAC address and serial number. Check what you're committing.

## Test data

If you're sharing a recorded response for testing, strip it first. Don't try to
remove the sensitive bits one at a time — you'll miss something, and Haier can
add new fields whenever they like. Instead, keep only the fields you know are
safe and drop everything else.

## Style

Match what's there. It's plain Python with no framework and no cleverness, and
that's deliberate — the appliance side is complicated enough without the code
being complicated too.

## Reporting a security problem

**Not in a public issue.** See [SECURITY.md](SECURITY.md) — use GitHub's private
vulnerability reporting under the Security tab.

## Licensing your contribution

By opening a pull request you agree to license your contribution under the
project's MIT licence. No paperwork beyond that.

## Code of conduct

Be decent. It's a tumble dryer.
