# Pastie — how it works and how to extend it

Pastie tells you what your Haier appliance is doing and lets you do something
about it — flash a light, announce it on a speaker, start an already-armed cycle
from your desk.

This document explains how the thing is put together, what we already know about
Haier's system that isn't written down anywhere else, and how to add your own
lights, speakers and appliances to it.

**Pastie is an unofficial community project. It is not affiliated with, endorsed
by, or supported by Haier.** It interoperates with Haier's hOn service using an
unofficial, community-maintained client.

**It's a hobby project.** Nobody's paid and there are no guarantees. It's
released under the MIT licence, which means you may use it commercially if you
want to — the maintainers simply don't sell it themselves.

Status: **design, revision 5.** A working prototype exists. The full version
described here is not built yet.

---

## 1. What Pastie does

You own a Haier appliance with Wi-Fi. It talks to Haier's servers. Haier's phone
app talks to those same servers. Pastie is a third thing that talks to them, so
your PC can know what the machine is doing.

Once your PC knows, it can do things the phone app won't:

- Flash a Philips Hue light when the cycle finishes
- Say "the tumble dryer's finished" through a Google Home speaker
- Show a proper progress bar on your desktop
- Start a cycle that's already been armed at the machine, without walking back to it
- Tell you when something's gone wrong, loudly

The phone app already sends you a notification when a cycle ends. Pastie's point
isn't notification — it's **doing something across your other kit**.

## 2. What Pastie is not

- **Not a replacement for Home Assistant.** If you already run Home Assistant, it
  does far more than this ever will. Pastie is for people who want appliance
  control without installing a whole home-automation platform.
- **Not a way round safety features.** Where an appliance requires someone
  present, we respect that and won't accept changes that defeat it.
- **Not official.** Haier could change something tomorrow and break it.
- **Not something we sell.** MIT licensed; do as you like within those terms.

---

## 3. Decisions already made

These are settled. If you disagree, open an issue before writing code, because a
pull request that assumes otherwise won't merge.

| Decision | Why |
|---|---|
| **Pastie runs on its own.** Home Assistant is optional | Requiring people to install a home-automation platform to get a light to flash is too much to ask |
| **Windows only, for now** | It's what it's built and tested on. Someone can port it later |
| **Python 3.11 or newer** | PyChromecast needs it |
| **The watcher runs as a Windows service** | The whole point is being told the dryer's finished when you're *not* at the PC |
| **Contributions go in the main codebase**, not separate plugin packages | The packaged `.exe` can only include code that existed when it was built |
| **MIT licence** | Simple, permissive, well understood |
| **We use `pyhon-revived`** to talk to Haier | It's the maintained version, and carries an authentication fix the older one lacks |
| **Dependencies are pinned to exact versions** | Two people cloning a month apart must get the same software |

---

## 4. How it fits together

```
Haier's servers
      ↓
  the connector      ← the only part that knows Haier's field names
      ↓
   the brain         ← works out what actually happened
      ↓
  ┌───┴────────────────────┐
  ↓                        ↓
the messengers        the app
(Hue, speakers,       (window, settings)
 webhooks…)
```

The messengers and the app are **both** fed by the brain. The app isn't
downstream of the messengers — it's a separate consumer.

### The connector

Talks to Haier. Translates their field names into plain ones.

**This is the important boundary.** Haier's data is full of things like
`machMode`, `remoteCtrValid` and `prPhase`. Those names must not appear anywhere
else in the codebase. When Haier change something — and they will — this is the
only part that should need fixing.

### The brain

Turns "here's what the machine looks like now" into "here's what just happened".
Section 6 explains why that's harder than it sounds.

### The messengers

Anything that reacts. A Hue light, a Google Home speaker, a webhook. Section 8 is
the walkthrough for writing your own.

### The app

The window you look at, and the settings screens. It doesn't talk to Haier — it
asks the service. That way there's only ever one connection to Haier's servers,
and the app and the service can't disagree about what's happening.

