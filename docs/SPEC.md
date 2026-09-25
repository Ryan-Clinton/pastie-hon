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

Status: **built, revision 7.** This document described a design; that design now
exists in `src/pastie`, and this revision marks what was built, what changed on
contact with reality, and what is still open. The four experiments in section 14
are what unblocked it — three answered, one still blocked on admin rights.

Where this document and the code disagree, the code is right and this is a bug.
Section 16 lists what actually got built.

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

### There's a statistics endpoint, separate from live state

Easy to miss, because it isn't in the appliance's live readings and has to be
asked for separately. It carries the cycle counter, the maintenance schedule and
usage history — see section 14. Worth knowing it exists before you go looking for
those things in the wrong place.

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

**There is a cycle counter, and we should use it.** The appliance reports
`programsCounter` in its statistics. If it went up by one while Pastie was off,
that's one completed cycle and we can say so plainly rather than hedging. If it
went up by more, say that instead. If it didn't move, nothing finished — whatever
the current state looks like.

That turns the honest-gap message from an apology into a fact:

> The dryer finished while Pastie wasn't running (one cycle, some time after
> 20:10).

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

## 14. The four experiments — results

These were run against the real dryer and the real Hue bridge on 2026-08-31.
Three are answered. One is blocked.

### 1. Does the appliance report a cycle counter? — **YES**

It's in a statistics endpoint we hadn't looked at, not in the live state:

```
statistics.programsCounter   3
statistics.mostUsedPrograms  [{programName: IOT_DRY_MIXED, count: 3, ...}]
```

Three completed cycles, with a fourth running at the time — matching the log.
That's consistent, though it wants one more observation to prove it increments
exactly once per cycle rather than per-programme-selection.

**This unblocks section 6.** A recovered completion can now be evidenced: if the
counter went up by one while Pastie was off, that's one cycle finished, and we
can say so with confidence instead of hedging.

**Same endpoint also gives us maintenance, for free:**

```
filterCleaning   {tot: 15,  count: 0, remaining: 15,  percentage: 0}
drumCleaning     {tot: 100, count: 0, remaining: 100, percentage: 0}
```

The machine reports **its own service schedule and how far through it is** —
filter every 15 cycles, drum every 100. Section 15 previously demoted maintenance
reminders because they'd need per-model knowledge nobody has. They don't. The
appliance tells us. That moves up the list.

### 2. Does MQTT push work? — **YES, connected and subscribed**

```
Lifecycle Connection Success
Subscribed: haier/things/<MAC>/event/appliancestatus/update
            haier/things/<MAC>/event/discovery/update
            $aws/events/presence/connected/<MAC>
            $aws/events/presence/disconnected/<MAC>
```

Three details from the negotiated session that **change the design**:

- **`session_expiry_interval_sec = 0`** — there is no session persistence. A
  reconnect replays *nothing*. So "full refresh after every reconnect" isn't a
  precaution, it's the only correct behaviour.
- **`maximum_qos = AT_LEAST_ONCE`** — duplicates are expected by design, not a
  fault. Deduplication is mandatory.
- **The presence topics are a gift.** We're told when the appliance goes offline
  and comes back, rather than having to infer it from silence.

Two API notes for whoever implements it: `subscribe_updates()` is **not** a
coroutine — don't await it — and it requires a callback argument.

**Not proven:** recovery after a long disconnection, and behaviour when
credentials expire mid-cycle. Both need hours of running rather than minutes. The
library's own release notes say a token-expiry reconnect bug was fixed in 0.19.1,
which is a reason to watch it rather than assume it.

**Also not observed:** an actual pushed message. The machine was idle for the
test, so there was nothing to send. Connection and subscription are proven;
delivery is not yet.

### 3. Can the existing Hue key be reused? — **YES**

```
GET https://<bridge>/clip/v2/resource/light
  no key                      → 403
  v1 username as
  hue-application-key header  → 200, 9 lights returned
```

Rooms, scenes and the event stream all return 200 with the same key.

**Nobody has to press the button on their bridge again.** The migration is
transport and code, not a re-pairing exercise — which removes the most annoying
part of the upgrade.

