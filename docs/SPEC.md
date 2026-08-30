# Pastie — design specification

A resilient, appliance-focused hOn companion: excellent state, notifications and
diagnostics, with optional Home Assistant integration.

Status: **proposal, revision 2**. Nothing here is built yet. Written against the
working prototype at commit `fa259dc`, revised after external audit.

> **Revision 2 changed the shape of this document.** It was previously scoped as
> an extensible home-automation framework. That scope competes with Home
> Assistant and loses. The provider layer — making hOn absurdly reliable — is the
> part that is genuinely hard and genuinely ours.

---

## 1. The product decision, before anything else

**This decision gates everything below. Nothing should be built until it is
settled.**

Home Assistant, with `hon-revived`, already provides: multi-appliance hOn
support, local-push Hue with rooms/zones/scenes, Google Cast, mobile push
notifications, an automation engine, MQTT discovery, and both voice assistants.

If Home Assistant is acceptable in the deployment, then this —

```
hOn → Pastie provider → normaliser → event bus → rules
    → Pastie Hue/Cast/ntfy/webhook adapters → Pastie web UI
```

— is substantially rebuilding this:

```
hOn → hon-revived → Home Assistant
                     ├─ automations, Hue, Cast, notifications
                     ├─ mobile UI, MQTT, Alexa, Google
                     └─ hundreds of other integrations
```

### Two viable products

**A. Companion to Home Assistant** *(smaller, recommended if HA is acceptable)*

```
hOn → pyhon-revived → Home Assistant → Pastie companion UI + appliance logic
```

Pastie owns appliance-specific intelligence and UX. HA owns automation and
device breadth. Native notifiers become unnecessary.

**B. Standalone** *(justified if requiring HA is unacceptable)*

Pastie owns the provider and a **deliberately narrow** set of outputs: Windows
toast, webhook, and optionally Hue and Cast because they already exist in the
prototype. **No native LIFX, WiZ, Tuya or Nanoleaf until there is demonstrated
need** — a webhook or an HA adapter reaches all of them for a fraction of the
cost.

Under either option the engineering priority is the same:

> make hOn absurdly reliable → make appliance state and events excellent →
> make setup pleasant → integrate outward

Not: support every smart light and voice ecosystem.

---

## 2. Principles

1. **The appliance still works if all this dies.** Never take an action that
   makes the machine depend on our software.
2. **hOn can break overnight without us changing anything.** Design for it.
3. **Local beats cloud where a choice exists.**
4. **A command is not done until the device says so.** Cloud acceptance is not
   confirmation.
5. **Capability-driven, but not credulous.** Ask the appliance what it exposes;
   do not assume we understand it.
6. **Don't rebuild what a vendor or Home Assistant gives free.**

---

## 3. Risk register

The provider is the risky part. This belongs in the architecture, not a footnote.

| Risk | Evidence | Mitigation |
|---|---|---|
| hOn API changes without warning | Haier retired the Salesforce auth path in June 2026, moving to CIAM/PKCE and breaking integrations until the library adapted | All hOn specifics behind the provider boundary; explicit `API_INCOMPATIBLE` state; fail loudly, not silently |
| Library is unofficial | `pyhon-revived` describes itself as reverse-engineered and liable to stop working | Pin versions; treat library upgrades as risk events; keep fixtures to detect breakage |
| Legal / governance | The original project received a takedown complaint from Haier before dialogue reopened | Keep the project clearly non-commercial and interoperability-focused |
| Cloud dependency | A port scan of the appliance found no local listener; it is outbound-only to AWS IoT | Accept it. Degrade gracefully; never block appliance function |
| Binary dependency fragility | A `pyhon-revived` release disabled AWS metrics over an `awsiotsdk`/`awscrt` compatibility problem | Pin `awsiotsdk`; test the frozen build, not just the source |

### Provider state is a first-class concept

