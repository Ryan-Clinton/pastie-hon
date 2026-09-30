# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Pastie (distribution `pastie-hon`, import package and commands `pastie`) is an unofficial Windows companion for Haier hOn
appliances: it watches an appliance through the community `pyhon-revived` client and reacts across
other kit (Hue, Google Home via Cast, webhooks). It is built and verified against one machine, a
**Haier HD90-A2959R-UK tumble dryer**. Read `docs/HANDOVER.md` for orientation; `docs/SPEC.md` is
the authority on design and on every hardware fact; `docs/UI-SPEC.md` governs the window and voice.

## Commands

```powershell
.venv\Scripts\pip install -e ".[dev]" -c constraints.txt   # always with -c constraints.txt

pytest -q --cov=pastie --cov-report=term-missing
ruff check .
ruff format --check src tests scripts packaging
mypy                                                       # strict, covers src and tests
python scripts/third_party_notices.py --check
```

On this machine the dev tools (pytest, ruff, mypy) are installed in **`.venv-revived`**; `.venv`
has only the runtime dependencies. Both run this checkout's `src/`.

Those five are exactly what CI runs (Windows + Linux, Python 3.11 and 3.12). Run them before
claiming anything works.

- Single test: `pytest tests/test_tracker.py::test_name` or `pytest -k "gap"`. Test names follow the
  scenarios in SPEC §13 ("what has to be tested").
- pytest runs with `filterwarnings = ["error"]`, `--strict-markers` and `asyncio_mode = "auto"`: any
  warning fails the run, and async tests need no decorator.
- Run it: `pastie login`, `pastie service` (background half), `pastie status`, `pastie where`,
  `pastie test <messenger>`, `pastie-app` (the window, which starts the service itself if needed).
- Windows build: `.venv\Scripts\python -m PyInstaller packaging/pastie.spec --noconfirm --distpath
  build/pkg/dist --workpath build/pkg/work`, then `build\pkg\dist\Pastie\pastie-cli.exe --self-check`.
  `.venv` has PyInstaller. One folder, two exes (`Pastie.exe` window/`service`, `pastie-cli.exe`);
  `packaging/entry.py` dispatches, and `app/launch.py` starts the service as `Pastie.exe service` when
  frozen. `.github/workflows/release.yml` builds zip + Inno Setup installer + SHA256SUMS on a `v*`
  tag. The tag must equal `pastie.__version__`, and the release notes are that version's CHANGELOG
  section (`scripts/release_notes.py`).
- `scripts/demo_gif.py` regenerates `assets/demo.gif` from real demo output. Rerun it when demo
  wording changes.
- `pastie demo [cycle|gap|tank|noise|ignored|unverified|list|all]` replays recorded readings through the real
  connector, tracker and command tracker. Each scenario's claims are pinned in `tests/test_demo.py`,
  so changing behaviour means updating the demo narration too.

## Architecture

```
Haier (hOn)  ->  connector  ->  core  ->  messengers
                                  \->  service  <-- named pipe -->  app (window)
```

- **`connector/`** is the only package that knows Haier's vocabulary (`machMode`, `prPhase`,
  `remoteCtrValid`, ...). `hon.py` is the only module that opens a connection; `reading.translate`
  is a pure function from `RawReading` to `core.state.Snapshot`; `profiles.py` declaratively records
  what each number means and whether that mapping is **verified**; `scrub.py` is a privacy
  **allow-list** that every reading passes through first. A field missing from that list is invisible
  to everything downstream, including the journal. A raw Haier field name outside `connector/` is a
  rejected change.
- **`core/`** imports nothing from the other layers and no third-party client: no network, no
  Windows. The Linux CI leg exists to prove this. `tracker.py` turns snapshots into `Event`s:
  UNKNOWN is a real state, the first reading of a session is a silent baseline, and a change since
  the last session is reported as a *gap*, not as news. The appliance's cycle counter (a separate
  statistics endpoint) is what distinguishes completed from cancelled. Every event key goes through
  `ledger.py` before it is emitted, so a restart never re-announces. `commands.py`: a command is
  never "done" because Haier accepted it; it carries an id, a proving state and a deadline, and
  success comes only from observed machine state.