A bonus: v2 states outright whether a light supports colour, so the guesswork in
section 8 ("check before sending a colour") becomes a simple property read
instead of inferring it from the v1 state shape.

### 4. Do the Haier libraries work as a Windows service? — **BLOCKED**

Needs an elevated session; this one wasn't. Not answered, and **not to be assumed
either way.**

Partial evidence only: the prototype's notifier already runs as `SYSTEM` and
works — but it *polls*. It has never run MQTT in a service context, and MQTT is
what drags in the Amazon networking components that are fussy about how they're
started.

To finish it, from an elevated prompt: register a scheduled task running as the
service identity, have it connect MQTT and log the lifecycle events, and confirm
`Lifecycle Connection Success` appears. Until that's seen, treat service-mode
MQTT as unverified.

---

Verdict: **build can start.** The one open item only affects how the watcher is
hosted, not the shape of anything above it.

---

## 15. First jobs — what happened to them

| Job | Where it got to |
|---|---|
| Get passwords out of the plain text file | **Done.** DPAPI, under the service's identity: `service/secrets.py` |
| Fix the Cast file server | **Done.** One file, in memory, unguessable path, bound to the LAN address, gone when the announcement ends: `messengers/fileserve.py` |
| Fault alerts | **Done**, and only for verified appliance types |
| Move Hue to the current method | **Done.** v2, and the existing key still works, so nobody re-pairs |
| Push updates | **Done.** Connected and subscribed against the real appliance; an actual pushed message is still unobserved, because the machine was idle |
| Handle restarts properly | **Done.** Gaps are reported as gaps and keyed on the cycle counter |
| A second appliance type | **Not done**, and it needs somebody who owns one. Everything is in place for it: adding a type is a `Profile` in `connector/profiles.py` |
| Maintenance reminders | **Done**, and they were nearly free — the appliance reports its own service schedule |

**Deliberately still later:** energy and cost tracking, delayed starts for
cheap-rate electricity, and a phone-friendly web page. Cheap-rate scheduling in
particular is fiddlier than it looks once you account for arming, clock changes
and dropped connections.

---

## 16. What was built, and what it taught us

The design above survived contact with the code. Four things changed or were
learned in the building, and they are the parts worth knowing about.

**Verification is a property of a mapping, and it needed a home.** Section 9
said so; in the code it is `Profile.states_verified`, and the flag genuinely
does the work — an unverified appliance's state comes out as UNKNOWN, which the
tracker then declines to interpret, which means no alerts and no commands
without a single special case anywhere else.

**"Time remaining" needed a rule, not a field.** Section 5 says the estimate
lies early on. The rule the code uses is that a remaining time above the
programme's fixed total is still being guessed at, and is shown as "about 40 min
(still estimating)". Outside a running cycle there is no remaining time at all:
the machine reports the selected programme's nominal length there, and
presenting that as a countdown would put a number on something that is not
happening.

**The appliance's own name is usually its model number.** hOn hands back
"HD90-A2959R-UK" when nobody has renamed it, and "The HD90-A2959R-UK has
finished" is a worse sentence than "The tumble dryer has finished". The
connector substitutes the profile's label when the two match.

**Two bugs were found by running it rather than by reading it**, which is the
argument for section 13's insistence on recorded sequences having limits:

- The settings document was cached after its first read, so a change made in the
  app would not have applied until a restart.
- The client's HTTP session was left open on disconnect, leaking one per
  reconnect. It showed up as "Unclosed client session" the first time the
  service was stopped.

**Still unproven, and honestly so:** an actual pushed MQTT message (the machine
was idle throughout), recovery after a long disconnection, behaviour when
credentials expire mid-cycle, and the Windows service question from experiment
4. All four need hours of running rather than minutes.

---

## 17. The delight contract

> **Status: proposed, not yet built.** Sections 17-20 came from the first design
> audit of the window (2026-09-25). They describe how Pastie should speak;
> [UI-SPEC.md](UI-SPEC.md) is the plan for building it. Until it is built, the
> code is right where the two disagree, as for the rest of this document.

Pastie should have a personality, but the personality must never be allowed to
change a fact, hide a control, delay an action, or make a serious situation less
clear.

