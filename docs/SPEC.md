# Pastie — how it works and how to extend it

Pastie tells you what your Haier appliance is doing and lets you do something
about it — flash a light, announce it on a speaker, start a cycle from your desk.

This document explains how the thing is put together, what we already know about
Haier's system that isn't written down anywhere else, and how to add your own
lights, speakers and appliances to it.

**This is a hobby project.** It's free, it's MIT licensed, nobody is being paid,
and there are no guarantees. It's also unofficial — Haier have nothing to do with
it and don't know it exists.

Status: **design, revision 4.** A working prototype exists. The full version
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
- Start a cycle without walking to the machine
- Tell you when something's gone wrong, loudly

The phone app already sends you a notification when a cycle ends. Pastie's point
isn't notification — it's **doing something across your other kit**.

## 2. What Pastie is not

- **Not a replacement for Home Assistant.** If you already run Home Assistant, it
  does far more than this ever will. Pastie is for people who want appliance
  control without installing a whole home-automation platform.
- **Not a way round safety features.** The machine won't let you start it
  remotely unless someone has armed it at the panel. We don't try to defeat that,
  and we won't accept changes that do.
- **Not official.** It works by imitating Haier's own app. Haier could change
  something tomorrow and break it.
- **Not for sale.** Fun, not profit.

---

## 3. Decisions already made

These are settled. If you disagree, open an issue before writing code, because a
pull request that assumes otherwise won't merge.

| Decision | Why |
|---|---|
| **Pastie runs on its own.** Home Assistant is optional | Requiring people to install a home-automation platform to get a light to flash is too much to ask |
| **Windows only, for now** | It's what it's built and tested on. Someone can port it later |
| **The watcher runs as a Windows service** | The whole point is being told the dryer's finished when you're *not* at the PC. A program that only runs while you're logged in misses that |
| **Contributions go in the main codebase**, not separate plugin packages | The packaged `.exe` can only include code that existed when it was built, so separate plugins wouldn't work in the version most people download. Send a pull request instead |
| **MIT licence** | Do what you like with it |
| **We use `pyhon-revived`** to talk to Haier | It's the maintained version. The older `pyhOn` is behind and missing an important authentication fix |

---

## 4. How it fits together

Four parts. Each one only talks to its neighbours.

```
Haier's servers
      ↓
  the connector          ← the only part that knows Haier's field names
      ↓
   the brain             ← works out what actually happened
      ↓
  the messengers         ← Hue, Google Home, webhooks, whatever you add
      ↓
     the app             ← what you look at
```

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

All of this came from poking a real machine. It cost hours to work out. If you're
extending Pastie, read it first.

### You can't start it remotely unless someone armed it

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

This means **remote start can never be unattended**, on any system — ours,
Haier's own app, or Google Assistant. Don't promise otherwise in the interface.

### "Accepted" doesn't mean "done"

When you send a command, you get a success response. That only means **Haier's
servers took the message**. It says nothing about whether the machine did
anything.

We proved this: a stop command returned success while the machine sat there
ignoring it.

So every command has to be checked by watching the machine's state actually
change. Never report success off the back of the response alone.

### The time remaining is a liar, at first

Early in a cycle the machine is still working out how wet the load is. During
that period the estimate jumps around and can go **up**. Later it settles and
counts down honestly, about a minute a minute.

There's a separate field for the **total** cycle length that stays put — use that
for a progress bar, not the estimate.

### What's proven, and what isn't

Everything above was measured on **one tumble dryer**. Haier's system covers
sixteen appliance types — ovens, hobs, dishwashers, fridges and so on. We own a
dryer.

So: **don't assume any of this applies to other appliances.** Especially the
arming rule. If an oven turns out not to need arming, that's remote start with
nobody in the room, and the safety story is completely different.

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
already flashed the light. We accept that. A light flashing twice is not a
problem worth engineering away. Anything sent to another system carries a unique
ID so the receiver can ignore a repeat if it cares.

---

## 7. Talking to it faster

The prototype asks Haier "what's happening?" every two minutes. That means alerts
can be two minutes late.

Haier's system can also **push** updates the moment something changes, using
their messaging system. The library we use supports it.

**The plan: use push as the main route, and keep asking periodically as a
backstop.** Push connections drop, duplicate messages, deliver them out of order,
and go quiet without saying so. Never trust push alone.

Rules:

- After any reconnection, ask for the full picture again. Don't assume you didn't
  miss anything.
- Wait longer between retries each time a connection fails, so we're not
  hammering Haier's servers during an outage.
- If the periodic check disagrees with what push told us, **that's worth
  logging** — it's the main clue that push has gone quiet.
- Show the user when Pastie is degraded. Silently falling back to slow checking is
  how a two-minute delay becomes invisible.

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
- **Put the light back how you found it.** Save its state, do your thing, restore
  it. Nobody wants their lamp stuck green at midnight.
- **Don't strobe.** Flashing lights can trigger seizures in people with
  photosensitive epilepsy. Philips's own developer terms make this the
  application's responsibility. Pastie caps how fast and how long anything can
  flash, centrally, and no messenger may go round that.
