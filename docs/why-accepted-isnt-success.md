# "Accepted" isn't success

*A short write-up of one of the design problems in Pastie. The full design is in
[SPEC.md](SPEC.md) §7; the code is
[`core/commands.py`](../src/pastie/core/commands.py).*

When you send a Haier appliance a command through hOn, the reply comes back
*success* as soon as Haier's servers have taken the message. It says nothing
about whether the machine did anything.

We know because we measured it, twice, on a Haier HD90-A2959R-UK dryer:

- **A stop command returned success while the dryer carried on running.**
- **Start "Duvet" returned success three times running, and the machine sent
  back nothing at all**: no change of mode, no pushed update. Starting
  Delicates in the same session worked at once. The reason, worked out
  afterwards: the app's "Duvet" is a recipe pointing at a programme this model
  doesn't have. The machine's own Duvet programme started immediately when
  sent directly. ([`connector/profiles.py`](../src/pastie/connector/profiles.py)
  records the whole observation.)

If a program reports the server's answer as the result, both of those show up
as "done". Somebody walks away believing the dryer is stopped, or started.

## Three parts to every command

In Pastie, a command is not a request and a reply. It's a small tracked object
with:

- **an id**, so a later reading can be matched to the request that expected it
- **a state that would prove it worked**: for a start, the machine going into
  *running*; for a stop, the machine leaving it
- **a deadline**, after which it has failed, whatever the server said

The user is shown which of those actually happened:

```
Start requested         20:41:02
Accepted by Haier       20:41:03
Machine confirmed       20:41:06   OK
```

or, when the machine never reacts:

```
Accepted by Haier, but the machine didn't react within 20 seconds
```

Nothing in Pastie reports success off the back of a server response. The
confirmation comes from a *reading*, the same way every other fact does.

## Refusing before sending

Some commands can be known to fail before they're sent. The tested dryer
refuses remote start unless somebody has armed it at the machine, and it disarms
itself after every cycle. Pastie reads that flag and says "arm it at the
machine first" rather than sending a command it knows will be ignored. It never
tries to work round the interlock: where an appliance requires somebody present,
that is the design.

Watch the ignored stop being caught:

```
pastie demo ignored
```
