# Roadmap

What's next, roughly in order. It's a hobby project: these are intentions, not
dates. Anything marked *help wanted* has an issue you can pick up.

## 0.3: the first release

- [x] A Windows download: an installer and a zip, built and self-checked by CI
- [x] Windows notifications, so a PC and an appliance are all you need
- [x] A compatibility table, and a no-code route for appliance owners to report
      what their machine's numbers do
- [ ] Tag `v0.3.0` and publish the GitHub Release

## 0.4: more homes, more machines

- [ ] **The first verified washing machine.** A Haier HW100-BP14357 is arriving.
      Its profile is written and waiting on real cycles
      ([HANDOVER](HANDOVER.md))
- [ ] **ntfy**, natively, for phone notifications without a relay *(help wanted)*
- [ ] **LIFX and WiZ** lights: both talk over your own network, no accounts
      *(help wanted)*
- [ ] Use pushed MQTT deltas directly rather than as a nudge to re-read
      everything
- [ ] A washer-to-dryer hand-off, once the washer's finish is verified: "the
      wash is done, here's the dryer programme to match". Haier has nothing
      equivalent for this pair ([HANDOVER](HANDOVER.md))

## 1.0: something you can forget is there

- [ ] Updates without reinstalling
- [ ] More than one verified appliance family
- [ ] Settings that carry across versions with a tested migration
- [ ] Settle whether the service can run under its own Windows identity
      ([SPEC](SPEC.md) §14, experiment 4)
- [ ] A one-page website. Worth it once people are arriving from outside
      GitHub; until then the README is the landing page

## Not planned

Said out loud so nobody waits for it:

- **macOS or a Linux desktop app.** The service and domain layer run on Linux
  already (CI proves it), but the window and the credential store are Windows.
  A contribution would be welcome, but it isn't on this list.
- **Competing with Home Assistant.** If you run it, its hOn integration does far
  more than Pastie will.
- **Supporting all sixteen hOn appliance types from here.** They get verified by
  the people who own them. That's the design.
