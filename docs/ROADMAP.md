# Roadmap

What's next, roughly in order. It's a hobby project: these are intentions, not
dates. Anything marked *help wanted* has an issue you can pick up.

## 0.3: the first public preview

The goal is narrow: the first version meant for someone who doesn't write Python.
No new appliance logic until it's out.

- [x] A Windows download: an installer and a zip, built and self-checked by CI
- [x] Windows notifications, so a PC and an appliance are all you need
- [x] A compatibility table, and a no-code route for appliance owners to report
      what their machine's numbers do
- [x] A first-run screen that gets you signed in to hOn
- [x] "Background watcher", not "service", in everything a user reads
- [x] `pip install pastie-hon`, published by the release workflow
- [x] Run the packaged build against a real hOn account
- [ ] Install it on a Windows PC with no Python or development tools
- [x] Tag `v0.3.0`: [released 2026-09-30](https://github.com/Ryan-Clinton/pastie-hon/releases/tag/v0.3.0), on PyPI as `pastie-hon`

## 0.3.1: from the first real users

- [x] Release notes that are short and readable, in UTF-8 (0.3.0's went up with
      broken characters)
- [x] **Export appliance report**: one safe file to attach instead of log lines
- [x] MAC addresses masked in the log
- [x] Product name and version in the .exe and installer metadata
- [ ] Apply to the SignPath Foundation for free code signing
      ([policy](CODE_SIGNING.md))
- [ ] The installer on a clean Windows PC: download, install, sign in, detect,
      notification test, sign out and in (does the watcher start?), uninstall
      (does anything stay behind?)
- [ ] 5-10 early testers who have never spoken to us, and whatever they find

## 0.4: more homes, more machines

**Appliance coverage is the priority, not features.** One verified model is
the product's biggest limit. Other Haier dryers ([#2](https://github.com/Ryan-Clinton/pastie-hon/issues/2))
are the cheapest wins, then washers, then Candy and Hoover.


- [ ] **The first verified washing machine.** A Haier HW100-BP14357 is arriving.
      Its profile is written and waiting on real cycles
      ([HANDOVER](HANDOVER.md))
- [ ] **ntfy**, natively, for phone notifications without a relay *(help wanted)*
- [ ] **LIFX and WiZ** lights: both talk over your own network, no accounts
      *(help wanted)*
- [ ] A washer-to-dryer hand-off, once the washer's finish is verified: "the
      wash is done, here's the dryer programme to match". Haier has nothing
      equivalent for this pair ([HANDOVER](HANDOVER.md))

## 1.0: something you can forget is there

- [ ] Updates without reinstalling
- [ ] More than one verified appliance family
- [ ] Settings that carry across versions with a tested migration
- [ ] Settle whether the service can run under its own Windows identity
      ([SPEC](SPEC.md) §14, experiment 4)
- [ ] The Microsoft Store (MSIX). The Store signs apps itself, which removes
      the SmartScreen warning entirely. Worth it once there's demand.
- [ ] A one-page website. Worth it once people are arriving from outside
      GitHub; until then the README is the landing page

## After launch, when it matters

- [ ] Use pushed MQTT deltas directly rather than as a nudge to re-read
      everything ([#8](https://github.com/Ryan-Clinton/pastie-hon/issues/8)).
      It would be quicker and lighter, but the full re-read works, and nobody
      is waiting on it.

## Not planned

- **More personality before more appliances.** The voice, the cast and the
  Departmental meters are the garnish. Compatibility and reliability are the
  meal. No new personality work until more models are verified.

Said out loud so nobody waits for it:

- **macOS or a Linux desktop app.** The service and domain layer run on Linux
  already (CI proves it), but the window and the credential store are Windows.
  A contribution would be welcome, but it isn't on this list.
- **Competing with Home Assistant.** If you run it, its hOn integration does far
  more than Pastie will.
- **Supporting all sixteen hOn appliance types from here.** They get verified by
  the people who own them. That's the design.
