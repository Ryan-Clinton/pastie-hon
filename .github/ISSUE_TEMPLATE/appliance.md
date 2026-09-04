---
name: I have another Haier appliance
about: Help make an appliance type verified
labels: appliance-support
---

This is the most useful contribution anyone can make, and it does not need any
code to start.

**What appliance is it?** Type and model.

**What does Pastie show now?** `pastie status` — it should detect and name it,
and show raw values without interpreting them.

**Which raw values have you actually confirmed?**

The thing that turns "raw numbers" into a working appliance is somebody who owns
one watching what the numbers do. For example:

- What is `machMode` while it is running? While it is finished? Idle?
- Does anything look like a cycle counter in the statistics?

**Please don't guess.** An unconfirmed mapping is worse than none: it means
Pastie announcing a fault on your oven because 6 means fault on somebody's
dryer. Say what you watched happen, and say what you have not checked.

> ⚠️ Do not paste a raw appliance dump — it contains GPS coordinates, a MAC
> address and a serial number. Quote the individual fields.
