# Pastie — the window, redone properly

Status: **approved 2026-09-25, revision 4; being built** on the
`feature/window-redesign` branch, one phase per commit (§12). Phases 1 to 5
are built. Where the build taught us something, the text below says so. It covers the desktop window only. The service, the
connector, the brain and the messengers don't change, and
[SPEC.md](SPEC.md) still governs them.

**How Pastie speaks is governed by SPEC §17–20** (the delight contract, the copy
architecture, where the personality lives, and earned delight). This document
is how the *window* carries that out. Where the two disagree, SPEC §17–20 wins.

Revision 2 applied audit round 1:
- the three personality levels (Plain / Dry / Departmental)
- fact first and plain words on faults
- no borrowed catchphrases, including every 42
- the command paper trail
- History, Diagnostics and About as places the voice lives
- the delight tests

Revision 3 applied audit round 2:
- the supplied crest as the visual identity, with three tiers of detail
- six static poses instead of animated expressions
- Pastie as the competent operative of a named division
- Pastie's laws
- stamps, and the case-file detail view
- "Why does Pastie say this?"
- "Where matters currently stand"
- the bureaucracy Pastie endures on the user's behalf
- idle as success
- the screen-by-screen design, in [UI-SCREENS.md](UI-SCREENS.md)
- **the owner's direction:** Pastie is the controller, and every appliance in
  the house, and the humans, have personalities Pastie negotiates with. It's a
  whole-house app, not a dryer app: a washer is coming, and solar panels may
  follow (§7.3)

Revision 4 applied the owner's direction after round 2: **every personality,
and how Pastie deals with it, is fully configurable** (§7.9).

The brief, in the owner's words: the app gets used "sometimes multiple times a
day", it's "one of the most useful things we have made", and it should become
"quite funny and slick". This document is how.

---

## 1. Goals, and what this is not

**Goals**

1. **Answer "what's the dryer doing?" in one glance, from across the room.** The
   window is opened several times a day to check on a cycle. Every other goal
   ranks below this one.
2. **Make it a pleasure to open.** The pastie mascot, and a voice built on
   Douglas Adams's *mechanism*: calm, precise prose documenting an unreasonable
   reality (SPEC §17). Humour that reacts to what actually happened, so the
   fifth look of the day isn't a repeat of the first. The final editorial test
   is SPEC §20's: *if Pastie stopped being funny, would it still be an unusually
   clear appliance utility?*
3. **Look like a finished product**, not a Tk demo. That means consistent dark
   styling with no white system widgets, real typography, motion that means
   something, and a layout that holds at any window size.
4. **Lose nothing.** Every fact the current window shows, it still shows, and
   every rule in the existing code about honesty still holds (see §3).
5. **Be a whole-house app from the start.** Today there's one dryer. A washer is
   coming, a smart projector is on its way, and solar panels may follow. Nothing in the layout, the voice or the
   presenter may assume there's only one appliance, or that every appliance is
   a dryer.

**Not goals**

- A web app, a phone app or remote access. It's a desktop window on the PC that
  runs the service, as now.
- New appliance features. This is presentation. Anything that needs new data
  from Haier is out of scope, and so is anything the service doesn't already
  supply (§6.4 lists what it does supply).
- Replacing the settings screens' *behaviour*. They get restyled and
  reorganised, but they still draw themselves from what each messenger declares
  (SPEC §8). No messenger-specific interface code.

---

## 2. Where it is now

The window is Tkinter (`src/pastie/app/main.py`, about 1,000 lines), with two
tabs, Appliance and Settings. Screenshots from 2026-09-25 show these problems:

| # | Problem | Where |
|---|---|---|
| 2.1 | Dropdowns and text fields render as bright white system widgets on a dark window. This is the single biggest "home-made" tell, and Tk can't restyle them properly on Windows | Both tabs |
| 2.2 | The status card is mostly empty space when idle, and the one useful fact (idle, armed or not) is small | Appliance |
| 2.3 | While idle it still shows "Programme: Cotton" and "Remaining: unknown" from the last cycle. That's stale, and reads as if something is running | Appliance |
| 2.4 | The command result ("Accepted by Haier 11:19:05") appears in grey monospace under the buttons and never goes away | Appliance |
| 2.5 | START and STOP are equal-weight boxes, and STOP is always shown, even when nothing is running | Appliance |
| 2.6 | Settings is one long scrolling form. The account, Hue, speaker and per-alert overrides all look the same, and the per-alert grid is hard to read | Settings |
| 2.7 | Nothing moves. A running cycle and an idle machine look nearly identical apart from one word and the meters | Appliance |
| 2.8 | The narration (`app/ordeal.py`) has two or three lines per stage. At several looks a day, they repeat within a day | Appliance |
| 2.9 | `app/ordeal.py` breaks three SPEC §17 rules. The sock meter holds at 42 (rule 6, no borrowed catchphrases). The fault and full-tank lines add a joke after the instruction (rule 5, plain language where action is needed). The unknown-state line is a joke with no fact in it (§19, "Unknown really means unknown"). **Recorded here as build work for phase 1 (§12), not changed during the audit** | Appliance |
| 2.10 | The window and taskbar icon is a photo of a burger on a grey square, which reads as a muddy square at 16–32 px. The owner has since supplied the crest (`docs/ChatGPT Image Sep 25, 2026, 01_51_56 PM.png`), and it becomes the identity (§10.4) | Window, taskbar |

What works and must survive:
- the service boundary
- the "(real)" meter
- the pastie icon and taskbar identity
- the per-programme recommended settings
- the command lifecycle wording ("accepted" is not "confirmed")
- the settings screens drawing themselves from each messenger's declared settings

---

## 3. Rules inherited, and not up for renegotiation

These come from SPEC.md and from how the current window was built. The redesign
has to satisfy them. It doesn't get to argue them.

| Rule | Source | What it means here |
|---|---|---|
| **The window never talks to Haier.** It asks the service | SPEC §4 | The new front end talks only to `ServiceClient`, exactly as now |
| **No unauthenticated network interfaces** | SPEC §10, §12 | The front end must not open a listening socket. See §5.3: this is the one trap in the recommended technology |
| **Windows only, for now** | SPEC §3 | We can depend on WebView2 (§5.2) |
| **Dependencies pinned to exact versions**, and the licence notices regenerated | SPEC §3, `constraints.txt` | Any new package goes into `pyproject.toml`, `constraints.txt` and `THIRD_PARTY_NOTICES.txt` in the same change |
| **Honesty over cheer** | `app/ordeal.py` docstring | The first meter is the real progress and says so. No meters without a real number behind them. A fault or full tank says what to do before the joke |
| **"Accepted" is not "done"** | SPEC §7 | The UI never shows success for a command until the machine confirms it |
| **Unverified appliances are shown raw** | SPEC §9 | Any other hOn appliance gets names and raw values, and never an interpreted description. The voice may explain Pastie's refusal to guess (SPEC §19, "Unknown really means unknown"), but it never guesses |
| **Pastie's laws** | SPEC §17 | The five administrative principles. The mascot corollary: **Pastie never gives the thumbs-up unless Pastie knows** |
| **The delight contract** | SPEC §17–20 | Fact first, wit second. Plain language for faults, safety, credentials and anything needing action, in every personality mode. No borrowed catchphrases. Logs hold canonical facts, never the displayed wording. No runtime-generated copy for appliance state, faults, commands or instructions |

---

## 4. The design, in one paragraph