- **`messengers/`**: each messenger *describes* its settings (`Setting`/`Kind`) and the settings
  screen draws itself from that. Register a new one in `build_registry` in `messengers/__init__.py`
  (explicit, because the packaged .exe can't scan folders). `base.py` enforces isolation and timeouts,
  one alert per target, a central flash-rate cap (seizure safety) and secret redaction.
- **`service/`** is the long-running half and holds the **only** connection to Haier. `watcher.py`
  loops connect -> subscribe (MQTT push) -> read -> translate -> tracker -> messengers, and
  re-baselines after any reconnect. `protocol.py` is transport-free JSON-lines request/reply
  (`WRITING` lists the mutating actions); `channel.py` is the Windows named pipe with an explicit
  security descriptor. `main.py` is the only place real implementations are wired, so tests build
  the same service from stand-ins. Credentials are DPAPI-encrypted under the service identity in
  `%PROGRAMDATA%\Pastie` and can never be read back out through the protocol.
- **`app/`** is a pywebview (WebView2) window. `client.py` is the whole service conversation with no
  window, tested against the real `Dispatcher`. `presenter.py` builds a plain-dict **ScreenState**,
  and every word and decision lives there, in Python, under test. `app/web/` (HTML/CSS/JS) only draws
  it. The page must always be loaded as an explicit `file:///` URI: pywebview otherwise silently
  starts a local HTTP server, which is forbidden, and `tests/test_webview.py` (via
  `tests/window_probe.py`, run as a subprocess) proves no socket is listening. Bridge calls
  arrive on several threads and take one lock.
- **Voice and personality.** `voice.py` holds every authored line (long lines allowed; one sentence
  per line), and `tests/test_voice.py` enforces pool sizes, lengths and uniqueness. `personality.py`
  handles the owner-editable TOML sheets. Levels are plain / dry / departmental. Facts are plain at
  every level. Faults, a full tank, login problems and anything else the user must act on never get
  a joke, and there is deliberately no pool for them. The "Confirmed" pose appears only on
  machine-confirmed state.

## Rules that are easy to break

- **Unverified appliance types** (anything without a verified mapping in `connector/profiles.py`)
  get raw values only: no interpreted state, no fault alerts, no commands. Verification is
  per-mapping and requires someone who owns the appliance to have observed it, not reasoned it out.
  Never guess what a number means.
- Never bypass or weaken an appliance safety interlock (e.g. the dryer's remote start requires
  arming at the panel, and it disarms after every cycle).
- Tests assert **what Pastie announced**, not what was parsed. Recorded fixtures (`tests/fixtures/`,
  format in its README) must be stripped via the `scrub.py` allow-list: Haier payloads contain GPS
  coordinates, MAC and serial. `dump/` and `.credentials` are gitignored for that reason.
- Dependencies are pinned exactly. `constraints.txt` locks the full transitive set; regenerate it
  only from a clean venv (see its header). `awsiotsdk` and `awscrt` move together.
  `THIRD_PARTY_NOTICES.txt` is generated, never hand-edited.
- Every third-party client without types is ignored in mypy and sits behind an adapter; keep it
  that way.
- `prototype/` is the verbatim record of what was measured on the hardware. It is excluded from
  ruff and mypy; don't tidy or delete it. `build/` and `dist/` hold the prototype's old .exe; the
  current build has no packaged artefact yet.

## Conventions

- Commit subjects are lowercase and typed: `feat(connector):`, `fix:`, `docs:`, `test:`. See
  `git log`.
- `CHANGELOG.md` is updated per change, newest first, under "Unreleased".
- Comments and docs explain *why*, usually naming the failure that forced the decision (see the
  comments in `pyproject.toml` and `ci.yml`). Don't write comments that restate the code.
- When unsure, prefer the vaguer true sentence to a specific guessed one. That applies to user-facing
  copy as much as to code.