---

## 5. What we know about Haier that nobody wrote down

All of this was measured on **one machine** — a Haier HD90-A2959R-UK tumble
dryer. It cost hours to work out. If you're extending Pastie, read it first.

### On the tested dryer, you can't start it remotely unless someone armed it

The machine reports a flag we call **"remote allowed"**. If it's off, any attempt
to start a cycle is refused — by the machine itself, not by us.

To turn it on, someone has to physically:

1. Switch the machine on, and
2. Turn the programme dial to the **remote** position

And here's the part that catches everyone: **it switches itself off again after
every completed cycle.** Once per load, someone walks to the machine.

Selecting a normal programme on the dial doesn't arm it — it actively *disarms*
it. When it is armed, the machine reports "no programme selected", which looks
broken but is correct: choosing the programme becomes Pastie's job.

**Whether other appliance types behave the same way is unknown.** Don't assume
it. The engineering rule that *is* universal is in section 12: Pastie never
bypasses or weakens a safety interlock an appliance exposes.

### "Accepted" doesn't mean "done"

When you send a command, you get a success response. That only means **Haier's
servers took the message**. It says nothing about whether the machine did
anything.

We proved this: a stop command returned success while the machine sat there
ignoring it. Section 7 turns this into an actual rule.

### The time remaining is a liar, at first

Early in a cycle the machine is still working out how wet the load is. During
that period the estimate jumps around and can go **up**. Later it settles and
counts down honestly, about a minute a minute.

There's a separate field for the **total** cycle length that stays put — use that
for a progress bar, not the estimate.

### What's proven, and what isn't

Haier's system covers sixteen appliance types — ovens, hobs, dishwashers,
fridges and so on. We own a dryer.

Guessing what a number means on a dryer wastes a load of washing. Guessing on an
oven or an induction hob is a different matter entirely.

---

## 6. Why "the dryer finished" is harder than it looks

The obvious approach — *if the machine says finished, announce it* — is wrong,
and gets it wrong in both directions.

**The false alarm.** Pastie starts up. The machine says "finished". Was that just
now, or three days ago? Announce it and you're shouting about a load that was put
away on Tuesday.

**The miss.** The dryer was running. The PC rebooted. While it was off, the cycle
finished. Pastie comes back and sees "finished" — a real completion, and it says
nothing.

So Pastie tracks four separate things:

```
what the machine sent us
        ↓
what state it's in now        (running, finished, faulted, unknown)
        ↓
what changed                  (it was running, now it's finished)
        ↓
what that means               ("the cycle finished")
```

**"Unknown" is a real state.** When Pastie starts, or loses its connection, it
doesn't know anything yet. The first thing it sees sets a baseline and announces
nothing. That kills the false alarm.

**Gaps get reported honestly.** If Pastie was off and something changed while it
wasn't looking, it says so rather than guessing:

> The dryer finished at some point while Pastie wasn't running.
> Last seen running at 20:10. Time of completion unknown.

If the machine has a cycle counter we can check, we can be more confident — a
counter that went up by one is decent evidence of exactly one completed cycle.
**Whether Haier expose such a counter is not yet known.** Somebody needs to look.

**Once announced, never re-announced.** Every alert is written down, so a restart
can't fire it twice.

**Nothing important is announced twice, but a light might flash twice.** If
Pastie crashes at exactly the wrong moment it may not have recorded that it
already flashed the light. We accept that. Anything sent to another system
carries a unique ID so the receiver can ignore a repeat if it cares.

---

## 7. Commands: how we know one actually worked

Because "accepted" doesn't mean "done", every command runs through the same
sequence:

```
requested  →  accepted by Haier  →  confirmed by the machine
                                 ↘  rejected | timed out | wrong state
```

Every command carries three things:

- **An ID**, so responses can be matched to requests
- **What state proves it worked** — for a start command, the machine going into
  "running"
- **A deadline** — how long to wait before calling it a failure

