# Pastie — design specification

Turning a working single-appliance script collection into a maintainable framework:
all hOn appliances, pluggable lighting, voice assistants, and credentials handled
properly.

Status: **proposal**. Nothing here is built yet. Written 2026-08-30 against the
working prototype at commit `fa259dc`.

---

## 1. Why change anything

The prototype works and should not be thrown away. But it has structural limits
that will bite as soon as a second appliance or a second light brand appears:

| Problem | Consequence |
|---|---|
| Everything assumes `appliances[0]` and a tumble dryer | A second appliance breaks it |
| Hue is hard-wired as *the* notifier | No other lighting, no other channels |
| Credentials sit in plaintext `.credentials` | Anyone with file access has the hOn account |
| GUI and daemon poll the cloud independently | Double the API load; the two can disagree |
| Config split across three files, two formats | No single source of truth |
| No tests, no packaging | Every change is a manual regression hunt |
| 120-second polling | Alerts up to two minutes late |

None of these are urgent. All of them get harder to fix later.

---

## 2. Principles

1. **The appliance still works if all this dies.** Never take an action that
   depends on our software for the machine to function.
2. **Local beats cloud where a choice exists.** Hue is local; hOn is not. Prefer
   the local path and degrade gracefully when the cloud is unreachable.
3. **Capability-driven, not model-driven.** Ask the appliance what it can do;
   don't hardcode a dryer.
4. **Verify writes by reading back.** hOn's `.send()` returning `True` means the
   *cloud* accepted it, not the machine. This is already a documented trap.
5. **Don't rebuild what a vendor gives free.** hOn already has official Google
   Home and Alexa integrations. Building our own is worse and more fragile.

---

## 3. Target architecture

```
pastie/
├── core/
│   ├── appliance.py       capability model, normalised state
│   ├── events.py          event bus
│   └── rules.py           trigger -> action engine
├── providers/
│   ├── base.py            Provider ABC
│   └── hon.py             pyhOn wrapper (all 16 appliance types)
├── notifiers/
│   ├── base.py            Notifier ABC
│   ├── hue.py             CLIP v2
│   ├── cast.py            Google Cast TTS
│   └── ...                lifx, wiz, ntfy, telegram, webhook
├── config/
│   ├── store.py           settings (JSON, versioned, migratable)
│   └── secrets.py         keyring-backed credential store
├── daemon/
│   ├── service.py         the only thing that talks to providers
│   └── api.py             localhost HTTP for clients
└── ui/
    └── desktop.py         thin client over the daemon API
```

### 3.1 The single-daemon rule

Today the GUI and the background service both authenticate to hOn and both poll.
That doubles cloud load, and they can report different states at the same moment.

**One daemon owns all provider connections.** It exposes a small HTTP API on
`127.0.0.1` — state, commands, config, and an SSE stream for live updates. The
desktop app becomes a client. So does anything else later: a phone-friendly web
page, a CLI, a Home Assistant integration.

Bind to loopback only. No authentication needed at first, but the API should be
designed so adding a token later is not a rewrite.

### 3.2 Capability model

Rather than "this is a dryer, so it has `dryLevel`", derive capability at runtime:

```python
@dataclass
class Capability:
    key: str                    # "dryLevel"
    kind: Literal["enum", "range", "bool", "readonly"]
    label: str                  # "Dryness"
    values: dict | tuple | None # {12: "Iron dry", ...} or (min, max)
    writable: bool
```

`discover.py` already produces everything needed for this. The UI renders from
capabilities, so a dishwasher gets a dishwasher's controls with no new UI code.

Type-specific knowledge (the `machMode` and `dryLevel` maps) lives in per-type
descriptor files, not in the UI:

```
descriptors/
├── common.yaml     machMode, errors, doorStatus - shared across types
├── TD.yaml         tumble dryer
├── WM.yaml         washing machine
└── ...             DW, REF, FRE, OV, IH, MW, HO, AC, AP, WD, WC, WH, RVC, AS
```

Known types from `pyhOn`: `AC` air conditioner, `AP` air purifier, `AS` air
scanner, `DW` dishwasher, `FRE` freezer, `HO` hood, `IH` induction hob, `MW`
microwave, `OV` oven, `REF` fridge, `RVC` robot vacuum, `TD` tumble dryer,
`WC` wine cellar, `WD` washer-dryer, `WH` water heater, `WM` washing machine.

Only `TD` is validated. Every other descriptor ships marked **unverified** until
someone runs it against real hardware.

---

## 4. Notifiers

### 4.1 Interface

```python
class Notifier(ABC):
    id: str                     # "hue"
    name: str                   # "Philips Hue"

    @abstractmethod
    def config_schema(self) -> list[Field]: ...   # UI renders from this
    @abstractmethod
    async def test(self, cfg: dict) -> Result: ...
    @abstractmethod
    async def fire(self, event: Event, cfg: dict) -> Result: ...
    @abstractmethod
    async def discover(self) -> list[Target]: ...  # lights, speakers, etc.
```