One window, one hero. **The caseload** is at the top: one row per appliance,
each with its state word, so a house with a dryer, a washer and solar panels is
understood in one glance. The appliance that most needs attention (running,
then waiting on somebody, then finished, then idle) becomes **the hero**: the
pastie in one of its poses, inside a ring that is the real progress. The pose
and the ring tell you the state before you read a word. Under it, the plain
facts and at most one aside. With one appliance, as today, the caseload is just
that appliance's row, and the hero is always it. Below that, a compact **Start
panel** that only appears when the machine is armed, and turns into a **Stop**
button while it runs. History, the Guide (the lore), Settings and About
live behind a small navigation rail, out of the way, and Diagnostics is one
click from About and from the health dot. Everything is dark by default, follows
the Windows light/dark setting, and never shows a white system widget.

---

## 5. Technology

### 5.1 Options considered

| Option | Look achievable | Effort | Risk | Verdict |
|---|---|---|---|---|
| **Polish Tk** (Sun Valley ttk theme, custom-drawn canvases) | Better, but combobox popups and scrollbars stay native-ish; motion is hand-rolled on a canvas | Low | Low | Fixes 2.1 partly. Can't reach "slick" |
| **CustomTkinter** | Modern flat widgets, rounded corners | Medium (a widget-by-widget rewrite) | Medium: limited layout and animation; one maintainer | A real improvement, with a visible ceiling |
| **PySide6 (Qt)** | Excellent; stylesheets, animation framework | High | Low technically; a large dependency (~100 MB) and LGPL obligations in the packaged `.exe` | Over-engineered for one window |
| **pywebview + HTML/CSS/SVG** | Anything a modern web page can do: SVG character, CSS animation, real typography | Medium | Two languages; one security trap (§5.3) | **Recommended** |

### 5.2 Why pywebview

- It uses **WebView2**, the Edge engine that ships with Windows 11, so there's no
  bundled browser. The package itself is small and pure Python.
- It gives full visual freedom for the pastie, the drum ring, motion and
  typography, which is most of what "slick" means here.
- JavaScript calls Python through `window.pywebview.api.<method>()`, which
  returns a promise. That maps one-to-one onto the existing `ServiceClient`, so
  the service boundary is untouched.
- Frameless windows, a background colour and a minimum size are all supported on
  Windows. Transparency and vibrancy are macOS-only, and this design doesn't
  depend on them.

### 5.3 The trap, and the rule that closes it

pywebview **starts a local HTTP server automatically when a page is given as a
path**, and that can't be switched off. That would be an unauthenticated
network interface, which SPEC §10 forbids.

**Found while building:** the pywebview documentation says this happens only
for *relative* paths. It doesn't. With pywebview 6.2.1, an absolute path *and*
`http_server=False` still served the page from `http://127.0.0.1:<port>`. A
spike caught it before any UI was built on it.

**Rule:** the page is loaded from an **explicit `file:///` URI**
(`webview.page_uri()`), never a path, with `webview.start(http_server=False)`.
No remote URLs, fonts or scripts, ever.

**The bridge exposes methods only.** pywebview hands every *public attribute*
of the `js_api` object to the page, not just its methods. It also walks into
them: a native window object stored as a public attribute sent it into endless
recursion. Everything that isn't a method the page may call is private, and a
test checks that every public name on the bridge is a method.

**Test (acceptance criterion A7):** with the window open, the window process
owns no listening TCP or UDP socket. `tests/window_probe.py` opens the real
window in its own process and checks `Get-NetTCPConnection -State Listen`
against its PID and its children. `tests/test_webview.py` runs it on Windows,
including CI's Windows runners, and skips only if WebView2 can't start there
at all.

The page also carries a Content-Security-Policy of `default-src 'self'
file:; script-src 'self' file:; style-src 'self' 'unsafe-inline' file:;
connect-src 'none'`. `connect-src 'none'` means the page can't fetch anything,
even if a future change tries to.

### 5.4 If WebView2 is missing

It's present on every supported Windows 11 install, but it can be removed. If
pywebview can't start, `pastie-app` shows a plain Tk dialog: "The window needs
Microsoft Edge WebView2. The background service is unaffected and alerts still
work." It includes a link to Microsoft's installer page, opened in the default
browser. The old Tk window is **not** kept as a fallback, because maintaining
two UIs is how both rot. The service, which is what matters when nobody's
looking, never depends on WebView2.

### 5.5 Where the logic lives

**All wording and all decisions stay in Python.** A new module,
`pastie/app/presenter.py`, turns the service's status reply into a
**ScreenState**: a plain dictionary holding every string, number and flag the
page needs. The page renders it and does nothing clever. This means:
- the jokes, the honesty rules and the no-repeat rules are tested with `pytest`,
  like everything else
- the JavaScript stays small (target: under 600 lines, no framework, no build
  step, no npm)
- a future change of front end repeats none of this work

`app/ordeal.py` becomes part of the presenter.

**Every message follows SPEC §18's shape:**
- `headline`: required, factual, short
- `fact`: required, the canonical description
- `next_action`: optional, a factual instruction
- `aside_key`: optional, the pool of authored lines
- `severity`: info, maintenance, warning, error or safety

**How the three personality levels work:** the presenter fills in the facts
first. Only then does it add an aside, if the chosen level allows one and the
severity is info or maintenance.
- **The same event keeps the same aside on every redraw.** The aside is picked
  from the pool by event ID and remembered.
- **What gets saved:** the window's small state file holds canonical facts and
  aside choices, never rendered sentences.
- **Nothing is generated at runtime.** Every line is authored and shipped with
  Pastie.

**Derived, not fetched.** Some of SPEC §19 needs history the service doesn't
send. The main example is noticing that the time remaining went *up*. The
presenter works these out by comparing successive status replies within the
session. No new service fields are needed for them. §11 lists the two things
that would need a service change.

---

## 6. The main screen

### 6.1 Layout

```
┌───────────────────────────────────────────────┐
│ ◉ Pastie                     ● Working normally│  header: name, health dot + words
├───┬───────────────────────────────────────────┤
│   │ Tumble dryer  RUNNING  │ Washer  FINISHED │  the caseload: one chip per appliance,
│   │ (one chip per appliance; click to make    │  most urgent first (§6.10)
│   │  it the hero)                             │
│   ├───────────────────────────────────────────┤
│ ⌂ │      ╭──────── drum ring ────────╮        │
│ 🕘│      │     [the pastie, SVG]     │  58%   │  hero: ring = real progress,
│ 📖│      ╰───────────────────────────╯        │        big % and time remaining
│ ⚙ │   RUNNING · Duvet · 25 min · settled      │  plain facts (§6.3)
│ ? │   "Somewhere in the drum a sock is…"      │  at most one aside (by level, §7.2)
│   │   Crispiness ▓▓▓▓▓▓▓░░ 82                 │  joke meters: Departmental only
│   │   Existential dread ▓▓▓▓▓▓▓▓░ 95          │
│   ├───────────────────────────────────────────┤
│   │  [ Stop ]      or      Start panel        │  actions (§6.5)
└───┴───────────────────────────────────────────┘
```

- **Minimum size 420 × 560**; the default is 480 × 720. The window remembers its
  size and position.
- At widths under 520 the rail collapses to icons only (it's icons-first
  anyway). Nothing scrolls horizontally, ever.

### 6.2 The hero: the pastie in the drum

- **The ring *is* the real progress.** It replaces the "Doneness (real)" meter
  as the honest number. The percentage is written beside it in large type.
