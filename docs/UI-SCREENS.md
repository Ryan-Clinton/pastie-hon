# Pastie — screen by screen

Status: **draft, revision 1, for audit** (added in audit round 2). This is
[UI-SPEC.md](UI-SPEC.md) turned into screens you can build one at a time. The
rules live in UI-SPEC and in SPEC §17–20. This document only applies them. Where
this and UI-SPEC disagree, UI-SPEC wins, and the disagreement is a bug here.

**How to read each screen:**
- **Pose** is one of the six in UI-SPEC §6.2.
- **Facts** are plain and identical at every personality level.
- The **Plain / Dry / Departmental** rows show only what the personality level
  adds on top of the facts. "—" means nothing is added.
- Every example value is illustrative. The real values come from the service,
  and nothing on these screens is invented.

---

## 1. The main window: the caseload and the hero

```
┌──────────────────────────────────────────────────────┐
│ [icon] Pastie                       ● Working normally │
├────┬─────────────────────────────────────────────────┤
│ ⌂  │ CURRENT CASELOAD            (Departmental only)  │
│ 🕘 │ [Tumble dryer · RUNNING] [Washer · FINISHED]     │
│ 📖 ├─────────────────────────────────────────────────┤
│ ⚙  │            ╭──── ring ────╮                     │
│ ?  │            │   [pose]     │     54%             │
│    │            ╰──────────────╯                     │
│    │ Tumble dryer                      RUNNING       │
│    │ Mixed / Ready to wear                           │
│    │ Estimated completion 14:37 · about 47 min ·     │
│    │ still estimating  (?)                           │
│    │                                                 │
│    │ <aside, per level>                              │
│    │ <meters, Departmental only>                     │
│    ├─────────────────────────────────────────────────┤
│    │ <actions: Waiting for Remote mode / Start / Stop>│
└────┴─────────────────────────────────────────────────┘
```

With one appliance, the caseload row is a single chip. The hero is always the
most urgent appliance (UI-SPEC §6.10).

---

## 2. The hero, state by state

### 2.1 Idle, not armed

| | |
|---|---|
| Pose | Normal |
| Facts | Tumble dryer · IDLE |
| Actions | **Waiting for Remote mode** (disabled). Beside it: "Remote start is unavailable. Turn the programme dial to Remote on the dryer first." |
| Plain | — |
| Dry | "No active proceedings." Next to the button: "The remote-control procedure currently contains a mandatory visit to the dryer." |
| Departmental | "No domestic machinery currently requires intervention." Same line next to the button. |

### 2.2 Idle, armed

| | |
|---|---|
| Pose | Normal |
| Facts | Tumble dryer · IDLE · Ready for remote start |
| Actions | The Start panel (§3.1) |
| Plain | — |
| Dry | "No active proceedings." |
| Departmental | "The dryer has made itself available. Pastie awaits the Household's instructions." |

### 2.3 Running, still estimating

| | |
|---|---|
| Pose | Working |
| Facts | RUNNING · Mixed / Ready to wear · Estimated completion about 14:37 · about 47 min · still estimating (?) · ring shows 54 % |
| Actions | **Stop** (secondary style) |
| Plain | — |
| Dry | Only if the estimate went up since the last reply: "It said 39 min six minutes ago. It now says 47. Pastie has elected not to contradict it." Otherwise nothing. |
| Departmental | The estimate line above if it rose. Otherwise "The dryer currently believes 47 minutes remain. Pastie has elected not to contradict it." Plus three meters for the programme. |

If there's no progress figure at all, the ring shimmers, the facts say "Still
estimating", the pose is **Waiting**, and there are no meters.

### 2.4 Running, settled

| | |
|---|---|
| Pose | Working |
| Facts | RUNNING · Mixed / Ready to wear · Estimated completion 14:37 · 32 min · settled (?) · ring shows 71 % |
| Plain | — |
| Dry | — (nothing notable has happened) |
| Departmental | A narration line from the running-late pool, plus meters. |

### 2.5 Paused

| | |
|---|---|
| Pose | Waiting |
| Facts | PAUSED · Mixed · 32 min remaining when paused |
| Plain / Dry / Departmental | — / — / a line from the paused pool |

### 2.6 Full tank (warning: plain at every level)

| | |
|---|---|
| Pose | Fault |
| Facts | PAUSED · **The water tank is full, so the dryer has stopped. Empty it and press start.** |
| Every level | Nothing added. No meters. |

### 2.7 Fault (error: plain at every level)

| | |
|---|---|
| Pose | Fault |
| Facts | FAULT · **The dryer has reported a fault and stopped. Check the machine's display.** · Fault code E3 (?) |
| Every level | Nothing added. No meters. |

### 2.8 Finished

| | |
|---|---|
| Pose | **Confirmed**, only if the finish is evidenced by the state change and the cycle counter. Otherwise Normal |
| Facts | FINISHED · Mixed · at 19:16 (?) · ring complete in gold |
| Plain | — |
| Dry | "Its part of the arrangement is complete." (the first finish of the day only; later finishes get nothing, per the repetition rules) |
| Departmental | One from the `finished` pool, e.g. "The machine is finished. The clothes have been transferred to your department." |