The user sees which of those happened:

```
Start requested          20:41:02
Accepted by Haier        20:41:03
Machine running          20:41:06   ✓
```

or

```
Accepted by Haier, but the machine didn't start within 20 seconds
```

Never report success off the back of the server response alone.

---

## 8. Adding a light, a speaker, or anything else

This is the bit most people will want. A "messenger" is anything Pastie can poke
when something happens.

Everything a messenger must be able to do:

| What | Why |
|---|---|
| **Describe its settings** | So the settings screen can draw itself. You don't write any interface code |
| **Find things** | List the lights, speakers or devices available |
| **Test** | Fire once on demand, so the user can check it works |
| **React** | Do the thing when an event happens |

Write one file, put it in the messengers folder, send a pull request. If it's
sensible it goes in the next release.

**Ideas that would be genuinely useful:** LIFX, WiZ and Nanoleaf lights (all
talk directly over your network, no accounts needed), phone notifications through
ntfy or Telegram, a plain Windows desktop notification, or a webhook so people
can wire it into anything at all.

### Rules for messengers

- **Don't assume every light does colour.** Plenty are white-only, and sending
  them a colour makes them fail. Check first, and pulse the brightness instead.
- **Put the light back how you found it — but only if it's still how you left
  it.** Save the state, do your thing, then check the light is still showing what
  you set before restoring. If it changed in the meantime, somebody turned it off
  or another automation touched it, and you must leave it alone. Restoring
  blindly overrides the user, which is maddening.
- **One alert at a time per target.** Two events firing at once must not both
  snapshot and both restore, or they'll trample each other.
- **Don't strobe.** Flashing lights can trigger seizures in people with
  photosensitive epilepsy. Philips's own developer terms make this the
  application's responsibility. Pastie caps flash rate and duration centrally,
  and no messenger may go round that.
- **A messenger failing must not take anything else down.** Run them with a
  timeout, isolated from each other. A speaker that's off shouldn't stop the
  light flashing.
- **Never write a password, key or token to a log.**

### If your messenger needs to serve a file

Google Cast is the awkward case, and it's worth spelling out because **the
prototype currently gets this wrong**.

A Chromecast or Google Home can't be handed audio directly — it needs a URL it
can fetch. So the prototype generates speech to an MP3 and runs a small web
server for the speaker to collect it from.

The prototype's version binds to **every network interface** and serves the
**whole speech cache directory**, with no authentication. It's only up for a few
seconds and only contains your own "the dryer's finished" recordings, so the
practical risk is small — but it's exactly what section 10 says not to do.

Any messenger that has to serve a file must:

- Serve **only that one file**, never a directory
- Use an unguessable URL, not a predictable filename
- Expire in seconds and shut down immediately afterwards
- Have no other endpoints — nothing that controls anything
- Bind as narrowly as the device allows

That's a very different thing from exposing Pastie's own interface, and the
distinction matters.

### Cast and speech are fragile

Two things worth knowing before relying on them:

- **The speech library is unofficial.** It uses an undocumented Google Translate
  endpoint and can break without warning. Its own project says so.
- **Finding Cast devices depends on multicast networking**, which needs the
  speaker on the same subnet and often fails when the calling program runs as a
  Windows service. The prototype works around this by connecting straight to a
  known address, and that workaround should stay.

---

## 9. Adding an appliance type

Haier's system covers sixteen kinds of appliance. Pastie has been tested on one.

Adding another means writing a description file listing what its numbers mean —
"machine mode 2 means running", "dryness level 14 means ready to wear", and so
on.

**Two different questions, which people confuse:**

```
Does Haier's data say this setting can be changed?
Have WE actually checked that we understand what changing it does?
```

Those are not the same, and the gap between them is a safety issue.

### Two levels of trust