- **Never write a password, key or token to a log.**

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

So an appliance type nobody has verified gets:

- **Reading: yes.** Show its state, show its progress, alert on faults.
- **Writing: no.** Commands are disabled until someone with that appliance has
  tested them.

Guessing what a number means on a dryer wastes a load of washing. Guessing on an
oven or an induction hob is a different matter entirely. If you have one of these
appliances and are willing to test it properly, that's one of the most useful
contributions you could make.

---

## 10. Passwords and security

Other people will run this on their own machines, so this matters more than it
would for a personal script.

**Passwords don't go in files.** The prototype keeps your Haier login in a plain
text file. The real version puts it in Windows' own password store, which is
encrypted and tied to your account.

**The window never touches the password store.** You type your password into the
app; the app hands it to the background service; the service saves it. That way
the two parts can run as different users without a problem.

**The app and service talk over a private Windows channel**, not a web address.
A web page open in your browser can reach programs listening on your own PC — it's
a real attack, and it's why browsers are adding warnings about it. A private
channel can't be reached that way at all.

**One trap for whoever implements that channel:** if you create it without
explicitly saying who's allowed to use it, Windows gives *everyone* — including
anonymous users — read access by default. It has to be locked down deliberately.

**The service does not run as the all-powerful system account.** It doesn't need
that, and things that don't need power shouldn't have it.

---

## 11. Things that will break, and what to do about it

Pastie depends on a reverse-engineered library that imitates Haier's app. This is
not stable ground, and the design should assume it.

| What could happen | Has it happened? | What we do |
|---|---|---|
| Haier change how logging in works | **Yes — June 2026.** Everything broke until the library caught up | Keep all Haier-specific code in the connector, so it's one file to fix |
| The library gets abandoned | Not yet. It's a small team | Keep the connector boundary clean enough that it could be swapped out |
| A library update breaks something | Yes, twice | Pin exact versions. Test the packaged `.exe`, not just the code |
| Haier object to the project existing | The original project got a legal complaint before things were patched up | See below |

### Staying out of trouble

Being free and non-commercial does **not** make you legally untouchable, and the
spec previously implied otherwise. What actually helps:

- Say clearly and prominently that this is unofficial and unaffiliated
- Don't use Haier's logos or branding, or anything implying they endorse it
- Respect the licences of the code we build on
- Don't republish anything of Haier's — their assets, their internal addresses,
  their keys
- Keep all of it isolated behind the connector, so it could be removed cleanly
- If this ever stops being a hobby, take proper advice first

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
- **Never work around a safety interlock.** If the machine won't do something
  without someone present, that's the design, not a bug.
- **Keep Haier's field names in the connector.** If `machMode` appears in the
  interface code, that's a rejected pull request.
- **A command isn't done until the machine says so.** Don't report success off a
  server response.
- **Don't guess what a number means on hardware you don't own.**
- **No unprotected network interfaces.** Nothing that listens for connections
  without checking who's asking.
- **New appliance types start read-only** until someone verifies them.

---

## 13. Before writing the real thing

Four things nobody knows the answer to, and each one changes the design. They're
quick to check and worth checking first.

1. **Does the appliance report a cycle counter?** Section 6's honest-gap handling
   depends on it. Without one, "it finished while you were out" can only ever be
   informational.
2. **Does the push connection recover properly** after being disconnected for a
   long time, or after credentials expire?
3. **Can the existing Hue setup be reused**, or does everyone have to press the
   button on their bridge again? The old key may work as-is. Test it.
4. **Do the Haier libraries work when run as a Windows service?** They pull in
   Amazon networking components that are fussy about how they're started.

After those four, build it in one go.

---

## 14. First jobs, roughly in order

| Job | Why it's high on the list |
|---|---|
| Get passwords out of the plain text file | It's the one thing that's genuinely wrong today |
| Fault alerts | The machine reports faults and currently nobody's told. High value, small job |
| Move Hue to the current method | The old one stops working on new Philips firmware |
| Push updates | Removes up to two minutes of delay |
| Handle restarts properly | Stops false and missed alerts |
| A second appliance type | Proves the design actually generalises |

**Deliberately later:** energy and cost tracking, delayed starts for cheap-rate
electricity, maintenance reminders, and a phone-friendly web page. All nice; none
urgent. Cheap-rate scheduling in particular is fiddlier than it looks once you
account for arming, clock changes and dropped connections.

---

## Appendix — where these facts came from

Everything in section 5 was measured against one real machine, a Haier
HD90-A2959R-UK tumble dryer, during the prototype work. It was not inferred or
looked up.

One observation is flagged as **unconfirmed**: the phase numbers this machine
reports appear to be the opposite way round from the community's shared mapping —
what everyone lists as "drying" behaves like the early sensing stage here, and
vice versa. That's from repeated cycles on one machine. If you have an HD90 and
see the same thing, please say so in an issue; that's how it gets confirmed or
corrected.

The library details were checked directly against its public listing on
2026-08-31.