### 2.9 Unknown or unverified

| | |
|---|---|
| Pose | Unknown |
| Facts | STATE UNKNOWN `UNVERIFIED` · "Pastie has data, but no verified mapping for what this appliance means by it." · raw values, in Diagnostics (?) |
| Plain | — |
| Dry / Departmental | "Inventing an answer would be quicker. It would also be an answer Pastie made up." |

### 2.10 Where matters currently stand (the service, internet, account or schema has a problem)

The hero is replaced by the layer panel from UI-SPEC §6.6. **Pose: Fault.**

| Health | The layer that fails | What to try |
|---|---|---|
| no reply | Pastie service: NOT RUNNING | "Start Pastie's background service. Alerts don't work until it's running." |
| offline | Internet: NOT REACHABLE | "Check this PC's internet connection." |
| auth | Haier account: CAN'T LOG IN | "Check your hOn password in Settings → Account." |
| schema | Haier's response: NOT UNDERSTOOD | "Haier has changed something and Pastie needs an update. Alerts may be unreliable until then." |
| slow | none: this is a header note only, with "Working, but updates are slow" | — |

**All plain at every level.** The only aside on this screen is the three-line
"The internet is present. Haier is present. The dryer, presently, is not.",
shown when the service, internet and account are all known to be fine and only
the dryer isn't reporting (Dry and Departmental).

### 2.11 Connecting and reconnecting

These are the observable stages from UI-SPEC §6.8, shown in the hero with the
**Waiting** pose. Plain shows "Connecting…" and "Reconnected" only.

---

## 3. Starting a cycle

### 3.1 The Start panel (armed and idle)

```
START A CYCLE

[Cotton] [Synthetics] [Mixed] [Towels] [Sports] [Timer]
[Duvet]  [Wool] [Delicates] [Quick dry] [Refresh]          ← tiles, dial order

Dryness      [Iron dry] [Cupboard] [Ready to wear ★]
Temperature  [Low] [Middle] [High ★]
Time         Until dry                                     ← locked chip when fixed

                                    [ Start Mixed ]
```

- The button names the programme ("Start Mixed"). Controls stay literal.
- A ★ marks the programme's recommended setting, pre-selected.
- A fixed setting shows as a locked chip labelled "(fixed)".

### 3.2 The paper trail (it replaces the Start panel until a final state)

| Step | Pose | Trail line | Stamp |
|---|---|---|---|
| Requested | Working | 20:41:02 Requested | — |
| Haier accepted | Working | 20:41:03 Haier accepted the request · "Waiting for dryer…" | `RECEIVED`, then `AWAITING APPLIANCE` |
| Machine confirmed | **Confirmed** | 20:41:06 Dryer confirmed RUNNING | `CONFIRMED` |
| Not confirmed within 20 s | Fault | the plain COMMAND NOT CONFIRMED panel (UI-SPEC §6.5) | — |
| Haier rejected | Fault | "Haier refused the request." plus the reason in its words | — |
| Refused before sending | Normal | e.g. "The dryer ignores Duvet when it's started remotely…" (not for the dial programmes), or "Not armed…" | — |

After CONFIRMED, Dry and Departmental may add "Three separate parties have now
agreed that the dryer is on." The first time only; later confirmations get
nothing, per the repetition rules.

### 3.3 Stop

"Stop the Mixed cycle?" appears inline with **Stop it** and **Keep running**.
It needs a second click within 5 seconds. The paper trail then shows the same
lifecycle, confirmed by the machine leaving RUNNING.

---

## 4. History and the case file

- **The list** is newest first, one row per event, with stamps. It's titled
  **History**, and in Departmental mode the subtitle is **Case file**. The rows
  are as in UI-SPEC §8.
- **A cycle row opens its case** (UI-SPEC §8): CASE number from the cycle
  counter, Opened and Closed times, programme, EVIDENCE, and ACTIONS TAKEN (only
  once passed through), then the closing lines for Dry and Departmental.
- **Empty state:** Plain "Nothing yet." · Dry "No proceedings on record yet." ·
  Departmental "The case file is empty. Pastie finds this suspicious, but
  cannot prove anything."

---

## 5. Diagnostics

The layout is fixed and identical at every level, because the headings are the
joke only in the sense that they're accurate:

```
WHAT PASTIE KNOWS
  Last reading                   19:02:11  verified
  State: RUNNING                 verified
  Programme: Mixed               verified
  Remaining: 43 min              reported by the appliance

WHAT PASTIE IS INFERRING
  Estimate settled               yes   (remaining 43 ≤ programme total 120)
  Cycle counter                  105

WHAT PASTIE WILL NOT GUESS
  Washer · raw state 6           no verified mapping          UNVERIFIED
```

Each row has a (?) that opens the same "Why does Pastie say this?" panel as the
main screen (UI-SPEC §6.7).

---

## 6. The Guide

