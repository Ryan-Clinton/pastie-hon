# Contributing to Pastie

Contributions welcome. This is a hobby project — nobody's paid, nothing's
urgent, and if you're waiting on a review it's because someone's at work.

Read [`docs/SPEC.md`](docs/SPEC.md) first. It explains how the thing is put
together and, more importantly, what we've learned about Haier's system that
isn't documented anywhere. It'll save you hours.

## Getting set up

```
git clone <this repo>
cd pastie
python -m venv .venv
.venv\Scripts\pip install pyhon-revived pychromecast gTTS pillow
```

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

- **Work around a safety interlock.** The machine refuses remote start unless
  someone armed it at the panel. That's deliberate, it's enforced in the
  appliance's own firmware, and we're not interested in defeating it.
- **Enable commands for an appliance type nobody has verified.** Reading state is
  fine. Sending commands to hardware nobody has tested is how you set an oven to
  something unexpected.
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

Open an issue, but don't include a working exploit or your own credentials. If
it's serious enough that you'd rather not post it publicly, say so in the issue
and we'll find another way.

## Code of conduct

Be decent. It's a tumble dryer.