```
CONNECTED           normal, MQTT live
MQTT_DEGRADED       events unreliable, reconciliation carrying it
POLLING_FALLBACK    MQTT unavailable, polling only
AUTH_FAILED         credentials rejected
API_INCOMPATIBLE    library cannot parse the response - loud failure
UNREACHABLE         network or cloud down
```

The UI must show this. A silent degradation to polling is how a two-minute alert
delay becomes invisible.

### Insulation

hOn field names — `machMode`, `remoteCtrValid`, `dryLevel`, `prPhase`,
`dryTimeMM` — **must not leak past the provider**. Everything above it sees
normalised state. This insulation is worth more than any plugin framework: it is
what makes an API break a one-module fix.

### Library choice

Move from `pyhOn` 0.17.5 to **`pyhon-revived`** (0.19.2 at time of writing),
which is actively maintained, carries the CIAM/PKCE fix, and depends on
`awsiotsdk>=1.21.0`.

---

## 4. Transport: MQTT primary, polling as reconciliation

The prototype polls every 120 seconds. `pyhon-revived` uses AWS IoT MQTT, with
recent releases fixing MQTT reconnection after auth-token expiry.

**MQTT is the primary transport. Polling is retained as reconciliation, not
removed.**

```
            ┌──── MQTT events ─────┐
hOn cloud ──┤                      ├──→ raw state reducer
            └── periodic reconcile ┘            ↓
                                        normalised state
                                                ↓
                                        transition detector
                                                ↓
                                          semantic event
```

Never push-only. Event streams disconnect, duplicate, arrive out of order, expire
credentials, and miss transitions during downtime.

Rules:

- **Every reconnect triggers a full state refresh.** Do not assume continuity.
- **A slow poll (a few minutes) runs regardless**, to repair missed state.
- Reconciliation that finds a discrepancy is a **logged event**, not a silent
  correction — it is the signal that MQTT is unhealthy.

---

## 5. State and event semantics

The most dangerous bugs are not parse failures. They are announcing "Tumble dryer
finished!" because the daemon restarted and the first snapshot said `FINISHED`.

Four distinct layers, never conflated:

```
raw message  →  normalised state  →  state transition  →  semantic event
```

### Transition rules

| From | To | Emits |
|---|---|---|
| `RUNNING` | `FINISHED` | `cycle_finished` |
| `UNKNOWN` | `FINISHED` | **nothing** — first observation after start |
| `FINISHED` | `FINISHED` | nothing — no duplicates |
| `ERROR` | `ERROR` | nothing — no repeated fault alerts |
| `RUNNING` | `ERROR` | `fault` |
| any | `UNKNOWN` | `connection_lost` after a grace period |

`UNKNOWN` is a real state and must be modelled explicitly. On startup, on
reconnect, and after any gap, state begins as `UNKNOWN` and the first observation
establishes a baseline **without emitting**.

Emitted events are persisted, so a restart mid-cycle does not re-fire an alert
already delivered.

---

## 6. Command lifecycle

"Verify writes by reading back" becomes a proper lifecycle rather than a
convention. Commands carry a correlation ID and a deadline.

```
REQUESTED → CLOUD_ACCEPTED → DEVICE_CONFIRMED
                           ↘ TIMEOUT | REJECTED | STATE_MISMATCH
```

Directly observable in the UI and in diagnostics:

```
Start requested        20:41:02
Cloud accepted         20:41:03
Appliance RUNNING      20:41:06   ✓ confirmed
```

versus

```
Start accepted by hOn but appliance state did not change within 20s
```

The prototype proved why this matters: `stopProgram` returned `True` and the
machine did nothing.

---

## 7. Capability model

Derive capability at runtime rather than hardcoding a dryer — but do not trust
the API's own account of what is writable.