- A list of entries in two groups, **Unlocked** and **Not yet**. Locked entries
  show their title, the plain condition ("Unlocks at the first full-tank
  alert") and nothing else. There are no teasers that make you want to cause a
  fault.
- An entry page has the title, the text in the voice, and a plain real-data
  footnote ("Cycles observed: 17 · Filter due in 15").
- In Plain mode, only the footnotes and the facts are shown.

---

## 7. Settings

### 7.1 Account (plain at every level)

The fields and wording are as today, restyled. The status reads "An account is
saved" or "No account saved". It never shows the password.

### 7.2 Notifications (one card per messenger)

- **The card title is the messenger's name**, and the section is called
  **Notifications**, not anything cleverer.
- A header toggle turns the messenger on or off. The fields are drawn from what
  the messenger declares, and the **Test** button shows its result inline.
- **Test results:**
  - Success: the messenger's own report, e.g. "Sent. The living room light flashed green for 18 s." Dry and
    Departmental add "It reports no objections."
  - Failure: the plain reason, with no aside.
- **Per-alert overrides** are a table: alert rows × settings columns, showing
  "(default)" where no override is set.

### 7.3 Personalities

One card per cast member: each appliance, the Household and Pastie. Every card
has three parts:

```
TUMBLE DRYER                                   [Reset to default]
Name             [ the dryer          ]
Temperament      [Indecisive ▾]      Pastie's stance  [Professional ▾]
Personality      [Follow global ▾]   Speech           (needs a service change)

LINES                                          [Show shipped lines]
  estimate_rose   3 shipped · 1 yours · 0 disabled      [Edit]
  finished        4 shipped · 0 yours                    [Edit]
  running-late    12 shipped · 2 yours · 1 disabled      [Edit]
  (fault, full tank: plain by rule, and not editable)

METERS           Crispiness (rising) · Existential dread (peaking) · …  [Edit]

PREVIEW  [Running ▾] [Departmental ▾]
  <the hero as it would look, with this sheet>
```

- **Editing a pool** lists every line with an on/off switch. The owner's lines
  are added in a text box and checked against UI-SPEC §7.9's limits as they're
  typed. Over-long lines and borrowed terms get a warning; lines keyed to
  warning, error or safety are refused, with the reason.
- **The preview** renders any state at any level with the sheet as it stands,
  before anything is saved.
- **Import pack…** and **Export pack…** sit at the top of the page. An import
  reports exactly what it applied and what it dropped.
- An unverified appliance's card is available and editable, and is marked
  "Takes effect once this appliance is verified."

### 7.4 Appearance

- **Personality:** Plain / Dry (default) / Departmental. There's one example
  line under each option, showing the same event in that level's voice.
- **Theme:** Follow Windows / Dark / Light.
- **Reduce motion:** Follow Windows / On.

---

## 8. Onboarding (first run, no saved account)

| Step | Screen | Pose | Supporting line (Dry and Departmental only) |
|---|---|---|---|
| 1 | Connect your Haier account (plain form) | Normal | — (the account is plain) |
| 2 | Finding appliances… then the list, each with its state and a `UNVERIFIED` stamp where it applies | Working | "Pastie is introducing itself to the household machinery." |
| 3 | Choose how Pastie tells you things: pick messengers | Normal | "Pastie will need someone to carry messages." |
| 4 | Test one messenger: it must produce a real, visible success | **Confirmed** (only on a real delivery) | "The chain from appliance to Household is complete." |

The hero crest is at the top of step 1. Buttons are literal: "Connect",
"Continue", "Send a test".

---

## 9. About

- **At every level:** the hero crest, "Pastie", the version, the MIT licence,
  "Unofficial. Not affiliated with, endorsed by, or supported by Haier.", and
  links to the repository and the changelog.
- **Departmental adds:** the full institution name, "(The acronym was developed
  considerably later than the name.)", the organisation chart (UI-SPEC §8),
  and release notes headed **Minutes of recent proceedings**.
- A **Diagnostics** link is at every level.

---

## 10. Art brief (for UI-SPEC §11, question 6)

These are made from the supplied crest, keeping the same character, colours and
rendering.

| Asset | Brief |
|---|---|
| **Pose: Normal** | The crest's pastie, mild smile, arms relaxed, on the chips. No thumbs-up. |
| **Pose: Working** | Holding a tiny clipboard, eyes on it, pen in the other hand. Concentrating, not stressed. |
| **Pose: Waiting** | Glancing sideways at a small wristwatch on the robot arm. Patient. |
| **Pose: Confirmed** | The crest's thumbs-up, exactly as supplied. |
| **Pose: Unknown** | Peering closely at a sheet of paper, one eyebrow slightly raised. |
| **Pose: Fault** | Neutral and attentive. Looking straight out, no smile, no comedy. Arms still. |
| **App icon** | The shield outline and a simplified pastie face, with no chips, arms or house, and two short circuit traces. Flat enough to read at 16 px. SVG preferred. |
| **Tray glyph** | The pastie silhouette only, inside a minimal house or shield outline. One colour. Reserved; not built in this spec. |

Every pose is delivered at the same canvas size and framing on a transparent
background, so a crossfade between them doesn't shift.
