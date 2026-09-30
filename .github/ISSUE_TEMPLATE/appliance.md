---
name: I have another Haier appliance
about: Help make an appliance type verified
labels: appliance-support
---

This is the most useful contribution anyone can make, and it needs no
programming. Haier, Candy and Hoover appliances on hOn are all welcome.

**What appliance is it?** Brand, type and model.

**What does Pastie show now?** The window's Diagnostics, or `pastie-cli status`
from the download's folder (`pastie status` from source). It should detect and
name the appliance and show raw values without interpreting them.

**What changed during a cycle?** Run one normal cycle, then export an
appliance report: About → Diagnostics → **Export appliance report** in the
window, or `pastie report -o report.txt`. Attach the file here. It holds no
ids, serial numbers, MAC addresses or location. Then say what you were doing at
the times it lists: "started it at 20:05", "opened the door at 21:40".

(On 0.3.0 there's no export yet: quote the lines Pastie writes to its log as
values change, and `pastie where` shows where the log is.)

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
