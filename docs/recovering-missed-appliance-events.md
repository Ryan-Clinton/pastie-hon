# How do you know the dryer finished while your program wasn't running?

*A short write-up of one of the design problems in Pastie. The full design is in
[SPEC.md](SPEC.md) §6; the code is
[`core/tracker.py`](../src/pastie/core/tracker.py).*

The obvious way to announce "the dryer has finished" is to watch for the machine
saying *finished* and announce it. That's wrong in both directions.

- **The false alarm.** Pastie starts and the dryer says *finished*. Was that just
  now, or on Tuesday? Announce it, and you're shouting about a load somebody put
  away days ago.
- **The miss.** The dryer is running and the PC reboots. The cycle ends while
  nothing is watching. When Pastie comes back it sees *finished*: a real
  completion that nobody was told about.

A single rule, "the state changed to finished", can't fix both at once. Pastie
keeps four things apart instead:

```
what the machine sent        ->  a snapshot
what state it is in now      ->  running, finished, faulted... or unknown
what changed since last time ->  compared with what was remembered
what that means              ->  an event, or nothing
```

## Unknown is a real state

At startup, and after any dropped connection, Pastie doesn't know what the
machine is doing. The first reading of a session sets a **baseline** and
announces nothing. That removes the false alarm: a *finished* seen at startup is
not news.

## A gap is reported as a gap

Pastie remembers the last thing it saw, on disk. If the baseline differs from
that memory, something happened while nobody was watching, and Pastie says so,
in those words:

> The tumble dryer finished while Pastie wasn't running (one cycle, some time
> after 20:10).

## The counter turns an apology into a fact

That sentence can say *one cycle* because the appliance keeps a count of
completed programmes. It isn't in the live readings; it's in a separate
statistics endpoint that has to be asked for. If the counter moved by one, one
cycle completed. If it didn't move, nothing completed, whatever the state looks
like. That also tells a finished cycle apart from one somebody cancelled. When
there's no counter, Pastie says the vaguer, truthful thing instead.

## Once announced, never announced again

Every event has a **key** built from the appliance's own facts: its hashed id,
what happened, and the counter value. The key is written to a ledger *before*
the event goes out, and an event whose key is already there is dropped. A
restart therefore can't announce the same completion twice, whether it was
announced live or recovered from the counter afterwards: both produce the same
key.

The price of that ordering is deliberate. If Pastie dies between recording and
acting, a light might not flash. If it recorded after acting, a light might flash
twice. Pastie records first, and every delivery carries a unique id so a
receiver that cares can drop a repeat.

## Testing it without a dryer

None of this needs an appliance to test. The tracker is plain Python with no
network and no Windows, so restarts, duplicates, stale readings and gaps are
replayed from recorded sequences. You can watch one:

```
pastie demo gap
```
