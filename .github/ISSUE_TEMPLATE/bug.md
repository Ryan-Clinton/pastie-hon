---
name: Something is wrong
about: Pastie did something it shouldn't, or didn't do something it should
labels: bug
---

**What happened, and what you expected instead**


**Which of these does Pastie say it is?**

`pastie status` prints one of: working normally / working but updates are slow /
can't log in / can't understand Haier's response / can't reach the internet.
Which one matters — they need completely different fixes.


**Your appliance**

- Type and model:
- Does Pastie call it verified or unverified? (`pastie status` says)

**Version**

`pastie --version`, and Windows version.

**Anything from the log**

`pastie where` says where the log is.

> ⚠️ **Before pasting anything from a dump or a raw reading**: Haier's responses
> contain your appliance's **GPS coordinates**, MAC address and serial number.
> The log does not, but a raw API dump does. If in doubt, don't paste it — say
> what you saw instead, and we'll ask for exactly the field.