The settings UI is **generated** from `config_schema()`. Adding LIFX support
should not touch the UI at all.

Notifiers register through Python entry points, so a third party can ship one as
a separate package.

### 4.2 Philips Hue — migrate to CLIP v2

The prototype uses API v1 over plain HTTP. That has a deadline: under RED
compliance, new bridge firmware no longer supports HTTP, and the API must be
reached over TLS. v1 also cannot do what v2 does.

| | v1 (current) | v2 (target) |
|---|---|---|
| Transport | HTTP | HTTPS, self-signed bridge cert |
| Auth | username in URL path | `hue-application-key` header |
| Updates | poll | **Server-sent events** at `/eventstream/clip/v2` |
| Addressing | integer ids | stable UUIDs |
| Scenes, rooms, zones | limited | first-class |

Work required:

- Bridge discovery via mDNS, falling back to the discovery endpoint
- Certificate handling — the bridge presents a self-signed cert; pin the bridge
  ID rather than disabling verification outright
- Re-pair to obtain a v2 application key (link-button flow, as before)
- Address lights, **groups, rooms and zones** — "flash the whole kitchen"
- Scene activation as an alert type
- Subscribe to the event stream so the app reflects lights changed elsewhere

Decide once whether to carry a v1 fallback for pre-v2 bridges at all.
Supporting both doubles the surface area of the least interesting code in
the project; dropping it excludes anyone on old hardware.

### 4.3 Other lighting

The abstraction should be **"a controllable light target"**, not "a Hue light".
Candidates, in rough order of effort:

- **LIFX** — local UDP protocol, no hub, well documented
- **WiZ** — local UDP JSON, cheap bulbs, trivial protocol
- **Tuya / Smart Life** — local key extraction needed; awkward but very common
- **Nanoleaf** — local HTTP API
- **Home Assistant** — one adapter reaches *everything* HA supports

That last one deserves emphasis. A single Home Assistant notifier gives access to
hundreds of device integrations for a fraction of the effort of writing them
individually. It is probably the highest-value item on this list.

### 4.4 Non-light notifiers

Same interface, no lighting involved:

- **Google Cast TTS** — exists; move behind the interface
- **ntfy / Gotify** — self-hosted push to phone, trivial HTTP
- **Telegram bot** — push with no infrastructure
- **Webhook** — generic escape hatch for anything else
- **Windows toast** — local desktop notification
- **Email** — for fault conditions rather than cycle completion

---

## 5. Voice assistants

### 5.1 Recommendation: do not build these

hOn already ships **official Google Home and Alexa integrations**, configured in
the phone app under Settings → *Configure Smart Home Speakers*. They are free,
maintained by Haier, and survive our project being abandoned.

A bespoke Alexa Smart Home skill requires an AWS Lambda function, an OAuth 2.0
authorisation server, account linking, and a public HTTPS endpoint — for
functionality the vendor already provides.

**Where the official integrations fall short**, and where we can add value:

| Need | Official | Us |
|---|---|---|
| Start / stop by voice | yes | not needed |
| Status on request | yes | not needed |
| **Proactive "it's finished"** | **no** — Haier's docs state you must ask | **yes** |
| Fine-grained programme control | limited | yes |
| Cross-vendor automation | no | yes |

### 5.2 If voice control is still wanted

Expose the daemon to **Home Assistant** rather than to assistants directly. HA
already solves Google Assistant and Alexa (and Matter, and HomeKit). One
integration, all assistants, none of the OAuth infrastructure.

Two options:

- **MQTT discovery** — publish to an MQTT broker in HA's discovery format.
  Zero-code on the HA side, works with any broker.
- **Custom component** — a thin HA integration talking to the daemon's local API.

MQTT discovery is the lower-effort path of the two.

### 5.3 Important constraint

`remoteCtrValid` gating is enforced in appliance firmware. **No integration —
ours, Haier's, or anyone's — can start a cycle that has not been armed at the
panel.** Any voice feature must be designed around semi-attended operation.
Document it prominently rather than letting users discover it.

---

## 6. Credential management

### 6.1 Current state

Plaintext `.credentials`, holding the hOn email and password and the Hue bridge
key. Gitignored, but readable by any process running as the user.

### 6.2 Target

Use **`keyring`**, which on Windows stores credentials in the Credential Manager,
encrypted and bound to the machine and user account. Equivalent backends exist on
macOS (Keychain) and Linux (Secret Service).

```python
class SecretStore(Protocol):
    def get(self, provider: str, key: str) -> str | None: ...
    def set(self, provider: str, key: str, value: str) -> None: ...
    def delete(self, provider: str, key: str) -> None: ...
    def list_providers(self) -> list[str]: ...
```

### 6.3 The constraint that decides the design

**The daemon currently runs as `SYSTEM`, and keyring entries are per-user.** A
secret saved by the user in the GUI would be invisible to a SYSTEM service.

Options:

- **(a) Run the daemon as the user** — simplest, keyring works, but it only runs
  while logged in.
- **(b) Keep SYSTEM, store secrets under SYSTEM** — the GUI cannot then manage
  them, which defeats the purpose.
- **(c) DPAPI machine-scope encrypted file** — `CryptProtectData` with
  `LOCAL_MACHINE` scope. Both the user and SYSTEM can read it; still encrypted at
  rest and machine-bound. Not as strong as Credential Manager but solves the
  split.

**Recommend (a)**, falling back to (c) where a boot-time service is genuinely
needed. Note the notifier only matters while a cycle is running, which in practice
means while someone is at home and likely logged in.

### 6.4 In-app management

A Credentials screen offering, per provider:

- Add / change / remove, with the password field masked and never logged
- **Test connection** before saving
- Clear status: connected, bad credentials, unreachable
- Migration from the existing plaintext file on first run, with the old file
  **securely deleted** afterwards and the user told it happened
- For Hue: bridge discovery and the link-button pairing flow in-app
- Never write a secret to a log, an error message, or a crash report

---

## 7. Things not asked for, worth considering

### 7.1 Push instead of polling — highest value

`pyhOn` already pulls in `awsiotsdk`. The appliances communicate over **AWS IoT
MQTT**, which means near-instant state changes are possible instead of a
120-second poll. That removes up to two minutes of alert latency and cuts cloud
requests dramatically.

This is the single biggest functional improvement available. Establish whether
it works before committing to a polling architecture, because it changes the
shape of the daemon.

### 7.2 Energy tracking and cheap-rate scheduling

The API exposes cumulative energy counters. With them:

- Cost per cycle, using a configurable tariff
- Monthly usage reporting
- **Delayed start into a cheap-rate window** — `delayTime` accepts 0–1410
  minutes, so an Economy 7 user could arm the machine at bedtime and have it run
  at 02:00 automatically

### 7.3 Fault alerting

`machMode == 6` is an error state and currently only reaches a log file. A fault
deserves louder treatment than a finished cycle: a different colour, a different
spoken message, possibly an email.

### 7.4 Maintenance reminders

Cycle counts are available. Lint filter every cycle, heat exchanger periodically,
descaling for washing machines. A gentle reminder is genuinely useful and costs
almost nothing to implement.

### 7.5 A rules engine rather than hardcoded behaviour

Today "cycle finished → flash light + speak" is compiled in. Generalise to:

```yaml
- when: { appliance: TD, event: cycle_finished }
  then:
    - notifier: hue
      target: "Living room light"
      colour: green
    - notifier: cast
      target: "Living Room speaker"
      text: "Tumble dryer finished."

- when: { appliance: "*", event: error }
  then:
    - notifier: hue
      colour: red
      effect: solid
    - notifier: ntfy
```

This is what makes multi-appliance support actually useful rather than just
possible.

### 7.6 A phone-friendly web UI

Once the daemon exposes an HTTP API, a small responsive web page is a modest
addition and removes the need to be at the PC. Serve it from the daemon on the
LAN.

### 7.7 Testing without hardware

Record real API responses as fixtures and replay them. This is the only practical
way to test 16 appliance types when you own one. `probe.py` and `discover.py`
already produce suitable captures — they just need anonymising (**strip GPS
coordinates, MAC and serial**) and committing as test data.

### 7.8 Packaging and updates

- Proper `pyproject.toml`, installable with `pip install pastie`
- Keep the PyInstaller build for non-technical users
- Signed installer, or expect SmartScreen warnings
- Update check against GitHub releases, with the user in control of installing

### 7.9 Observability

- Structured logging with rotation, replacing the current append-forever file
- Redaction filter so a credential can never reach a log
- `/health` on the daemon API
- Optional anonymous crash reporting, off by default and opt-in

---

## 8. Decisions needed before starting

Built in one pass rather than staged, so every one of these has to be
answered up front - there is no later round in which to revisit them.

1. **Daemon identity** — run as the logged-in user (keyring works, needs login)
   or as SYSTEM (needs DPAPI machine-scope)? Recommendation: user.
2. **Scope of ambition** — a personal tool that happens to be public, or a project
   inviting contributors? That changes how much process is warranted.
3. **Home Assistant: adapter or replacement?** If HA is going to be installed
   anyway, much of this specification is redundant — HA plus `hon-revived`
   already provides multi-appliance support, every lighting brand, and both voice
   assistants. **Settle this before writing anything**, because the honest answer may be
   that the right architecture is a good HA integration plus a small companion
   app, not a parallel framework.
4. **Windows only, or cross-platform?** tkinter and the current build are
   Windows-shaped; nothing else is.

---

## 9. Explicit non-goals

- Reimplementing Google Home or Alexa integrations that Haier ships for free
- Controlling appliances without the manufacturer's safety interlocks
- Any feature that makes the appliance depend on this software to function
- Cloud hosting, user accounts, or telemetry beyond opt-in crash reports