```python
@dataclass
class Capability:
    key: str
    kind: Literal["enum", "range", "bool", "readonly"]
    label: str
    values: dict | tuple | None
    unit: str | None
    minimum: float | None
    maximum: float | None
    step: float | None

    # safety and preconditions - declarative, not ad hoc code
    requires_remote_arm: bool
    requires_idle: bool
    requires_door_closed: bool

    # verification tier - see below
    api_writable: bool          # the API says this is writable
    verified: bool              # WE have verified we understand it
    experimental: bool
    verification_strategy: str | None
```

### Verification tiers

**`api_writable` and `verified` are different things.** Only the tumble dryer is
validated; fifteen other appliance types are not.

An unverified appliance type gets:

```
state discovery    yes
telemetry          yes
unknown fields     visible, diagnostically
commands           READ ONLY
```

until command semantics are confirmed against real hardware. Capability-driven
must not become "blindly expose whatever a reverse-engineered API advertises" —
on an oven or an induction hob that is a safety question, not a UX one.

Type descriptors (`descriptors/TD.yaml` and so on) carry the mappings. Every
descriptor except `TD` ships marked **unverified**.

Known types: `AC` air conditioner, `AP` air purifier, `AS` air scanner, `DW`
dishwasher, `FRE` freezer, `HO` hood, `IH` induction hob, `MW` microwave, `OV`
oven, `REF` fridge, `RVC` robot vacuum, `TD` tumble dryer, `WC` wine cellar,
`WD` washer-dryer, `WH` water heater, `WM` washing machine.

---

## 8. Security

### 8.1 Local IPC — not an unauthenticated REST API

The previous revision proposed binding REST to `127.0.0.1` with "no
authentication needed at first". **That should not ship** for an interface
exposing commands and configuration.

Loopback is not a trust boundary. A malicious web page in the user's browser can
reach poorly protected localhost services — which is precisely why browsers are
adding explicit local-network access permission prompts.

**Default: a Windows named pipe with an ACL**, between the desktop UI and the
agent. No browser can reach it.

```
Desktop UI ──named pipe (ACL)──→ Pastie agent
```

If REST is genuinely wanted for CLI, HA or web clients, the protection must be
designed in from the start, not retrofitted:

- Authentication on every state-changing request
- Strict `Origin` and `Host` validation
- Separate read and write scopes
- Explicit API versioning

The previously proposed phone-friendly LAN web UI **moves behind that
authentication model** and is deferred until it exists. Adding auth after
external clients depend on an unauthenticated API is exactly the rewrite this
document exists to avoid.

### 8.2 Credentials

The previous revision offered machine-scope DPAPI and described it as "still
encrypted at rest and machine-bound". **That was misleading and is withdrawn.**
Data protected with `CRYPTPROTECT_LOCAL_MACHINE` can be decrypted by *any user
account on that machine* — a substantial downgrade from per-user protection.

The reasoning that "SYSTEM secrets mean the GUI cannot manage them" was also
wrong. The GUI never needs to touch the secret store:

```
Pastie UI ──authenticated IPC──→ Pastie agent ──→ secret store (agent identity)
```

The UI sends *set this credential*; the agent stores it under its own identity.

**Decisions:**

- **Do not run as `LocalSystem`.** Nothing in this architecture needs SYSTEM
  privileges.
- If a background service is wanted, use a **dedicated low-privilege service
  identity** with its own secret store.
- If Pastie is a per-user desktop application, run as the interactive user and
  use `keyring` → Windows Credential Manager. Entirely defensible.

The previous justification — that the user is "likely logged in" while a cycle
runs — was weak and is withdrawn. Dryers and dishwashers routinely run overnight.

**Implementation note:** `keyring` provides get/set/delete but no reliable
cross-platform enumeration. `list_providers()` must read from Pastie's own
configuration, not attempt to enumerate the keyring.

### 8.3 Alert safety

Hue's developer terms place responsibility on applications not to create light
combinations that could adversely affect health, and to warn where appropriate.
Flashing is not an unconstrained effect.

- **Defaults:** fault → solid or gentle pulse; finished → colour change or
  limited flash