| Unverified appliance type | Verified appliance type |
|---|---|
| Detect it, show its name and model | Everything on the left, plus: |
| Show raw values as diagnostics, labelled as raw | Proper state — running, finished, faulted |
| **No interpreted state** | Progress and time remaining |
| **No fault alerts** | Fault alerts |
| **No commands at all** | Commands that have been tested |

The key restriction is the one that's easy to get wrong: **an unverified
appliance gets no interpreted state and no fault alerts.** If a new oven reports
mode 6, Pastie has no business announcing "fault" just because that's what 6
means on a dryer. Show the raw number, say it's unverified, and leave the
interpretation to whoever owns one.

**Verification is per-mapping, not per-appliance.** You don't have to prove out
an entire oven before anything works. Confirm what "running" looks like and mark
that one mapping verified; the rest stays raw until someone gets to it.

If you have one of these appliances and are willing to test it properly, that's
one of the most useful contributions you could make.

---

## 10. Passwords and security

Other people will run this on their own machines, so this matters more than it
would for a personal script.

**Passwords don't go in files.** The prototype keeps your Haier login in a plain
text file. That's the one thing about the prototype that's genuinely wrong today.

**Credentials belong to the service, not to you.** They're encrypted using
Windows' own facilities under the Pastie service's identity. The desktop app
submits a new password over the secure channel and never reads or stores one
itself. This matters because the service and the logged-in user are different
accounts — a secret saved under your account wouldn't be readable by the service
at all.

Exactly which Windows mechanism to use is one of the experiments in section 14.

**The app and service talk over a private Windows channel**, not a web address.
A web page open in your browser can reach programs listening on your own PC — it's
a real attack, and it's why browsers are adding warnings about it. A private
channel can't be reached that way.

**One trap for whoever implements that channel:** if you create it without
explicitly saying who's allowed to use it, Windows gives *everyone* — including
anonymous users — read access by default. It has to be locked down deliberately.

**The service does not run as the all-powerful system account.** It doesn't need
that, and things that don't need power shouldn't have it.

**No unauthenticated network interfaces**, with the single narrow exception in
section 8 for handing a file to a Cast device.

**Reporting a security problem:** see [`SECURITY.md`](../SECURITY.md). Please
don't open a public issue for one.

---

## 11. Things that will break, and what to do about it

Pastie depends on an unofficial, community-maintained client for Haier's service.
This is not stable ground, and the design should assume it.

| What could happen | Has it happened? | What we do |
|---|---|---|
| Haier change how logging in works | **Yes — June 2026.** Everything broke until the client caught up | Keep all Haier-specific code in the connector, so it's one file to fix |
| The client gets abandoned | Not yet. It's a small team | Keep the connector boundary clean enough that it could be swapped out |
| A dependency update breaks something | Yes, twice | Pin exact versions. Test the packaged `.exe`, not just the code |
| The speech library breaks | Not yet, but it uses an undocumented endpoint | Isolate it; a failed announcement must not stop the light |
| Haier object to the project existing | The original project got a legal complaint before things were patched up | See below |

### Staying out of trouble

Being free and non-commercial does **not** make you legally untouchable. What
actually helps:

- Say clearly and prominently that this is unofficial and unaffiliated
- Don't use Haier's logos or branding, or anything implying they endorse it
- Respect the licences of the code we build on, and ship their notices
- Don't republish anything of Haier's — their assets, internal addresses, or keys
- Keep all of it isolated behind the connector, so it could be removed cleanly
- If this ever stops being a hobby, take proper advice first

### Shipping other people's code

The packaged `.exe` contains third-party libraries, and their licences require
their notices to travel with them. Ship a `THIRD_PARTY_NOTICES.txt` alongside it,
**generated from the actual pinned dependency list** rather than maintained by
hand — `pip-licenses` is in the dev dependencies for this.

Not everything is MIT. The Amazon networking components (`awscrt`, `awsiotsdk`)
are Apache-2.0, which asks for more than MIT does — attribution, a copy of the
licence, and any NOTICE file carried through. Generating the file rather than
writing it by hand is how you avoid getting that wrong.

