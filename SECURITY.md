# Reporting a security problem

**Please don't open a public issue for a security vulnerability.**

Even a vague one — "I think there's an authentication problem" — tells anyone
watching that there's something worth digging into, before there's a fix.

## How to report one

Use GitHub's private reporting: go to the **Security** tab on this repository and
choose **Report a vulnerability**. It stays private between you and the
maintainers while it's being sorted out.

Helpful to include, as far as you can:

- What the problem is and what someone could do with it
- Steps to reproduce it
- Which version or commit you found it on

**Please don't include** passwords, tokens, appliance dumps, or anything else
personal. A description is enough. If you need to demonstrate something with
real data, say so and we'll work out a safe way.

## What happens next

This is a hobby project maintained in people's spare time, so there's no
guaranteed response time. Realistically you'll hear back within a week or two.
If it's a genuine problem it gets fixed and credited to you, unless you'd rather
stay anonymous.

## What counts

Worth reporting:

- Anything that exposes credentials — the Haier login, the Hue bridge key,
  anything from the Windows credential store
- Anything that lets another program or another machine on the network control an
  appliance, or reach Pastie's internal interface
- Anything that lets a web page in a browser reach Pastie
- A file server left open wider or longer than it should be

Probably not worth reporting:

- The fact that Pastie talks to Haier's cloud. It has to; there's no local
  alternative on these appliances.
- The fact that it uses an unofficial client. That's documented and deliberate.
- Something in `pyhon-revived`, PyChromecast or another dependency — report those
  to the projects themselves, though do tell us so we can pin around it.

## One thing worth knowing

The data Haier's API returns about your appliance includes its **GPS
coordinates**, MAC address and serial number. `discover.py` writes that to
`dump/`, which is gitignored for exactly that reason.

If you're sharing output for a bug report, strip it first — and strip it by
keeping only the fields you know are safe, not by deleting the ones you spot.