- **Bounded** rate and duration, enforced centrally
- Rules cannot generate unlimited strobing

---

## 9. Philips Hue

Migrating off plain HTTP is correct — new bridge firmware drops HTTP under the
RED compliance changes. But transport and API generation are **separate
migrations**, and the previous revision conflated them.

```
Current:          CLIP API v1 over HTTP  (obsolete transport)
Required first:   HTTPS / TLS
Preferred:        CLIP API v2, for the resource model and event stream
```

Terminology, used consistently: **CLIP API v1/v2** is the API generation;
**Bridge hardware generation** is the physical device. The previous phrase "v1
fallback for pre-v2 bridges" conflated the two.

| | CLIP v1 | CLIP v2 |
|---|---|---|
| Auth | username in URL path | `hue-application-key` header |
| Updates | poll | server-sent events at `/eventstream/clip/v2` |
| Addressing | integer ids | stable UUIDs |
| Rooms, zones, scenes | limited | first-class |

Corrections carried from audit:

- **Do not assume self-signed certificates.** Current Hue documentation
  references Signify-signed bridge certificates. Use a library or verification
  strategy that supports the current certificate model rather than inventing
  "disable verification except pin the bridge ID" logic.
- **Re-pairing may not be required.** An existing v1 username can reportedly
  serve as the v2 application key. **Test against a real bridge before
  specifying a forced re-pair.**

---

## 10. Voice assistants

**Do not build bespoke Alexa or Google infrastructure.** Haier ships official
integrations for both, configured in the hOn app. A bespoke Alexa Smart Home
skill needs an AWS Lambda function, an OAuth 2.0 authorisation server and account
linking, for functionality the vendor already provides.

Two corrections to the previous revision, which overstated both sides:

- **hOn does provide proactive notifications.** Haier's material advertises
  end-of-cycle and maintenance notifications to the phone. The earlier claim of
  "no proactive notification" was wrong. The honest differentiator is narrower
  and still real:

  > hOn already provides proactive phone notifications; Pastie provides richer
  > cross-device actions — lights, speaker announcements, and local automation.

- **Home Assistant does not make voice assistants free of external
  infrastructure.** Home Assistant Cloud is the easy path; manual Google and
  Alexa integration still require cloud-facing setup, and Alexa's manual route
  involves AWS Lambda. The accurate claim is that **HA centralises and
  substantially simplifies** it.

If voice is wanted, expose Pastie to Home Assistant — MQTT discovery is the
lower-effort route — rather than integrating with assistants directly.

### Unavoidable constraint

`remoteCtrValid` is enforced in appliance firmware. **No integration — ours,
Haier's, or anyone's — can start a cycle that has not been armed at the panel.**
It also disarms itself after every cycle. Document this prominently; every voice
feature is semi-attended by design.

---

## 11. Persistence

A small durable store, **SQLite**, for:

- Last-known appliance state, so a restart has a baseline and does not re-fire
- Emitted event history, for deduplication and a timeline in the UI
- Appliance metadata and capability cache
- Rules
- Schema version, with migrations

Secrets stay in the OS-backed store, never in SQLite.

---

## 12. Extensibility — deliberately conservative

Python entry points are a reasonable plugin mechanism for installed packages, but
they **conflict with PyInstaller distribution**: a frozen application imports what
was present at build time, and dynamically discovered plugins need explicit hooks
or must exist at freeze time.

Two further considerations: a Python plugin executes arbitrary third-party code
with Pastie's permissions — there is no sandbox — and supporting a plugin API
means a versioned SDK and a compatibility contract.

**Decision: defer third-party Python plugins.** Built-in adapters plus **webhook
and MQTT** give enormous extensibility at a fraction of the support and security
cost. Internally, notifiers still implement a common interface so adding one is a
single file — that is a code-organisation benefit, not a public contract.

---

## 13. Testing

