# Changelog

Notable changes, newest first. Dates are when the work landed, not when anybody
released anything — nothing has been released yet.

The format is loosely [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- 131 tests, CI on Windows and Linux across Python 3.11 and 3.12, ruff and mypy
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