The premise is simple: **Pastie behaves like a tiny, excessively conscientious
office whose entire remit is liaison between people and domestic machinery.** It
takes this job completely seriously. The appliances, cloud services and network
connections provide all the absurdity required.

This is deliberately not a sarcastic assistant and not a comedy character that
happens to know whether the dryer is running. Pastie is useful first. The humour
comes from calm, precise descriptions of things that are already slightly
ridiculous: a server accepting a command that the machine ignores, a dryer that
changes its mind about the remaining time, or a remote-control system that first
requires somebody to walk over to the machine.

**Pastie itself is the competent operative, not an abstract institution.** It
is the working employee of the **Domestic Appliance Liaison Division** of PASTIE,
the *Practical Appliance Supervision, Telemetry & Interoperability Executive*.
About admits that the acronym was developed considerably later than the name.
The institution exists only to give the departmental language somewhere to come
from. It is not lore to be expanded for its own sake.

**Pastie is the controller, and the rest of the house is its cast.** Every
appliance, and the humans (the Household), has a personality that Pastie
negotiates with. Pastie is the only narrator: the others appear only as reported
speech and reported positions ("The dryer currently believes 47 minutes
remain"), which also keeps every fact attributed to its source. A personality
is written from an appliance's observed behaviour, only once its type is
verified. **Every personality, and how Pastie deals with each one, is
configurable by the owner**: names, temperaments, Pastie's stance, lines and
meters. The limits in [UI-SPEC.md](UI-SPEC.md) §7.9 apply: no configuration can
change a fact, soften a warning, error or safety message, or earn the
thumbs-up. The Household are the principals Pastie works for, and never the
punchline. Pastie is a whole-house controller: a washer is expected, a smart projector is on its
way, and other sources, such as solar panels, may follow. [UI-SPEC.md](UI-SPEC.md) §7.3 holds
the cast.

The mascot artwork (a battered pastie in a gold shield, giving a thumbs-up) is
warm, heroic and rather cute. The voice is dry, officious and restrained. **That
mismatch is kept on purpose.** Pastie looks as if it ought to say "Yay! Your
laundry is finished!", and instead says "Tumble dryer finished. Its part of the
arrangement is complete."

### Pastie's laws: the five administrative principles

These are design principles for anybody contributing. They aren't necessarily
shown to users.

1. **Pastie does not claim to know what it does not know.**
2. **A cloud service's opinion is not evidence that an appliance complied.**
3. **The user should never suffer for the sake of a joke.**
4. **Routine competence deserves less attention than exceptional information.**
5. **When machinery behaves absurdly, accurate description is usually
   sufficient comedy.**

A corollary for the mascot: **Pastie never gives the thumbs-up unless Pastie
knows.** The confirmed pose appears only on machine-confirmed state.

### Voice rules

1. **Fact first; wit second.** The first sentence must remain useful if the second
   sentence is removed.
2. **Pastie is on the user's side.** The user is never the punchline. Neither are
   accessibility needs, mistakes, forgotten maintenance or failed commands.
3. **Precision is funnier than wackiness.** Prefer an unnecessarily exact account
   of what happened over a random joke.
4. **Never manufacture friction for comedy.** Pastie may describe bureaucracy; it
   must never create bureaucracy.
5. **Do not joke over danger.** Appliance faults, safety interlocks, credential
   problems and anything requiring immediate action use plain language.
6. **Do not borrow somebody else's catchphrases.** No Hitchhiker quotations,
   towels, 42s, depressed robots or "don't panic" jokes. The voice has to become
   recognisably Pastie's own.
7. **A joke earns its place by explaining the system, rewarding attention or
   making repetition nicer.** If it only demonstrates that the writer can make a
   joke, cut it.
8. **Restraint is part of the voice.** One good aside on a screen is better than
   five competing for attention.

### Personality level

Personality is user-selectable:

| Setting | Behaviour |
|---|---|
| **Plain** | Facts only. No asides, jokes or playful labels. |
| **Dry** | Occasional short deadpan asides. Recommended default. |
| **Departmental** | Full Pastie voice: official-sounding headings, richer asides and callbacks. |

Changing this setting changes presentation only. It never changes event
detection, command behaviour, severity, logging or the factual part of a
message.

Serious fault and safety messages ignore the personality setting and remain
plain in every mode.

---

## 18. The copy architecture

Comedy text must not be scattered through the event engine. The brain emits a
canonical fact. The presentation layer may decorate that fact.

Conceptually, an event presented to a person has:

```
headline        required, factual, short
fact            required, canonical description of what happened
next_action     optional, factual instruction
aside_key       optional, identifies an authored pool of personality lines
severity        info | maintenance | warning | error | safety
```

The event log stores the canonical facts, not whichever joke happened to be
shown on screen. A redraw must not produce a different interpretation of the
same event.

If an `aside_key` has several variants, choose one deterministically for the
event ID and remember it. The same event therefore does not visibly rewrite
itself every time the app refreshes. A later event may get a different variant.

All personality copy is authored and shipped with Pastie. Runtime-generated copy
must not be used for appliance state, faults, commands or instructions. A utility
that controls real hardware should not improvise its meaning.

### Repetition rules

Routine state should become quieter, not louder, with repetition. The first
interesting occurrence may get an aside; repeated occurrences use the factual
line unless there is genuinely new context.

A notification should normally contain one fact and, at most, one short aside.
The desktop app can afford longer optional text because the user has chosen to
open it.

---

## 19. Where the personality lives

### The home screen

The main card stays operationally boring in the best possible way:

```
Tumble dryer                         RUNNING
Mixed / Ready to wear
About 47 min remaining               54%

Still estimating. The dryer currently believes 47 minutes remain. Pastie has
elected not to contradict it.
```

The status, programme, time and progress are the product. The last line is the
personality.

When the estimate has settled, the aside disappears rather than inventing
something else to say.

### Remote control not armed

Factual message:

> Remote start is unavailable. Turn the programme dial to Remote on the dryer
> first.

Optional Dry/Departmental aside:

> The remote-control procedure currently contains a mandatory visit to the
> dryer.

The disabled button should say **Waiting for Remote mode**, not something jokey.
Controls stay literal.

### Commands get a paper trail

The existing requested -> accepted -> confirmed sequence should become one of
Pastie's signature interactions. Present it like a tiny case file:

```
START CYCLE
20:41:02  Requested
20:41:03  Haier accepted the request
20:41:06  Dryer confirmed RUNNING                    CONFIRMED
```

Optional aside after confirmation:

> Three separate parties have now agreed that the dryer is on.

If confirmation fails, no punchline:

> Haier accepted the request, but the dryer did not start within 20 seconds.
> Nothing has been reported as successful.

### Time remaining

Pastie should expose the difference between **machine estimate** and **confidence
in that estimate** rather than pretending the early number is trustworthy.

Suggested labels:

```
About 52 min        still estimating
47 min              settled
```

Optional early-cycle asides can refer to the estimate changing its mind, but the
numeric value and confidence label are always unambiguous.

### Unknown really means unknown

Unknown and unverified states are an opportunity for the voice precisely because
Pastie already refuses to guess.

```
State unknown
Pastie has data, but no verified mapping for what this appliance means by it.
```

Departmental aside:

> Inventing an answer would be quicker. It would also be an answer Pastie made
> up.

### Gaps and restarts

Recovered events should feel like a useful incident report rather than an
apology:

```
1 cycle completed while Pastie was offline
Last seen running: 20:10
Completion time: not known
```

If the cycle counter proves what happened, say so. If it does not, preserve the
uncertainty. Personality may comment on the gap only after the facts are clear.

### Maintenance

Maintenance is low-stakes and recurring, which makes it ideal for restrained
personality:

```
Filter clean due in 2 cycles
Reported by the appliance: 13 of 15 cycles used
```

Departmental aside:

> The dryer has begun keeping records. This seems only fair, given what Pastie
> does for a living.

Never turn maintenance into guilt or a streak that can be "lost". The point is
to help, not to gamify chores.

### Finished notifications

The factual sentence is stable:

> Tumble dryer finished.

Optional variants may follow it in Dry or Departmental mode, for example:

> Its part of the arrangement is complete.

or:

> The machine is finished. The clothes have been transferred to your department.

Speech notifications should use fewer variants than the desktop app. Spoken
jokes become irritating much faster than written ones.

### Connectivity

Connectivity messages identify the layer that failed:

```
Dryer offline
Last update: 12:17
Haier login: OK
Internet connection: OK
```

A restrained aside is acceptable for an ordinary offline state. Authentication
failure, corrupt/unrecognised responses and repeated connection failures stay
plain because the user may need to act.

### Diagnostics: "what we know"

The diagnostics screen should make the project's epistemology visible:

```
WHAT PASTIE KNOWS
  Dryer online                       verified
  Cycle running                      verified
  Programme: Mixed                   verified
  Remaining time: 43 min             reported by appliance

WHAT PASTIE IS INFERRING
  Remaining-time estimate settled    yes

WHAT PASTIE WILL NOT GUESS
  Unknown raw state 6                no verified mapping
```

This is useful to contributors and is also one of the most natural places for the
project's personality.

### Event history: the case file

Call the ordinary screen **History**. In Departmental mode its subtitle may be
**Case file**.

Events should read like compact evidence:

```
18:02  Cycle started                  confirmed by dryer
18:31  Remaining time changed 41 -> 47 min
19:16  Cycle finished                 cycle counter 104 -> 105
19:16  Hue kitchen light notified     delivered
19:16  Kitchen speaker announcement   timed out
```

This makes the architecture understandable without an architecture diagram.

### Onboarding

Onboarding should prove the useful path quickly:

```
1. Connect Haier account
2. Find appliances
3. Choose how Pastie tells you things
4. Test one messenger
```

Personality belongs in the supporting text, not in the buttons or required
instructions. The final test should create a real, visible success so the user
understands the chain from appliance event to messenger.

### Settings

Settings can carry small bits of personality because the user is browsing rather
than reacting to an event. Good candidates are section subtitles, empty states
and test-result messages.

Do not rename standard concepts beyond recognition. "Notifications" should still
be called Notifications; "Faffing Department" is funny once and annoying every
time somebody needs to find a setting.

### About and release notes

These are safe places to turn the dial up.

The About screen can present the real architecture as an unnecessarily formal
organisation chart:

```
PASTIE
Domestic Appliance Liaison

Connector        translates what Haier said
Brain            decides what actually happened
Messengers       bother something else about it
App              tells you what everybody is doing
```

Release notes may be headed **Minutes of recent proceedings** in Departmental
mode, but the version number and actual changes remain ordinary text.

---

## 20. Delight that is earned rather than sprayed everywhere

The best surprises should come from state Pastie genuinely knows, not random
one-liners.

A few examples worth building later:

- A small acknowledgement on the 50th or 100th observed completed cycle, based on
  the real cycle counter. No points, streaks or rewards; just recognition that
  the software has history with the appliance.
- A first-time note when Pastie successfully reconstructs a completion that
  happened while it was offline. This is a genuinely clever capability and is
  worth celebrating once.
- Contextual copy the first time an ETA increases instead of decreases. The joke
  explains a real behaviour the user would otherwise think was a bug.
- A hidden but discoverable **What Pastie refuses to guess** diagnostics page for
  raw/unverified mappings.
- Small visual stamps such as `CONFIRMED` on command completion and `RECOVERED`
  on evidenced gap events. They should be accessible text as well as decoration.

Avoid generic achievements such as opening the app ten times, using it at 3am,
or completing seven loads in a week. Those reward use of Pastie rather than
understanding the machinery, and quickly become noise.

### Tests for the delight layer

The personality system is not finished until automated tests prove:

```
Plain, Dry and Departmental modes expose the same canonical facts
safety events contain no personality aside
no command is called successful before machine confirmation
a repeated render keeps the same aside for the same event ID
logs contain canonical facts rather than personality text
an unknown/unverified state never gains an interpreted joke-description
notifications still make sense when the aside is removed
```

The final editorial test is simpler: **if Pastie stopped being funny, would it
still be an unusually clear appliance utility?** If the answer is no, the joke is
carrying information it should not be carrying.

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