Recorded fixtures, but **the fixtures are sequences, not single responses**. The
dangerous bugs are temporal.

Required scenarios:

```
startup while idle
startup mid-cycle                     (must NOT emit)
idle -> running -> finished
running -> error
running -> disconnect -> finished -> reconnect
duplicate MQTT event
out-of-order MQTT event
credential expires mid-cycle
daemon restarts mid-cycle
command accepted by cloud, device never changes
reconciliation disagrees with last MQTT state
```

Tests assert on **emitted semantic events**, not on parsed fields.

### Anonymisation: allowlist, not blacklist

The previous revision said to strip GPS, MAC and serial. **That is too narrow.**
Fixtures must be generated by an **allowlist of fields known safe to retain**.
Blacklisting cannot anticipate every email, account id, appliance id, token,
Wi-Fi identifier, nickname, endpoint or new field Haier adds later.

---

## 14. Feature priorities

| Feature | Priority | Note |
|---|---|---|
| **Fault alerting** | **High** | `machMode 6` currently only reaches a log. High value, low cost |
| Energy and cost per cycle | Medium | Counters already exposed; natural fit |
| Maintenance reminders | Low | Needs **verified per-model** schedules. Generic inferred rules are wrong |
| Cheap-rate delayed start | Low | Interacts with remote arming, model-specific delay semantics, DST, and cloud interruption. Do not build merely because `delayTime` accepts a number |
| Phone web UI | Deferred | Until the authentication model exists |

---

## 15. Validation gates

> **Note for the author:** this section reinstates staged validation, reversing
> the earlier "build in one pass" instruction. It is retained because several
> decisions depend on experimentation against systems we do not control.
> **This one is yours to overrule** — the argument for it is that discovering at
> the end that Home Assistant makes half the work unnecessary is the expensive
> outcome.

These are de-risking spikes, not delivery phases. The build can still be one pass
*after* they resolve.

| Gate | What must be proved |
|---|---|
| **0 — Spikes** | HA vs standalone; MQTT reconnect behaviour; whether the Hue v1 key works as a v2 application key; the service identity and secrets model |
| **1 — Reliable TD agent** | One appliance: MQTT plus reconciliation, normalised state, command verification |
| **2 — Event correctness** | Restart, reconnect, duplicate, out-of-order, persistence |
| **3 — Multi-appliance** | A genuinely different second appliance proves the capability abstraction |
| **4 — Integration boundary** | HA, webhook or native notifiers, driven by actual unmet need |
| **5 — Packaging** | Installer signing, upgrade and migration, security review |

---

## 16. Decisions required

1. **Home Assistant: companion or standalone?** (§1) Everything else follows.
2. **Service identity** — per-user desktop app with `keyring`, or dedicated
   low-privilege service? **Not `LocalSystem`.**
3. **Local IPC** — named pipe (default), or authenticated REST because other
   clients are genuinely wanted?
4. **Windows only, or cross-platform?** tkinter and the current build are
   Windows-shaped.
5. **Do the validation gates in §15 stand, or is this one pass?**

---

## 17. Non-goals

- Reimplementing Google Home or Alexa integrations Haier ships free
- Native support for LIFX, WiZ, Tuya or Nanoleaf without demonstrated need
- Third-party Python plugins in the first release
- Becoming a general-purpose home-automation hub
- Controlling appliances around manufacturer safety interlocks
- Unauthenticated network interfaces of any kind
- Cloud hosting, user accounts, or telemetry beyond opt-in crash reports

---

## Appendix — provenance

Prototype findings cited here — the `remoteCtrValid` gate, the `machMode` values,
`.send()` returning `True` without device action, `dryTimeMM` versus
`remainingTimeMM`, and the appliance having no local listener — were measured
against the real machine during the prototype session, not inferred. The
`prPhase` 15/19 inversion versus the community mapping is an observation from
repeated cycles on one machine and should be treated as provisional until seen on
another.