### When something breaks, say so

Pastie should always be able to tell you which of these it is:

```
Working normally
Working, but updates are slow
Can't log in — check your password
Can't understand Haier's response — something changed, needs a fix
Can't reach the internet
```

"It's not working" is a useless error message. Each of those needs a different
response from the user.

---

## 12. Rules for contributions

- **The appliance must work without Pastie.** Never do anything that leaves
  someone's washing machine dependent on our software.
- **Pastie never bypasses or weakens a safety interlock an appliance exposes.**
  If a machine requires someone present, that's the design, not a bug. This is
  the universal rule; the specific arming behaviour in section 5 is a fact about
  one dryer.
- **Keep Haier's field names in the connector.** If `machMode` appears in the
  interface code, that's a rejected pull request.
- **A command isn't done until the machine says so.** Section 7.
- **Don't guess what a number means on hardware you don't own.**
- **Unverified appliance types get no interpreted state, no fault alerts and no
  commands.** Section 9.
- **No unauthenticated network interfaces**, except the narrow file-serving case
  in section 8.

---

## 13. What has to be tested

The dangerous bugs here are about timing and restarts, not about parsing. A build
isn't finished until automated tests cover all of these, using recorded
sequences rather than a live appliance:

```
starting up while the machine is idle
starting up while it's already finished        (must stay silent)
starting up and restarting mid-cycle
running → finished
running → fault
the same update arriving twice
updates arriving out of order
the connection dropping and coming back
credentials expiring mid-cycle
Haier accepting a command the machine then ignores
the periodic check disagreeing with the pushed update
the cycle finishing while Pastie is switched off
```

Tests check **what Pastie announced**, not what it parsed. These are also the
early-warning system for when a dependency update quietly changes behaviour.

**Recorded test data must be stripped by keeping only fields known to be safe** —
not by removing the bad ones one at a time. Haier's responses contain your
appliance's **GPS coordinates**, MAC address and serial number, and they can add
new fields whenever they like.

---

## 14. Before writing the real thing

Four things nobody knows the answer to, and each one changes the design.

1. **Does the appliance report a cycle counter?** Section 6's honest-gap handling
   depends on it.
2. **Does the push connection recover properly** after a long disconnection or
   after credentials expire?
3. **Can the existing Hue setup be reused**, or does everyone have to press the
   button on their bridge again? The old key may work as-is. Test it.
4. **Do the Haier libraries work when run as a Windows service?** They pull in
   Amazon networking components that are fussy about how they're started. This
   also settles exactly how credentials get stored.

After those four, build it in one go.

---

## 15. First jobs, roughly in order

| Job | Why it's high on the list |
|---|---|
| Get passwords out of the plain text file | The one thing that's genuinely wrong today |
| Fix the Cast file server | Section 8 — currently binds everywhere and serves a directory |
| Fault alerts | The machine reports faults and nobody's told. High value, small job |
| Move Hue to the current method | The old one stops working on new Philips firmware |
| Push updates | Removes up to two minutes of delay |
| Handle restarts properly | Stops false and missed alerts |
| A second appliance type | Proves the design actually generalises |

**Deliberately later:** energy and cost tracking, delayed starts for cheap-rate
electricity, maintenance reminders, and a phone-friendly web page. Cheap-rate
scheduling in particular is fiddlier than it looks once you account for arming,
clock changes and dropped connections.

---

## Appendix — where these facts came from

Everything in section 5 was measured against one real machine, a Haier
HD90-A2959R-UK tumble dryer, during the prototype work. It was not inferred or
looked up.

One observation is flagged as **unconfirmed**: the phase numbers this machine
reports appear to be the opposite way round from the community's shared mapping —
what everyone lists as "drying" behaves like the early sensing stage here, and
vice versa. That's from repeated cycles on one machine. If you have an HD90 and
see the same thing, please say so in an issue.

Dependency details were checked against their public listings on 2026-08-31.
