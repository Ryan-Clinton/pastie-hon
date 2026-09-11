# Changelog

Notable changes, newest first. Dates are when the work landed, not when anybody
released anything — nothing has been released yet.

The format is loosely [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **`pastie demo`** — replays recorded readings through the real connector, the
  real brain and the real command tracker, with no appliance, no hOn account and
  no network. Six scenarios, each one a case that is easy to get wrong: a
  watched cycle, a completion nobody saw, a tank filling twice in one load,
  duplicate and stale updates, a command
  Haier accepted and the machine ignored, and an unverified appliance. Every
  claim the narration makes is pinned by a test, so the demonstration cannot
  drift away from the code and start lying.
- Screenshots of the window in the README, and repository topics.
- **The window starts the background service** if one is not already running, so
  a single shortcut is all anybody needs. Two processes is an implementation
  detail, not something to make somebody open a terminal for.
- **`scripts/install-shortcuts.ps1`** — points the Start menu and Desktop at the
  window, puts the service in Startup so something is watching when you are not
  at the PC, and takes the prototype's shortcuts off the menus.
- **One service, enforced.** A named mutex refuses a second one rather than
  letting two connections to Haier disagree about what the machine is doing.
- **A different alert per event.** Any messenger setting marked `per_event` can
  be given its own value for each alert — a colour per event on a Hue light, a
  different sentence on a speaker. Merged centrally in
  `pastie.messengers.base.for_event`, so a messenger receives one flat config
  and cannot get it wrong. The settings screen draws the grid implied by two
  facts it does not itself hold: which settings the messenger says can vary, and
  which alerts the core defines.
- **Cleaning reminders are alerts now.** The appliance keeps its own service
  schedule — filter every 15 cycles, drum every 100 — and Pastie already read
  it, but nothing was ever done with it.
- **A full water tank alert.** The HD90 reports it as notification
  `message 4`, pausing itself in the same pushed update, and it raises
  `NEEDS_EMPTYING` as soon as it appears - including at startup, a deliberate
  exception to "the first reading announces nothing", because a dryer standing
  stopped is not old news - and again if the tank fills twice in one load.
  Found by watching the real machine, not by reading Haier's strings: those
  suggested a phase number, and it is not one.

### Fixed

- **Only the direct dependencies were pinned.** CI resolved `multidict` 6.8.0
  where the licence notices had been generated against 6.7.1, and the notices
  check failed on a commit that changed no dependency at all. `constraints.txt`
  now locks the whole resolved set, and CI installs with it.
- **Faults flashed green.** Replacing Hue's hard-coded "faults are red" with
  per-alert settings left no default behind it, so every alert looked like a
  finished cycle unless somebody configured otherwise - and a full tank would
  have been announced with the "finished" sentence. Each alert now carries a
  default of its own, beneath whatever the user chooses.
- **The change journal could not see notification codes.** `message` was not on
  the allow-list, so the journal watched the tank fill and wrote down "paused".
- **The mouse wheel changed dropdown values.** Tk cycles a combobox while the
  pointer is merely over it, so scrolling the settings page quietly rewrote
  saved choices, and scrolling the appliance page changed the programme about to
  be started. Found by scrolling past Temperature and watching it go from High
  to Middle.
- **The Settings tab was empty.** Nothing ever asked the service for the
  settings; `_draw_messengers` was written and tested by being called directly,
  so the drawing worked and was unreachable.
- **Lights and speakers were text boxes.** The `TARGET` setting kind had no case
  in the window, so you would have been pasting a UUID rather than choosing
  "Living room light". Now a dropdown filled from the messenger's own
  `discover()`, showing whether the light does colour.
- **The named pipe served one client at a time**, while the window asks for the
  status, the settings and a light list on three threads at once — so two of the
  three were told the service was not running while the header said it was
  working normally.
- **The service could not shut down.** `ConnectNamedPipe` cannot be cancelled,
  so the accept loop waited forever for a client that was never coming. It now
  nudges its own pipe to wake up.
- The migration converts Hue brightness from the v1 scale to the v2 one (254 is
  not 254%), and matches the prototype's v1 light number to its v2 id **by
  name** — so upgrading needs nothing from the user at all.

## [0.2.0] — 2026-09-04

The framework the specification describes, built. The prototype still works and
is kept in `prototype/` as the record of what was measured against the hardware.

### Added

- **`pastie.core`** — the domain layer, with no network, no Windows and no Haier
  in it. Snapshots, the state tracker, the announcement ledger, command
  lifecycle and health classification.
  - "Unknown" is a real state: the first reading of a session baselines silently,
    and anything that changed while Pastie was off is reported as a gap.
  - Completed cycles are keyed on the appliance's own counter, so a live
    announcement and a restart-inferred one cannot both fire.
  - Commands are confirmed by the machine changing state, never by a server
    accepting the request.
- **`pastie.connector`** — the only package that knows Haier's field names.
  Declarative appliance profiles with per-mapping verification, and an
  allow-list scrubber that cannot go stale.
- **`pastie.messengers`** — Hue (on the current v2 API), spoken announcements on
  a Chromecast, and webhooks. Isolation, timeouts, a central flash-rate cap and
  one-alert-at-a-time locking are enforced in the base rather than left to each
  author.
- **`pastie.service`** — one connection to Haier, credentials encrypted with
  DPAPI under the service's own identity, and a named pipe with an explicit
  security descriptor for the app to talk over.
- **`pastie.app`** — the window, with settings screens generated from what each
  messenger says it needs.
- **`pastie` command line** — `service`, `login`, `migrate`, `status`, `test`,
  `where`.
- **`pastie migrate`** — brings a prototype folder's account and Hue/speaker
  settings across. The existing Hue key keeps working; nobody re-presses the
  bridge button.
- **Maintenance reminders** — the appliance reports its own service schedule
  (filter every 15 cycles, drum every 100), so no per-model knowledge is needed.
- 153 tests, CI on Windows and Linux across Python 3.11 and 3.12, ruff and mypy
  (strict) clean, and generated third-party notices.

### Changed

- **The hOn password is no longer in a plain text file.** This was the one thing
  about the prototype that was genuinely wrong.
- **The Cast file server serves one file.** The prototype bound to every network
  interface and served the whole speech cache directory. It now serves a single
  file from memory, at an unguessable path, bound to the LAN address, and shuts
  down the moment the announcement ends.
- **Hue moved to the v2 API.** The v1 interface stops working on newer bridge
  firmware. v2 also states outright whether a light supports colour, so
  white-only bulbs are pulsed rather than sent a colour that fails.
- **Faults flash a different colour from a finished cycle**, so you can tell
  which it is from the next room.

### Fixed

- A setting changed in the app applies to the next alert rather than the next
  restart — the settings document was being cached after its first read.
- The client's HTTP session is closed on every disconnect, rather than leaking
  one per reconnect.

## [0.1.0] — 2026-08-30

The prototype: a working control panel and notifier for a Haier HD90 dryer.
Polls the hOn cloud, flashes a Hue light and announces on a Google Home when a
cycle ends. Kept in `prototype/`.
