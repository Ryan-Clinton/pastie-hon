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
.venv\Scripts\pip install -e ".[dev]" -c constraints.txt
```

Direct dependencies and their exact versions live in `pyproject.toml`; everything they
pull in is locked in `constraints.txt`, which is why the install line above passes it. Please don't
`pip install` things ad hoc — if two of us clone this a month apart we need to be
running the same software, or "works on mine" becomes meaningless.

Save your Haier login - it is encrypted with DPAPI, under the account that
saves it - and check the service can see your appliance:

```
.venv\Scripts\pastie login
.venv\Scripts\pastie service      # leave this running
.venv\Scripts\pastie status       # in another window
```

If that names your machine, you're ready.

Before sending anything, these all have to be clean:

```
pytest
ruff check .
ruff format --check src tests scripts
mypy
```

The test suite needs no appliance and no network - that is deliberate, and
keeping it that way is a review criterion. If a change can only be tested
against real hardware, the design is wrong somewhere.

## The most useful things you could do

**Own a Haier appliance that isn't a tumble dryer?** That's the single most
valuable contribution available. Pastie has been tested on exactly one machine.
It will already detect yours and show its raw values without interpreting them;
open an issue saying what those values do as you use the machine, and we can
work out what they mean together.

Do not paste a raw dump into an issue - it contains your appliance's GPS
coordinates, MAC address and serial number. Quote individual fields.

**Want your brand of light supported?** Section 8 of the spec is the walkthrough,
and `src/pastie/messengers/webhook.py` is the shortest example to copy - about
eighty lines including its docstring. LIFX, WiZ and Nanoleaf all talk directly
over your home network with no accounts involved, so they're approachable.

**Just want to help?** Phone notifications through ntfy or Telegram, and a plain
Windows desktop notification, are both a single messenger file each.

## Where the code lives

```
src/pastie/core          what state it's in and what just happened.
                         No network, no Windows, no Haier - so its tests
                         need none of those either.
src/pastie/connector     the only package that knows Haier's field names
src/pastie/messengers    things that react: lights, speakers, webhooks
src/pastie/service       the long-running half, and the app's channel
src/pastie/app           the window
prototype/               the original scripts, kept as the record of what
                         was measured. Not maintained to the same standard,
                         and deliberately excluded from the linters.
```

Start in `core` if you want to understand the project. It is where the design
lives, and it reads without knowing anything about Haier.

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
- **Commit your own credentials.** `prototype/.credentials` is gitignored. So is `dump/` —
  the appliance data Haier return includes your machine's **GPS coordinates**,
  MAC address and serial number. Check what you're committing.

## Test data

If you're sharing a recorded response for testing, strip it first. Don't try to
remove the sensitive bits one at a time — you'll miss something, and Haier can
add new fields whenever they like. Instead, keep only the fields you know are
safe and drop everything else.

That allow-list is `src/pastie/connector/scrub.py`, and it is what every reading
already passes through before anything else sees it. If a field you need is
missing from it, add it there first — having looked at what it actually
contains. `tests/fixtures/README.md` explains the shape of a recorded sequence.

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