- **The time remaining carries a confidence label** (SPEC §19, "Time
  remaining"): **"About 52 min · still estimating"** while the machine's figure
  is early, and **"47 min · settled"** once it's trustworthy. That's the
  distinction the connector already makes. When there's no progress figure at
  all, the ring shows a slow neutral shimmer and "Still estimating", not 0 %.
- **The pastie takes one of six static poses**, all drawn from the supplied
  crest so it's recognisably the same character (§10.4). Pastie never bounces
  or does game-character animation; a pose change is a 200 ms crossfade and
  nothing more.

  | Pose | Shown when |
  |---|---|
  | **Normal**: the crest's mild smile, arms down | idle, armed |
  | **Working**: looking at a tiny clipboard | running, and while a command waits for the machine |
  | **Waiting**: glancing sideways at a watch | paused, still estimating, reconnecting |
  | **Confirmed**: the crest's thumbs-up | **only** on machine-confirmed state: a command confirmed by the machine, or a finish evidenced by state change and counter |
  | **Unknown**: peering at a piece of paper | unknown or unverified state |
  | **Fault**: neutral and attentive, no comedy | fault, full tank, anything with warning, error or safety severity |

  **Pastie never gives the thumbs-up unless Pastie knows** (SPEC §17, Pastie's
  laws). In Plain mode the pose is always Normal, except Fault.
- **Motion carries meaning, and only the ring moves.** While running, the ring's
  leading edge has a slow travelling highlight. It stops dead when paused, and
  completes cleanly when finished. The pastie itself doesn't move. No motion
  loops while idle.
- **Colour and shape agree.** The state colour (green running, amber paused,
  blue finished, red fault, grey idle) is always paired with a word and an
  expression, never colour alone.

### 6.3 Facts line, and the one aside

```
CURRENT CASELOAD                                   (Departmental heading only)

Tumble dryer                         RUNNING
Mixed / Ready to wear                   54%
Estimated completion  14:37  ·  about 47 min · still estimating

The dryer currently believes 47 minutes remain.
Pastie has elected not to contradict it.
```

- **"Estimated completion" is a clock time**, derived from the time remaining
  and the time of the reading (derived, not fetched, §5.5). It's prefixed
  "about" while the estimate is still settling.

- **The facts** are the state word, the programme with its settings, and the
  time remaining with its confidence. They're plain in every mode. **The
  programme and time are shown only while a cycle is running, paused or just
  finished**, which fixes 2.3.
- **Under them, at most one aside.** What it is depends on the personality level
  (§7.2):
  - **Plain:** nothing.
  - **Dry:** an aside **only when something genuinely happened**, such as the
    estimate going up, a recovered gap, or the first confirmation of a start.
    **Otherwise the aside disappears rather than inventing something to say**
    (SPEC §19, "The home screen"). The one standing exception is idle (§6.9).
  - **Departmental:** the pastie's ordeal. A narration line from the stage's
    pool (§7.4) when nothing notable has happened, and the reactive aside
    instead when something has.
- The aside is never the only place a fact appears. Delete it and the screen
  must lose nothing (SPEC §17, voice rule 1).

### 6.4 Meters (Departmental only)

- In Departmental mode, three joke meters sit under the aside, with a set per
  programme (§7.5). In Dry and Plain modes there are no joke meters; the ring is
  the only gauge.
- Each meter animates from its old value to its new one over 600 ms, and shows
  its number.
- There are no meters without a real progress figure (the existing rule), and
  none while the severity is warning, error or safety.
- **The data the presenter can use** is only what the service already sends:
  state, progress, programme, remaining (with the settled flag), attention,
  fault code, maintenance, cycle count, recent events, commands, remote-armed,
  per-programme options, trust and raw values. Anything else is derived from
  successive replies within a session (§5.5).

### 6.5 Actions, and the paper trail

- **Not armed:** no Start panel. The facts are "Remote start is unavailable.
  Turn the programme dial to Remote on the dryer first." In Dry and
  Departmental modes, the aside is "The remote-control procedure currently
  contains a mandatory visit to the dryer." The one control says **Waiting for
  Remote mode**. Controls stay literal (SPEC §19).
- **Armed and idle:** the Start panel appears.
  - The programme is chosen from **a grid of tiles** for the 11 programmes, each
    with a small icon. It's faster than a dropdown, and the tiles are the dial.
  - Dryness, temperature and time are **segmented controls**. The recommended
    choice is marked with a small ★ and pre-selected (the current behaviour,
    restyled). A fixed setting shows as a locked chip, not a disabled dropdown.
- **Running:** the Start panel collapses into one **Stop** button, in secondary
  style. Stopping asks "Stop the Duvet cycle?" inline, not in a modal dialog,
  and needs a second click within 5 seconds.
- **Commands get a paper trail** (SPEC §19). This replaces the toast, and fixes
  2.4:

  ```
  START CYCLE
  20:41:02  Requested
  20:41:03  Haier accepted the request
  20:41:06  Dryer confirmed RUNNING                    [CONFIRMED]
  ```

  - `[CONFIRMED]` is a small stamp, and is real text, so screen readers read
    it.
  - After confirmation, in Dry or Departmental mode only, one aside may follow:
    "Three separate parties have now agreed that the dryer is on."
  - **While it waits for the machine**, the pastie takes the Working pose over
    "Waiting for dryer… Haier accepted the request. Pastie is waiting for the
    machine itself." **When the machine confirms**, it switches to the Confirmed
    pose over "Confirmed. The dryer is running." The thumbs-up then means
    something, because nothing else can produce it.
  - **On failure, no aside in any mode, and the Fault pose.** A plain panel:

    ```
    COMMAND NOT CONFIRMED

    Haier accepted                14:22:01
    Dryer confirmation            NOT RECEIVED
    Waited                        20 seconds

    Pastie cannot establish that the machine started.
    Nothing has been marked successful.
    ```

    The sudden absence of humour is itself the signal that this matters.
  - The trail collapses to its last line 8 seconds after a final state, and the
    full trail stays in History (§8).

### 6.6 Header, health and connectivity

The header has the Pastie icon, the name, and a health dot with words from the
service's own health states: "Working normally" (ok), "Working, but updates are
slow" (slow), "Can't log in" (auth), "Can't understand Haier's response"
(schema), "Can't reach the internet" (offline), and "The service isn't running"
(no reply). When something is wrong, the hero becomes **Where matters currently
stand**: the layers, each with its real status, then what to try.

```
WHERE MATTERS CURRENTLY STAND

Pastie service                WORKING
Internet                      CONNECTED
Haier account                 CONNECTED
Dryer                         NOT REPORTING SINCE 12:17

The internet is present.
Haier is present.
The dryer, presently, is not.

Try:
• Check that the dryer is switched on
• Check its Wi-Fi connection
```

- **Only layers the service can actually tell apart are shown**, mapped from its
  health state: the service (does it reply?), the internet (offline), the Haier
  account (auth) and Haier's responses (schema). There's also the time of the
  last appliance reading, which comes with every status.
- **The Dryer row is an exception.** The service subscribes to Haier's
  appliance presence events but doesn't yet pass them to the window. Until it
  does (§11, question 2), the Dryer row appears only when the last reading is
  older than the service's own staleness threshold, and says "NOT REPORTING
  SINCE 12:17". It never says "offline", which would be a claim Pastie can't
  make.
- The three-line aside appears only when every layer it mentions has a known
  status, and only in Dry and Departmental modes.
- **Authentication failures, unrecognised responses, repeated connection
  failures and "the service isn't running" are always plain**, because the
  user may need to act. Alerts don't work while the service is down, and the
  screen says so.

### 6.7 "Why does Pastie say this?"

A small `?` sits beside any statement Pastie makes with a confidence attached:
the time remaining, a finish, a confirmed command, an unknown state. Clicking
it explains **why Pastie believes it**, built only from the actual rule and its
actual inputs. It's a product feature first: smart-home software says things,
and Pastie can say why.

```
WHY DOES PASTIE SAY THIS?                  47 min · settled

The dryer reports 47 minutes remaining. That is now within the Mixed
programme's total of 120 minutes, which is the point at which this dryer
counts down about a minute a minute.

Source        Appliance telemetry
Confidence    Settled estimate
```

```
WHY DOES PASTIE SAY THIS?                  Finished

The dryer changed from RUNNING to FINISHED at 19:16:41.
Its completed-cycle counter also increased from 104 to 105.

Source        Appliance state and cycle counter
Confidence    Confirmed
```

- **Every explanation is generated from the real rule.** The settled test is
  "remaining is within the programme's total" (`connector/reading.py`). It is
  not, for example, "the last three estimates decreased", which isn't what
  Pastie checks.
- The confidence wording is one of **Confirmed**, **Reported by the
  appliance**, **Settled estimate**, **Still estimating** or **Not known**.
- The explanation text is plain in every mode. The heading is the joke, because
  it's accurate.

### 6.8 The bureaucracy Pastie endures on your behalf

Pastie may describe paperwork. It never makes the user do any (SPEC §17, rule
4).

- **Connecting.** While the window waits for its first good status, the lines
  follow the **observable** stages, never a timer:

  | Stage the window can see | Line |
  |---|---|
  | No reply from the service yet | "Contacting the service…" |
  | The service replies, but health isn't ok yet | "Contacting Haier…" |
  | Health ok, no appliance in the reply yet | "Requesting appliance records…" |
  | An appliance, but its first reading isn't verified yet | "Comparing their account with ours…" |
  | First verified reading | "Everything appears to be in order." (shown for 1.5 s) |

- **Reconnecting.** After health returns to ok from anything else, the line is
  "Connection restored. Pastie is requesting a complete account of what
  happened during its absence." If the first reading afterwards shows no change
  and no gap event, then in **about one in twenty** such reconnects, chosen
  deterministically by event ID (§7.4), the follow-up is "Nothing happened. This
  has simplified the paperwork considerably." Otherwise there's no follow-up.
- In Plain mode, these are "Connecting…", "Reconnected" and nothing else.

### 6.9 Idle is success

Most of the time nothing is happening, and **nothing happening is success**.
Pastie doesn't demand attention while idle, and the idle screen says so calmly:

| Level | Under "Tumble dryer · Idle" |
|---|---|
| Plain | *(nothing)* |
| Dry | "No active proceedings." |
| Departmental | "No domestic machinery currently requires intervention." |

In Dry and Departmental modes, an occasional variant from the `idle` pool (§7.8)
may replace it, for example "Pastie has nothing to report. This is generally
considered a successful outcome." That happens at most once a day.

### 6.10 More than one appliance

- **The caseload row** has one chip per appliance: its name, state word and
  pose thumbnail. The order is most urgent first: needs action (fault, tank),
  then running, then paused, then finished, then idle. Clicking a chip makes that
  appliance the hero until the next state change anywhere.
- **The hero follows urgency automatically**, unless the user picked one in the
  last five minutes.
- **Unverified appliances** appear in the caseload with the `UNVERIFIED` stamp
  and raw values only (§3). They never become the automatic hero.
- **Every appliance type has its own meters, pools and personality**, keyed by
  appliance type in the presenter. Nothing in the presenter is keyed on
  "dryer".
- **Non-Haier sources**, such as the smart projector and solar panels, need a
  new connector, and that's a
  SPEC change, not a window change (§11, question 7). The caseload and the
  presenter are shaped so that a new source arriving through the service needs
  only its own profile and personality, and no layout work.

---

## 7. The lore and the voice

### 7.1 The voice

SPEC §17's eight voice rules govern. In short:
1. fact first, wit second
2. the user is never the punchline
3. precision is funnier than wackiness
4. never manufacture friction for comedy
5. never joke over danger, faults, credentials or anything needing action
6. no borrowed catchphrases: no quotations, towels, 42s, depressed robots or
   "don't panic"
7. a joke has to explain the system, reward attention or make repetition nicer
8. restraint: one good aside per screen

What the window adds:
- **The target of the humour is the system**, meaning the appliance, the cloud,
  the procedures and the socks. It's never the user, and never the pastie's
  competence. Pastie itself is competent; the world it administers is absurd.
- **Short.** An aside is one sentence, two at most, under 160 characters, so it
  fits the hero at the minimum width.
- **Tests enforce rule 6:** no aside, narration, meter label or Guide entry
  contains any of a maintained list of borrowed terms (starting with `42`,
  `towel`, `panic`, `improbab`, `vogon`, `hitchhik`, and the two names that were
  in the README lore). The README lore has been brought into line (§11,
  question 1).

### 7.2 The personality level

SPEC §17's three levels, chosen in Settings → Appearance. **Dry is the
default.**

| Level | Home screen | Meters | Paper trail | Settings, History, Diagnostics, About |
|---|---|---|---|---|
| **Plain** | facts only | none | facts only | plain labels and help |
| **Dry** | facts, plus an aside only when something happened | none | an aside after confirmation | an occasional subtitle or empty-state line |
| **Departmental** | facts, plus the pastie's ordeal or the reactive aside | three per programme | an aside after confirmation | official-sounding subtitles ("Case file", "Minutes of recent proceedings"), the About org chart, richer Guide entries |

The level changes presentation only. It never changes event detection,
commands, severity, logging or the factual part of a message. **Anything with
warning, error or safety severity is plain at every level.**

### 7.3 The cast

**Pastie is the controller.** Everything else in the house, the appliances and
the humans, has a personality, and Pastie spends its working life negotiating
between them. That's where most of the comedy comes from: not jokes, but
Pastie's calm, precise reports of what the others are like.

**The rules that make a cast work:**
- **Pastie is the only narrator.** Nobody else speaks to the user directly.
  Everyone else appears as reported speech or reported position: "The dryer
  currently believes 47 minutes remain." That keeps one voice, one point of
  view, and keeps every fact attributed to its source, which is exactly what
  Pastie's laws require.
- **The shipped default personality describes real, observed behaviour**,
  never invented behaviour. The dryer "changes its mind about time" because its
  estimates really do wander. A new appliance's default character is written
  from what it actually does, once it has been watched. **The owner can change
  any of it** (§7.9). The defaults are just a well-observed starting point.
- **Only verified appliance types get a personality.** An unverified appliance
  is "not yet introduced": Pastie reports its raw values and declines to
  characterise it (Pastie's law 1).
- **The Household**, the humans, are the people Pastie works for. They have a
  personality in the sense that Pastie has a professional relationship with
  them: they're the principals, their wishes are sovereign, and they're sometimes
  out when something needs them. **They're never the punchline** (SPEC §17,
  rule 2). Pastie negotiates *on their behalf*, never *at* them.
- **At Plain level the cast disappears.** It's just appliances and their facts.

**Who's in it now, and who's coming:**

| Member | Status | Character, from observed behaviour |
|---|---|---|
| **Pastie** | the controller | §7.3.1 below |
| **The tumble dryer** | verified | Diligent but indecisive about time: its estimate wanders and sometimes goes *up*. Keeps its own records (cycle counter, filter and drum schedules), and Pastie respects it for that. Insists on a personal visit before it will accept remote instructions. Stops dead when its tank is full and waits, without complaint, for a human. |
| **The Household** | always | The principals. They set the programmes, empty the tank, and are occasionally elsewhere. Pastie is loyal to them, and keeps their paperwork tidy. |
| **The washing machine** | coming (not yet verified) | Written only once one is watched. Until its data is verified it's "not yet introduced". Where the dryer and washer interact, such as a wash handed over to the dryer, Pastie is the go-between. |
| **Solar panels** | possible, and not an hOn device | They'd arrive through a new connector (§11, question 7). Their character would come from their real behaviour, most obviously generating a great deal when nobody needs it and very little when everybody does, and Pastie would report it with the same care. Not written until they exist. |
| **The smart projector** | on its way; source not yet known, and probably not hOn | Like the panels, it arrives only through a connector for whatever it speaks, and its character is written from what it actually does. Not written until it's here and connected. |
| **Messengers** (the light, the speaker) | verified | Minor civil servants. They carry Pastie's messages and report back whether they were delivered. They don't speak in the window; Pastie reports on them. |

**Negotiation is shown as Pastie's report of positions**, never as dialogue
between machines. For example, in Departmental mode:

> The washer has finished. The dryer is available. The Household has not yet
> moved the laundry. Pastie has noted all three positions.

#### 7.3.1 Pastie itself

- **What it is:** a Northern Irish pastie (minced meat and potato, battered and
  deep-fried, usually served with chips, as in the crest). **It's the competent
  operative of the Domestic Appliance Liaison Division** of PASTIE, the
  *Practical Appliance Supervision, Telemetry & Interoperability Executive*
  (SPEC §17). Pastie is the employee, not the institution. It was placed in the
  post by a process nobody remembers agreeing to, and it regards the work as
  serious administration.
- **How it looks versus how it speaks:** the crest is warm, heroic and cute, and
  the voice is dry, officious and restrained. **That mismatch is deliberate**
  and shouldn't be "fixed" in either direction.
- **Competence:** Pastie is good at its job. The absurdity comes from what it
  administers: a dryer that changes its mind, a cloud that accepts commands the
  machine ignores, and a remote control that requires a visit.
- **Temperament:** unflappable and precise. It keeps records. It takes its
  duties seriously and itself not at all.
- **Believes:** that evidence beats supposition. That socks leave on purpose.
  That lint is a form of weather.
- **Relationship with the appliances:** professional, and slightly wary. It's
  been through a lot with the dryer, most of it in circles. Each appliance gets
  the same courtesy and the same scrutiny.
- **Relationship with the Household:** a loyal colleague. It's on their side
  against the machinery.
- **Never:** panics on screen, blames, sulks, guesses, or claims something
  happened that didn't.

### 7.4 Pools, memory and getting quieter

**Reactive asides (Dry and Departmental).** Each notable event has an
`aside_key` with a small authored pool. There are at least **3** variants per
key, and the key list is in §7.8.
- **A given event keeps its aside** on every redraw, because the pick is seeded
  by event ID and remembered.
- **Routine repeats get quieter** (SPEC §18, "Repetition rules"): the first
  occurrence of a kind of event may get an aside. Later ones use the factual
  line, unless there's genuinely new context, such as the estimate going up by
  more than last time.

**Departmental narration.** Stage pools for the pastie's ordeal have at least
**12 lines** for each of idle, armed, running-early, running-middle,
running-late and finished, and at least **6** for paused, estimating and
scheduled.
- **No pools for fault or full tank,** because those are plain (§7.1).
- **No repeats:** a line shown in the last 30 looks at the same stage isn't used
  again, until the pool runs out.
- **Stable within a stage:** once picked, a line stays until the stage changes.

**Tests:**
- every pool meets its minimum size
- every line is under 160 characters
- no line appears in two pools
- 200 simulated looks produce no repeat within the window
- the tests from §10.1

### 7.5 Meter sets by programme (Departmental)

Every joke meter goes from 0 to 100 and is derived only from real progress, so
it moves with the cycle. None is a borrowed number.

| Programme | Meter 1 | Meter 2 | Meter 3 |
|---|---|---|---|
| Default (Cotton, Mixed, Synthetics, Sports, Timer, Quick dry) | Crispiness (rises, then levels off) | Existential dread (peaks mid-cycle) | Sock escape probability (barely moves, then everything at the end) |
| Duvet | Loft | Feather anxiety | Likelihood it is secretly a cloud |
| Wool | Shrinkage fear | Sheep-related guilt | Cosiness |
| Towels | Fluffiness | Absorbency regained | Beach-readiness |
| Delicates | Nervousness | Frills intact | Tact |
| Refresh | Freshness | Smell of adventure removed | Plausible deniability |

Each meter has a named curve (rising, peaking or late), set in the presenter.
They're all tested for the 0–100 range across the whole cycle.

### 7.6 The Guide: lore unlocked by real events

The **Guide** page (📖 in the rail) is a small encyclopaedia in the voice.
Entries unlock from **real things Pastie has seen**, using data the service
already sends. They reward understanding the machinery, not using the app
(SPEC §20).

| Entry | Unlocks when | Uses |
|---|---|---|
| On Pasties, and Why One Is in Charge | always | the README lore |
| On Being Round | the first cycle Pastie watches | recent events |
| On Estimates, Which Change Their Minds | the first time the estimate goes up | derived (§5.5) |
| On Coming Back | the first completion Pastie reconstructs from a gap | recent events |
| On Water, and Where It Goes | the first full-tank alert | attention |
| On Lint | the first filter-clean reminder | maintenance |
| On Duvets, Which Are Not Quilts | the first Duvet cycle (the bug we fixed, told as legend) | programme |
| On Faults | the first fault, unlocked *after* it clears | fault code |
| The Fiftieth and the Hundredth | the cycle counter reaches 50, then 100 | cycle count |

- Each entry has a plain real-data footnote, for example "Cycles observed: 17 ·
  Filter due in 15".
- **Unlocks are recorded by the window**, and a new one shows a small "New in
  the Guide" dot on the rail. There's never a pop-up. There are no generic
  achievements such as "opened the app ten times" or "used it at 3am" (SPEC §20).
- In Plain mode, the Guide is still there, but its entries show only the facts.

### 7.7 Small delights (Departmental unless stated)

- **Clicking the pastie three times** gives a one-line aside from a pool of 12,
  with a 30-minute cooldown. It rewards poking about, and never blocks
  anything.
- **When a cycle finishes and is confirmed**, the Confirmed pose appears. That
  *is* the celebration. There's no steam puff, confetti or bounce; the pastie
  doesn't animate (§6.2).
- **At the 50th and 100th cycles**, the Guide entry unlocks, and the case file
  for that cycle (§8) carries one extra closing line.
- **The loading and empty states** have Dry-level lines: "Consulting the
  service…" while starting, and "No appliance yet. Pastie is ready to
  administer one." when there's no appliance.

### 7.8 The reactive aside keys

Each key has at least three authored variants, used in Dry and Departmental
modes only, and only at severity info or maintenance. The examples come from
SPEC §19.

| Key | When | Example |
|---|---|---|
| `estimate_unsettled` | the estimate is still settling | "The dryer currently believes 47 minutes remain. Pastie has elected not to contradict it." |
| `estimate_rose` | the remaining time went up since the last reply | "It said 39 min six minutes ago. It now says 47. Pastie has elected not to contradict it." |
| `reconnect_quiet` | a reconnect with nothing to report (about 1 in 20, §6.8) | "Nothing happened. This has simplified the paperwork considerably." |
| `idle` | occasionally while idle (§6.9) | "Pastie has nothing to report. This is generally considered a successful outcome." |
| `start_confirmed` | the paper trail reached CONFIRMED | "Three separate parties have now agreed that the dryer is on." |
| `remote_not_armed` | a start was wanted but the machine isn't armed | "The remote-control procedure currently contains a mandatory visit to the dryer." |
| `gap_recovered` | a completion was reconstructed from the cycle counter | "Pastie wasn't present, but the dryer kept minutes." |
| `unknown_state` | a raw value with no verified mapping | "Inventing an answer would be quicker. It would also be an answer Pastie made up." |
| `maintenance_due` | a maintenance counter is close | "The dryer has begun keeping records. This seems only fair, given what Pastie does for a living." |
| `finished` | a cycle finished | "Its part of the arrangement is complete." |
| `dryer_offline` | an ordinary offline state (not auth or service) | *(to be written)* |


### 7.9 Configurable personalities

Every personality in the cast, and how Pastie deals with each one, is
configurable by the owner. It's their house and their fiction. What can't be
configured is anything that would make Pastie less trustworthy.

**What each appliance's personality sheet holds**

| Setting | What it changes | Default |
|---|---|---|
| **Name** | what Pastie calls it ("the dryer", "Big Dave") in asides and narration | its appliance type |
| **Temperament** | which shipped line pools it draws on. Presets: *Diligent*, *Indecisive*, *Dramatic*, *Aloof*, *Weary*, *Cheerful*, plus *Custom* (only the owner's lines) | written from observed behaviour: the dryer is *Indecisive* |
| **Pastie's stance** | how Pastie reports and negotiates with it. Presets: *Professional*, *Deferential*, *Firm*, *Weary*, *Fond* | *Professional* |
| **Personality level** | Plain, Dry or Departmental for this appliance only, overriding the global level | follows the global level |
| **Lines** | per aside key and narration stage: disable a shipped line, add the owner's own lines, or replace a pool entirely | the shipped pools |
| **Meters** | the three joke meters: each label, and its curve (rising, peaking, late) | the shipped set for the programme (§7.5) |
| **Speech** | whether the personality reaches spoken announcements at all | off (SPEC §19 keeps speech restrained) |

**The Household** has a sheet too:
- how Pastie refers to them ("the Household", "the humans", or names)
- Pastie's stance towards them
- the owner's own lines

**Pastie itself** has a sheet for its own stance and a few signature lines. Its
role as the only narrator isn't configurable, because that's what keeps every
fact attributed to its source.

**As built (phase 5):** appliance sheets carry every field above. The
Household's and Pastie's sheets hold a name and their own lines. Their *stance*
is left out until something on screen would use it, because a setting that
changes nothing would mislead. Speech stays switched off, marked "needs a service
change" (§11, question 8). Pools are addressed by name, so a narration stage and
a reactive remark may never share one: the finished remark is `finished_aside`.

**The limits no configuration can cross.** These are enforced in the
presenter, not left to good behaviour:
1. **Facts never change.** A sheet only affects asides, narration, meter
   labels and names used inside asides. The facts line, the paper trail, stamps,
   "Why does Pastie say this?" and Diagnostics always use the appliance's real
   type and the plain wording.
2. **Warning, error and safety are always plain.** A custom line keyed to a
   fault or full tank is refused when saved, with the reason shown.
3. **Poses follow state, not personality.** No setting can produce the
   Confirmed pose without machine confirmation (Pastie's laws).
4. **Nothing is generated.** The owner's lines are authored by the owner and
   stored as written. Pastie never generates or rewrites them.
5. **Stored state stays canonical** (A15). Sheets are configuration, and the
   logs and history hold facts, never rendered lines.
6. **Length.** An owner's line over 160 characters is accepted, but flagged as
   too long for the hero at the minimum width.
7. **Borrowed catchphrases** (§7.1): the banned-term test applies to *shipped*
   copy. The owner's own lines get a gentle warning, never a refusal, since
   it's their house.

**Where it lives and how it travels**
- Sheets are stored by the window as one **personality pack** per appliance
  type, plus one for the Household and one for Pastie. Each pack is a
  human-readable file (TOML) in the window's own settings folder. Presentation
  config belongs to the window, never to the service.
- **Packs can be exported and imported**, so a household can share, for
  example, "Pastie, but it despises the projector". An imported pack is
  validated against the limits above. Anything invalid is dropped with a
  message, and the rest applies.
- **"Reset to default"** is available per sheet and per line pool.
- **An appliance that isn't verified yet** can be given a name and a sheet
  ahead of time. The sheet takes effect only once its type is verified; until
  then Pastie still declines to characterise it (§7.3).

**Tests** (added to §10.1):
- no sheet can change a fact, a stamp or a pose
- custom lines keyed to warning, error or safety are refused
- the Confirmed pose appears only on confirmed state, whatever is configured
- an imported pack with invalid entries applies its valid parts and reports the
  rest
- "Reset to default" restores the shipped pools exactly

---

## 8. The other places the voice lives

- **History** (the rail's clock icon). Its title is always **History**. In
  Departmental mode, the subtitle is **Case file**. Events read as compact
  evidence, with small stamps:

  ```
  18:02  Cycle started                  confirmed by dryer     [CONFIRMED]
  18:31  Remaining time changed 41 -> 47 min
  19:16  Cycle finished                 cycle counter 104 -> 105
  09:40  1 cycle completed while Pastie was offline             [RECOVERED]
         Last seen running 20:10 · completion time not known
  ```

  - Rows come from the service's recent events plus the window's own session
    observations. "Remaining time changed" is one of those, derived as in §5.5.
  - Messenger delivery rows ("Hue notified: delivered") need a service
    pass-through; see §11, question 2.
  - `[RECOVERED]` appears only when the cycle counter proves the completion. If
    it doesn't, the row keeps the uncertainty and carries no stamp.
  - **Clicking a cycle opens its case**, numbered by the dryer's own cycle
    counter (a real number, not an invented one). Every row is real data:

    ```
    CASE 000105                          Completion of drying operation

    Opened      18:02:11          Programme   Mixed
    Closed      19:16:43          Dryness     Ready to wear

    EVIDENCE
    18:02:11   Dryer reported RUNNING                    [CONFIRMED]
    18:31:04   Estimate revised 41 → 47 min
    19:16:41   Dryer reported FINISHED
    19:16:43   Cycle counter 104 → 105                   [CONFIRMED]

    ACTIONS TAKEN
    19:16:43   Living room light notified                [DELIVERED]
    19:16:44   Speaker announcement                      [DELIVERED]

    No further action is required by Pastie.
    Laundry-related responsibilities have now returned to their usual owner.
    ```

    - **Actions taken** appears only once the service passes delivery results
      through (§11, question 2). Until then the section is left out, not faked.
    - The closing two lines are Dry and Departmental only. Plain ends at the
      evidence.
    - If the cycle counter didn't move, the case says "Closed (not confirmed by
      counter)" and carries no `[CONFIRMED]` on the close.
- **Stamps** are the case-file marks used across the app, always as real text in
  small caps, on the cream "document" colour (§10.2):

  | Stamp | Means |
  |---|---|
  | `RECEIVED` | Haier accepted a request (not the same as done) |
  | `AWAITING APPLIANCE` | accepted, and waiting for the machine to confirm |
  | `CONFIRMED` | the machine's own state proves it |
  | `RECOVERED` | reconstructed after a gap, and evidenced by the counter |
  | `UNVERIFIED` | an appliance or value with no verified mapping |
  | `DELIVERED` | a messenger reported success (once passed through) |

- **Diagnostics** (discoverable from About and from the health dot). It makes
  the project's epistemology visible (SPEC §19):

  ```
  WHAT PASTIE KNOWS            Last reading 19:02 · verified
                               Programme: Mixed · verified
                               Remaining time: 43 min · reported by the appliance
  WHAT PASTIE IS INFERRING     Remaining-time estimate settled: yes
  WHAT PASTIE WILL NOT GUESS   Raw state 6 · no verified mapping
  ```

  Everything here comes from the trust level and raw values the service
  already sends. The headings are the same in every mode, because the joke is
  that they're simply accurate.

- **About.** The full crest (§10.4), the version, the licence and the
  "unofficial" statement. In Departmental mode it adds the institution and the
  real architecture as a formal organisation chart:

  ```
  PASTIE
  Practical Appliance Supervision, Telemetry & Interoperability Executive
  (The acronym was developed considerably later than the name.)

  Domestic Appliance Liaison Division

  Connector       translates what Haier said
  Brain           decides what actually happened
  Messengers      bother something else about it
  App             tells you what everybody is doing
  ```

  Release notes come from `CHANGELOG.md`, headed **Minutes of recent
  proceedings** in Departmental mode. The version numbers and changes stay as
  written.

- **Onboarding** (first run, when there's no saved account). Four steps: connect
  the Haier account, find appliances, choose how Pastie tells you things, test
  one messenger. The last step has to produce a real, visible success. Any
  personality goes in the supporting text only, never in buttons or required
  instructions, and the account step is plain (§7.1).

- **Speech and other messengers** are out of this spec's scope. They're
  governed by SPEC §19, "Finished notifications", which says spoken
  announcements use fewer variants than the window. The window's personality
  level doesn't change what a speaker says.

---

## 9. Settings, restyled

- **Split into sections in the rail's Settings page:** Account, Notifications
  (one card per messenger), **Personalities** (one sheet per cast member, §7.9),
  Appearance (global personality level, theme, reduced motion) and About.
- **Standard names stay standard.** Notifications are called Notifications, and
  settings are findable by their ordinary names (SPEC §19, "Settings").
  Personality lives only in section subtitles, empty states and test-result
  messages, at Dry or Departmental level.
- **The Account card** is plain in every mode (§7.1). Its wording is unchanged
  from today: it's accurate and it reassures.
- **Messenger cards** are still generated from each messenger's declared
  settings (SPEC §8), now as a card with a header toggle and a **Test** button
  that shows its result inline.
- **Per-alert overrides** become a small table: alert rows × the messenger's
  per-alert settings as columns, with "(default)" shown in place of blank. That
  fixes 2.6.
- **Every input is styled:** no white system fields. The Hue light picker keeps
  choosing by name, not id (an existing tested rule).

---

## 10. Visual system, tests and accessibility

### 10.1 Tests for the delight layer

From SPEC §20, and required before phase 4 ships:
- Plain, Dry and Departmental modes expose the same canonical facts
- anything with warning, error or safety severity has no aside, no joke meter
  and no amused expression, in any mode
- nothing is called successful before the machine confirms it
- a repeated render keeps the same aside for the same event ID
- the window's state file and the service log hold canonical facts, not
  rendered wording
- an unknown or unverified state never gains an interpreted description
- every screen still makes sense with every aside removed
- no shipped copy contains a borrowed term (§7.1)
- the configurable-personality tests in §7.9

### 10.2 Visual system

- **The colour language comes from the crest**, and each colour has one job:

  | Colour | Job | Starting value |
  |---|---|---|
  | **Navy** | the ordinary working surface (background and cards) | `#0f1422` background, `#171e30` card, sampled from the crest at build |
  | **Gold** | acknowledged, confirmed, official: the Confirmed pose, `CONFIRMED` stamps, the ring when finished, primary actions | `#e0a03c` (the existing crust) |
  | **Cream** | documents and evidence: the paper trail, case files, "Why does Pastie say this?" panels and stamps | `#f3ead8` background with `#2a2418` ink |
  | **Text and muted** | everything else | `#eef1f6`, `#8994a5` |
  | **Red** | faults and actions that need doing, and nothing else | `#e2664f` |

  **There are no generic green ticks.** Certainty is shown by gold and stamps,
  and state by words and poses. Green, blue and grey become small state
  accents only, always paired with a word. Contrast is checked to WCAG AA for
  body text in both themes, including ink on cream. A light theme keeps the same
  jobs.
- **Type:** Segoe UI Variable (system, so no font files and no network). Three
  sizes for text (13, 15, 20 px) plus a display size for the percentage (44 px,
  tabular figures). Stamps use small caps.
- **Shape:** 12 px corners on cards and 8 px on controls. One elevation step.
  The pastie's amber is the only strong colour apart from state colours.
- **Motion:** 150–250 ms ease-out for interface changes, 600 ms for meters, and
  continuous motion only for the drum while running. **Respects "reduce motion"**
  (both Windows' setting via `prefers-reduced-motion` and the in-app toggle).
  With reduced motion, the drum is still and changes happen instantly.
- **Icons:** one small inline SVG set for the rail and the programme tiles. No
  icon fonts, no CDN.

### 10.3 Accessibility

- Every state is conveyed by words, not only by colour, the pastie's face or a
  stamp.
- Keyboard: tab order follows the layout, the programme tiles use arrow keys,
  and Enter starts once a programme is chosen. Visible focus ring.
- Screen readers: the facts line is an `aria-live="polite"` region, so a state
  change is announced once. Asides and narration aren't live, to avoid chatter.
  The meters and stamps have text values.
- The window respects Windows' text scaling. Layouts are tested at 100 %, 150 %
  and 200 %.

### 10.4 Identity: one crest, three levels of detail

The supplied crest is too detailed to survive at small sizes: the chips, arms,
circuit traces and face collapse at 32 × 32. So there are three tiers of the same
identity:

| Tier | What | Used for |
|---|---|---|
| **Hero** | the full crest as supplied: pastie, chips, house, circuits, shield | About, onboarding, the service-down and empty screens |
| **App icon** | the shield, a simplified pastie face, and two circuit traces | the window, taskbar, Start menu and Desktop shortcuts (replaces the burger photo, 2.10) |
| **Tray glyph** | only the pastie silhouette inside a minimal house or shield outline | reserved for a tray icon, which isn't in this spec (§11, question 4). Defined now so the family is complete |

- The app icon must stay legible at 16, 24, 32 and 48 px (A18).
- The six poses (§6.2) are drawn from the same character as the crest.
- The asset files live in `assets/brand/`. The crest moves there from `docs/`
  at build time.

---

## 11. Open questions for the audit

1. **The README lore** ("Why a pastie?") used two names from Adams's books, a
   corporation and its product, plus a "never panics" line. That goes against
   SPEC §17, voice rule 6. *Resolved in revision 2: the README section now uses
   original names.* It's docs only, so it's done now, not at build.
2. **Four things need the service to pass through data it already holds:**
   - messenger delivery results (the case file's Actions taken, and `DELIVERED`)
   - the most-used programme (Haier's statistics)
   - appliance presence (the Dryer row in §6.6; the service already subscribes
     to Haier's connected and disconnected events)
   - the programme's total length (the "Why…" settled explanation in §6.7
     quotes it; it's already computed in the connector)

   That's a service change, and out of this spec's scope. *Proposed: ship
   without them, leaving each section out rather than faking it, and add all
   four through one separate, small SPEC change.*
3. **A frameless window with a custom title bar, or the native title bar?**
   Frameless looks slicker but has to reimplement dragging, snap and the window
   buttons. *Proposed: the native title bar, with its colour set to the dark
   theme through the Windows DWM API.*
4. **Should the tray icon come now?** It would let the window close to the
   tray. It's a separate dependency (`pystray`), and the service already runs
   without the window. *Proposed: not in this spec.*
5. **Sound?** A soft "done" chime while the window is open. *Proposed: no. The
   messengers already do announcements, and SPEC §19 wants spoken copy kept
   more restrained than written copy.*
6. **Who makes the art?** The six poses and the two simplified tiers are new
   drawings of the supplied character. *Proposed: the owner generates them from
   the crest with the same tool that made it, to the brief in UI-SCREENS §10.
   The app icon tier could instead be hand-built as SVG from the crest's shapes,
   which keeps it crisp at every size. The owner should also confirm they're
   content for AI-generated art to ship in an MIT-licensed public repository,
   under that tool's terms.*
7. **Non-Haier appliances: the smart projector (on its way) and solar panels.** Pastie's service talks
   only to Haier's hOn today, through one connector (SPEC §4). The projector and
   the panels would each need their own connector, and SPEC §3's "we use pyhon-revived" decision would
   become "one connector per source". *Proposed: this spec only guarantees the
   window is ready for more than one source (§6.10). The connector change is its
   own SPEC revision, written when each device is real.*
8. **Should personality reach speech?** §7.9 has a per-appliance Speech switch,
   off by default. Speech belongs to the messengers (SPEC §19), so the switch
   would need the service to read the window's packs, or have a copy of them.
   *Proposed: the switch exists in the sheet but stays disabled, marked "needs a
   service change", until a separate SPEC change decides how packs reach the
   service.*

---

## 12. Build order

Each phase ships on its own and leaves the app working. **Nothing is built
until this spec is approved.**

1. **Presenter first, in Tk.**
   - Extract `presenter.py` with ScreenState and SPEC §18's message shape, and
     move `ordeal.py` into it.
   - **Fix 2.9:** remove the 42, make the fault and tank lines plain, and put the
     fact first on unknown states.
   - Add the personality level setting, with Dry as the default.
   - Fix 2.3 and 2.4 in the current Tk window.
   - This phase is worth shipping even if nothing else happens.
2. **The web shell at parity.**
   - pywebview window, the §5.3 rules and the A7 test.
   - Main screen, paper trail and settings rendering the ScreenState.
   - Tk window deleted in the same change (§5.4).
3. **The character and identity.** The crest tiers (§10.4), the six poses, the
   ring, meter animation and reduced motion, built screen by screen from
   [UI-SCREENS.md](UI-SCREENS.md).
4. **The voice everywhere.** Reactive asides (§7.8), Departmental narration
   pools (§7.4), History and case files, Diagnostics, "Why does Pastie say
   this?", connecting and reconnecting (§6.8), About, the Guide and small
   delights, plus the §10.1 tests.
5. **Configurable personalities** (§7.9). Personality sheets and packs, the
   Personalities settings page, import, export and reset, and their tests.
   It comes after phase 4, because it configures pools that phase 4 builds.
6. **Onboarding, light theme, accessibility pass.**

---

## 13. Acceptance criteria

| # | Criterion | How it's checked |
|---|---|---|
| A1 | The state is readable from 3 m at 100 % scaling: the state word and ring percentage are at least 20 px and 44 px | Screenshot review |
| A2 | No white system widgets in either theme | Screenshot review of every screen |
| A3 | Every fact the old window showed is still shown (programme, remaining, attention, fault, maintenance due, health, command lifecycle, armed state, per-programme options) | Checklist against `main.py` before deletion |
| A4 | The honest number is always visible when known, and nothing claims progress when it isn't | Presenter tests |
| A5 | Anything with warning, error or safety severity carries no aside, no joke meter and no amused expression, at any personality level | Presenter tests (§10.1) |
| A6 | No Departmental narration line repeats within 30 looks of the same stage, and a given event keeps its aside across redraws | Presenter tests (§7.4) |
| A7 | The window process has no listening socket | CI test on the Windows runners (§5.3) |
| A8 | The page makes no network request: the CSP includes `connect-src 'none'`, and the bundle contains no `http(s)://` URL except documentation links opened in the default browser | CI grep plus CSP check |
| A9 | Plain, Dry and Departmental show the same canonical facts. Plain shows no asides, no joke meters and no amused expressions | Presenter tests (§10.1) |
| A10 | Reduced motion stops the drum and removes animations | Manual check, both settings |
| A11 | Opens in under 1.5 s on this PC, and uses under 1 % CPU while idle | Measured, recorded in the handover |
| A12 | pywebview is pinned in `pyproject.toml` and `constraints.txt`, and `THIRD_PARTY_NOTICES.txt` is regenerated in the same change | CI licence-notices job |
| A13 | Unverified appliances get names, raw values and the fact-first unknown-state wording, never an interpreted description, a joke meter or an expression beyond neutral | Presenter test |
| A14 | No copy anywhere contains a borrowed term (§7.1) | Presenter test over every pool, label and Guide entry |
| A15 | Stored state (the window's file, the service log) holds canonical facts, never rendered asides | Test |
| A16 | The Confirmed pose and every `CONFIRMED` stamp appear only on machine-confirmed state | Presenter test over every command and event path |
| A17 | Every "Why does Pastie say this?" explanation is built from the real rule and inputs, and the settled explanation matches `connector/reading.py`'s test | Presenter test |
| A18 | The app icon is legible at 16, 24, 32 and 48 px | Screenshot review at each size |
| A19 | Connecting lines follow the observable stages in §6.8, never a timer | Presenter test |
| A20 | No personality configuration can change a fact, a stamp, a pose's link to real state, or the plainness of warning, error and safety messages | Presenter tests (§7.9) |
| A21 | Personality packs round-trip: export, import and reset give back exactly what was saved or shipped | Test |

---

## Sources

- SPEC.md §17–20: the delight contract, the copy architecture, where the
  personality lives, and earned delight (audit round 1, 2026-09-25).
- pywebview API reference: `http_server`, `private_mode`, `frameless`,
  `background_color`, `min_size`, `js_api`, and which options are Windows-supported.
  <https://pywebview.flowrl.com/api/>
- pywebview project. <https://github.com/r0x0r/pywebview>
- Which Python GUI library should you use in 2026? <https://www.pythonguis.com/faq/which-python-gui-library/>
- Mailchimp Content Style Guide, voice and tone. <https://styleguide.mailchimp.com/voice-and-tone/>
- The supplied crest: `docs/ChatGPT Image Sep 25, 2026, 01_51_56 PM.png`
  (audit round 2).
- CARROT Weather, a precedent for user-selectable personality levels in a
  serious utility. <https://support.meetcarrot.com/weather/>
- How to use comedy in UX writing. <https://blog.dailyuxwriting.com/how-to/use-comedy-ux-writing/>
- UX Content Collective, error messages. <https://uxcontent.com/how-to-write-error-messages/>
