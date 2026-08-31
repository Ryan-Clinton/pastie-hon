# Pastie — design specification

A resilient, appliance-focused hOn companion: excellent state, notifications and
diagnostics, with optional Home Assistant integration.

Status: **proposal, revision 3**. Nothing here is built yet. Written against the
working prototype at commit `fa259dc`, revised after two rounds of external
audit.

> **Scope note.** This was originally an extensible home-automation framework.
> That scope competes with Home Assistant and loses. The provider layer — making
> hOn absurdly reliable — is the part that is genuinely hard and genuinely ours.

---

## 1. The product decision, before anything else

**This gates everything below. Nothing is built until it is settled.**

Two names that must not be confused:

- **`pyhon-revived`** — the Python *library* that talks to hOn
- **`hon-revived`** — the separate Home Assistant *custom integration*,
  distributed via HACS, which uses that library

Revision 2 conflated them, which hid the real question: **where does Pastie's
appliance intelligence execute, and who owns hOn reliability?**

### Three coherent options

**A1 — Pastie as a Home Assistant integration**

```
hOn → Pastie provider → Home Assistant → Pastie panel / UI
```

Pastie owns the provider but lives inside HA. HA supplies automation, device
breadth and voice. Requires HA; competes directly with `hon-revived`.

**A2 — Pastie as a Home Assistant companion**

```
hOn → pyhon-revived → hon-revived → Home Assistant → Pastie UI / analytics
```

Pastie **does not own hOn reliability** — `hon-revived` does. Pastie consumes HA
state and adds appliance-specific UX, analytics and history. Much of §3–§6 of
this document then belongs to somebody else's project, and should be deleted
rather than built.

**B — Standalone, with HA as an integration target** *(recommended)*

```
hOn → Pastie provider → Pastie core ─┬─ UI
                                     ├─ notifications
                                     └─ HA adapter (MQTT discovery)
```

Pastie is useful without anyone installing Home Assistant. HA becomes an output,
not a foundation. This is the cleanest continuation of the existing prototype and
the only option under which the rest of this specification is coherent as
written.

**The remainder of this document assumes B.** If A2 is chosen instead, §3–§6 are
out of scope and the document shrinks by more than half — which is precisely why
this decision comes first.

Under B the engineering priority is:

> make hOn absurdly reliable → make appliance state and events excellent →
> make setup pleasant → integrate outward

Not: support every smart light and voice ecosystem.

---

## 2. Principles

1. **The appliance still works if all this dies.** Never make the machine depend
   on our software.
2. **hOn can break overnight without us changing anything.** Design for it.
3. **Local beats cloud where a choice exists.**
4. **A command is not done until the device says so.** Cloud acceptance is not
   confirmation.
5. **Capability-driven, but not credulous.** Ask the appliance what it exposes;
   do not assume we understand it.
6. **One appliance is not all appliances.** A behaviour proven on the tumble
   dryer is a `TD` fact until proven elsewhere.
7. **Don't rebuild what a vendor or Home Assistant gives free.**

---

## 3. Risk register

| Risk | Evidence | Mitigation |
|---|---|---|
| hOn API changes without warning | Haier retired the Salesforce auth path in June 2026, moving to CIAM/PKCE and breaking integrations until the library adapted | All hOn specifics behind the provider boundary; explicit `API_INCOMPATIBLE` state; fail loudly |
| Library is unofficial | `pyhon-revived` describes itself as reverse-engineered and liable to stop working | See supply chain below |
| Supply chain | 0.19.2 is classified **Development Status :: 4 - Beta**, and neither the wheel nor the sdist was published with Trusted Publishing *(verified against PyPI, 2026-08-31)* | Exact version lock **with artefact hashes**; pin `awsiotsdk` and `awscrt` **together**; run compatibility fixtures before any upgrade; test the **frozen build**, not just the source; SBOM shipped with the installer |
| Upstream disappears | Single small maintainer team | Keep the provider abstraction good enough to freeze or replace the library without rewriting Pastie. **Do not fork or vendor pre-emptively** — that is a permanent maintenance burden for a hypothetical |
| Legal / governance | The original project received a takedown complaint from Haier before dialogue reopened | See below — non-commercial status is **not** a mitigation |
| Cloud dependency | A port scan of the appliance found no local listener; outbound to AWS IoT only | Accept it. Degrade gracefully; never block appliance function |
| Binary fragility | A `pyhon-revived` release disabled AWS metrics over an `awsiotsdk`/`awscrt` incompatibility | Covered by the pinning rule above |

### Legal posture

Revision 2 claimed "keep the project non-commercial and interoperability-focused"
as a mitigation. **That was overconfident** — non-commercial status does not
remove IP, trademark, contractual or takedown exposure. The actual posture:

- State unofficial, unaffiliated status prominently
- Do not use Haier trademarks or branding in any way implying affiliation
- Respect upstream licences (`pyhon-revived` is MIT)
- Do not redistribute proprietary vendor assets, endpoints or secrets
- Keep vendor-specific implementation isolated behind the provider
- Maintain a contingency for upstream library removal
- Seek legal review before any material commercial distribution

### Provider health — objectively defined

```
CONNECTED           MQTT live and fresh
MQTT_DEGRADED       connected but stale; reconciliation is carrying it
POLLING_FALLBACK    MQTT unavailable, polling only
AUTH_FAILED         credentials rejected
API_INCOMPATIBLE    library cannot parse the response - loud failure
UNREACHABLE         network or cloud down
```

These must be **derived from metrics, not from provider opinion**:

```
last_auth_success          last_reconcile_success
last_mqtt_connect          mqtt_disconnect_count
last_mqtt_message          consecutive_poll_failures
last_state_change
```

`MQTT_DEGRADED` is then a rule, not a judgement call:

```
MQTT connected
AND no message or heartbeat within the expected interval
AND polling still succeeds
=> MQTT_DEGRADED
```

**`CONNECTED` does not imply the state is fresh.** Every piece of state carries a
freshness timestamp, and the UI shows it.

### Insulation

hOn field names — `machMode`, `remoteCtrValid`, `dryLevel`, `prPhase`,
`dryTimeMM` — **must not leak past the provider**. This is what makes an API
break a one-module fix. It also means type-specific constants such as
`machMode 6 == fault` live in the `TD` descriptor, **not** in core logic, until
proven across types.

### Library

Move from `pyhOn` 0.17.5 to **`pyhon-revived`** (0.19.2), actively maintained,
carrying the CIAM/PKCE fix, depending on `awsiotsdk>=1.21.0`.

---

## 4. Transport: MQTT primary, polling as reconciliation

**MQTT is primary. Polling is reconciliation, not removed.**

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

Never push-only. Streams disconnect, duplicate, arrive out of order, expire
credentials, and miss transitions during downtime.

### Connection discipline

- **Reconnect uses exponential backoff with jitter.** A reconnect storm against
  Haier's cloud during an outage is both rude and self-defeating.
- **Reconciliation is also backed off** — a full refresh on every reconnect,
  unthrottled, is a request storm by another name.
- **Every reconnect triggers a full state refresh**, subject to that backoff.
- **A slow poll runs regardless**, to repair missed state.
- A reconciliation discrepancy is a **logged event**, not a silent correction —
  it is the primary signal that MQTT is unhealthy.

---

## 5. State, events and delivery

The most dangerous bugs are temporal, not parsing.

```
raw message  →  normalised state  →  state transition  →  semantic event
```

### 5.1 Transition rules

| From | To | Emits |
|---|---|---|
| `RUNNING` | `FINISHED` | `cycle_finished` |
| `UNKNOWN` | `FINISHED` | **nothing** — first observation, no evidence of a transition |
| `FINISHED` | `FINISHED` | nothing |
| `ERROR` | `ERROR` | nothing — no repeated fault alerts |
| `RUNNING` | `ERROR` | `fault` |
| any | `UNKNOWN` | `connection_lost` after a grace period |

`UNKNOWN` is a real modelled state. On startup, on reconnect, and after any gap,
state begins `UNKNOWN` and the first observation establishes a baseline
**without emitting**.

### 5.2 Recovered transitions — the downtime gap

Revision 2 had a genuine conflict: §5 said `UNKNOWN → FINISHED` emits nothing,
while §11 persisted last-known state so a restart has a baseline. Both cannot be
true without a fifth concept.

The problem:

```
20:00  RUNNING
20:10  Pastie stops
20:40  the dryer actually finishes
21:00  Pastie starts, cloud says FINISHED
```

Treat it as `UNKNOWN → FINISHED` and a real completion is missed. Restore
`RUNNING → FINISHED` from SQLite and announce it, and we are asserting something
we cannot know — was that one cycle, two, or a manual cancellation?

**A recovered transition is a distinct kind of transition**, and requires
evidence:

```
persisted:  state RUNNING,  cycle_count 175
on startup: state FINISHED, cycle_count 176
=> recovered_cycle_finished  (evidence: counter advanced by exactly one)
```

Where the appliance exposes no counter or session identifier, or the evidence is
ambiguous, **do not invent the event.** Report the gap honestly instead:

```
State changed while Pastie was offline.
  Previous: RUNNING   (last seen 20:10)
  Current:  FINISHED
  Completion time unknown.
```

A recovered event is marked as such, and notifiers may be configured to treat
recovered events differently from live ones — announcing "the dryer finished at
some point while I wasn't looking" is not the same message as "it just finished".

**Gate 0 must establish whether hOn exposes a usable cycle counter or session
id.** If it does not, recovered completions are informational only.

### 5.3 Delivery semantics

Persisting emitted events prevents re-firing on restart, but that is necessary
rather than sufficient:

```
1. cycle_finished persisted
2. webhook sent
3. webhook succeeds
4. crash before recording "delivered"
```

Retry and it may duplicate; don't retry and a crash can lose it. There is no
exactly-once delivery to arbitrary external systems, so **the semantics must be
chosen explicitly rather than left to each notifier**.

```
semantic event
     ↓
SQLite transaction
     ├─ events
     └─ deliveries
          ↓
      dispatcher
```

```
event:     id (uuid), type, appliance_id, occurred_at, recovered (bool)
delivery:  event_id, notifier, destination,
           status (pending | delivered | failed),
           attempts, last_attempt, last_error
```

**Chosen semantics: at-least-once, with deduplication where the receiver
supports it.**

- Webhooks carry `X-Pastie-Event-Id: <uuid>` so a receiver can be idempotent
- For lights, speech and toasts, an occasional duplicate after a process crash is
  an accepted and documented trade-off — a light flashing twice is not a fault
- Failed deliveries are retried with backoff and surfaced in the UI rather than
  disappearing into a log

---

## 6. Command lifecycle

Commands carry a correlation ID and a deadline.

```
REQUESTED → CLOUD_ACCEPTED → DEVICE_CONFIRMED
                           ↘ TIMEOUT | REJECTED | STATE_MISMATCH
```

```
Start requested        20:41:02
Cloud accepted         20:41:03
Appliance RUNNING      20:41:06   ✓ confirmed
```

versus

```
Start accepted by hOn but appliance state did not change within 20s
```

The prototype proved why: `stopProgram` returned `True` and the machine did
nothing.

---

## 7. Appliance model

### 7.1 Properties and commands are different things

Revision 2 used a single `Capability` for both, which forced awkward constructs
like `kind="readonly"`. They have different semantics and are modelled
separately.

```python
@dataclass
class PropertyDescriptor:
    key: str
    label: str
    type: Literal["number", "enum", "bool", "duration", "timestamp"]
    unit: str | None
    values: dict | None          # enum mapping
    minimum: float | None
    maximum: float | None
    freshness_required: timedelta | None


@dataclass
class CommandDescriptor:
    key: str
    label: str
    parameters: list[ParameterDescriptor]

    # preconditions - declarative, never ad hoc code
    requires_remote_arm: bool
    requires_idle: bool
    requires_door_closed: bool

    # verification
    api_writable: bool           # the API claims this is writable
    verified: bool               # WE have confirmed we understand it
    experimental: bool
    verification_predicate: str | None   # what proves DEVICE_CONFIRMED
    timeout: timedelta
```

### 7.2 Verification tiers

**`api_writable` and `verified` are not the same thing.** Only the tumble dryer
is validated; fifteen other types are not.

An unverified appliance type gets:

```
state discovery    yes
telemetry          yes
unknown fields     visible, diagnostically
commands           READ ONLY
```

until command semantics are confirmed against real hardware. "Capability-driven"
must never become "expose whatever a reverse-engineered API advertises" — on an
oven or an induction hob that is a safety question, not a UX one.

Type descriptors (`descriptors/TD.yaml` and so on) carry the mappings. Every
descriptor except `TD` ships marked **unverified**.

Known types: `AC` air conditioner, `AP` air purifier, `AS` air scanner, `DW`
dishwasher, `FRE` freezer, `HO` hood, `IH` induction hob, `MW` microwave, `OV`
oven, `REF` fridge, `RVC` robot vacuum, `TD` tumble dryer, `WC` wine cellar,
`WD` washer-dryer, `WH` water heater, `WM` washing machine.

### 7.3 What is actually proven

**Validated `TD` behaviour, from the prototype machine only:**

- Remote start requires `remoteCtrValid == 1`, which needs the machine powered on
  *and* the dial physically on the remote position
- Remote control **disarms itself after a completed cycle**
- `machMode 6` indicates a fault
- `dryTimeMM` is a stable total; `remainingTimeMM` is unreliable early in a cycle

**None of this is established for other appliance types.** An oven, washer,
dishwasher or water heater must be verified independently before the same safety
model is assumed. This matters most for the arming interlock: if another type
does *not* require arming, remote start is unattended, and that changes the
safety story entirely.

---

## 8. Security

### 8.1 Local IPC — named pipe with an explicit DACL

An unauthenticated REST API on `127.0.0.1` **must not ship** for an interface
exposing commands and configuration. Loopback is not a trust boundary; a
malicious web page can reach poorly protected localhost services, which is why
browsers are adding local-network access prompts.

**Default: a Windows named pipe.**

```
Desktop UI ──named pipe (explicit DACL)──→ Pastie agent
```

**Hard requirement, not an implementation detail:**

> **Never create the Pastie pipe with a NULL or default security descriptor.**

A pipe created with no explicit security descriptor gets a default ACL that
grants full control to SYSTEM, administrators and the creator — and **read access
to Everyone and to anonymous users**. The DACL must be constructed explicitly:

- **Per-user deployment** — the current logon SID, plus administrators if
  genuinely required
- **Service deployment** — `NT SERVICE\Pastie`, plus the authorised interactive
  user's SID
- Use the **logon SID** where access should be confined to the current terminal
  session

If REST is later wanted for CLI, HA or web clients, the protection is designed in
from the start, never retrofitted: authentication on every state-changing
request, strict `Origin` and `Host` validation, separate read and write scopes,
explicit API versioning. The phone-friendly LAN web UI sits behind that model and
is deferred until it exists.

### 8.2 Service identity

**`LocalSystem` is rejected** — nothing here needs SYSTEM privileges.

Machine-scope DPAPI is **withdrawn**: data protected with
`CRYPTPROTECT_LOCAL_MACHINE` can be decrypted by *any user account on that
machine*, which is a substantial downgrade from per-user protection. Revision 2
described it as "encrypted at rest and machine-bound", which was misleading.

The GUI never touches the secret store:

```
Pastie UI ──authenticated IPC──→ Pastie agent ──→ secret store (agent identity)
```

The UI sends *set this credential*; the agent stores it under its own identity.
This removes the supposed conflict between service identity and credential
management entirely.

**The two candidates for Gate 0:**

| | Option 1 — per-user app | Option 2 — Windows service |
|---|---|---|
| Identity | interactive user | **virtual service account** `NT SERVICE\Pastie` |
| Secrets | `keyring` → Credential Manager | service-owned store, ACL'd to the service SID |
| Password management | n/a | **none** — virtual accounts are managed automatically |
| Runs when logged out | **no** | yes |
| Install complexity | low | higher |

Revision 2 described Option 2 vaguely as a "dedicated low-privilege service
identity", implying a local account with a password to manage. It should be a
**virtual service account**, which Windows manages automatically, with a service
SID used to ACL files and the IPC pipe specifically to that service.

**Likely outcome: the service wins**, because the entire point is being told an
appliance has finished when you are *not* sitting at the PC — and dryers and
dishwashers routinely run overnight. But Gate 0 must first prove that
`pyhon-revived` and `awscrt` behave correctly in a service context before
committing.

**Implementation note:** `keyring` offers get/set/delete but no reliable
cross-platform enumeration. `list_providers()` reads Pastie's own configuration,
never the keyring.

### 8.3 Alert safety

Hue's developer terms place responsibility on applications not to create light
combinations that could adversely affect health, and to warn where appropriate.

- **Defaults:** fault → solid or gentle pulse; finished → colour change or
  limited flash
- **Bounded** rate and duration, enforced centrally, not per-notifier
- Rules cannot generate unlimited strobing

---

## 9. Philips Hue

Transport and API generation are **separate migrations**.

```
Current:          CLIP API v1 over HTTP  (obsolete transport)
Required first:   HTTPS / TLS
Preferred:        CLIP API v2, for the resource model and event stream
```

Terminology, used consistently: **CLIP API v1/v2** is the API generation;
**bridge hardware generation** is the physical device.

| | CLIP v1 | CLIP v2 |
|---|---|---|
| Auth | username in URL path | `hue-application-key` header |
| Updates | poll | server-sent events at `/eventstream/clip/v2` |
| Addressing | integer ids | stable UUIDs |
| Rooms, zones, scenes | limited | first-class |

- **Do not assume self-signed certificates.** Current Hue documentation
  references Signify-signed bridge certificates. Use a verification strategy that
  supports the current model rather than inventing "disable verification except
  pin the bridge ID" logic.
- **Re-pairing may not be required.** An existing v1 username can reportedly
  serve as the v2 application key. **Test against the real bridge in Gate 0.**

---

## 10. Voice assistants

**Do not build bespoke Alexa or Google infrastructure.** Haier ships official
integrations for both. A bespoke Alexa Smart Home skill needs an AWS Lambda
function, an OAuth 2.0 authorisation server and account linking, for
functionality the vendor already provides.

- **hOn does provide proactive notifications** — end-of-cycle and maintenance
  alerts to the phone. The honest differentiator:

  > hOn already provides proactive phone notifications; Pastie provides richer
  > cross-device actions — lights, speaker announcements, local automation.

- **Home Assistant does not make voice free of external infrastructure.** HA
  Cloud is the easy path; manual Google and Alexa setup still require
  cloud-facing configuration, and Alexa's manual route involves AWS Lambda. HA
  **centralises and substantially simplifies** it.

If voice is wanted, expose Pastie to Home Assistant via MQTT discovery rather
than integrating with assistants directly.

### Constraint (validated on `TD` only)

The tested dryer enforces `remoteCtrValid` in firmware, and no integration —
ours, Haier's or anyone's — can start a cycle it has not had armed at the panel.
It also disarms after every completed cycle. **Whether other appliance types
share this model is unverified.** Where it applies, every voice feature is
semi-attended by design and must be documented as such.

---

## 11. Persistence

**SQLite**, holding:

- Last-known appliance state and its freshness timestamp
- Cycle counter or session id, where available, for recovered-transition evidence
- Emitted events, with a `recovered` flag
- Delivery records (§5.3)
- Appliance metadata and capability cache
- Rules
- Schema version, with migrations

Secrets never go in SQLite.

---

## 12. Extensibility — deliberately conservative

Python entry points conflict with PyInstaller distribution: a frozen application
imports what existed at build time, and dynamically discovered plugins need
explicit hooks or must be present at freeze time. A Python plugin also executes
arbitrary third-party code with Pastie's permissions — there is no sandbox — and
a plugin API means a versioned SDK and a compatibility contract.

**Decision: defer third-party Python plugins.** Built-in adapters plus **webhook
and MQTT** give enormous extensibility at a fraction of the support and security
cost. Internally, notifiers still share a common interface — that is code
organisation, not a public contract.

---

## 13. Testing

Fixtures are **sequences, not single responses**.

```
startup while idle
startup mid-cycle                          (must NOT emit)
startup after downtime, cycle completed    (recovered transition)
startup after downtime, counter ambiguous  (must NOT invent an event)
idle -> running -> finished
running -> error
running -> disconnect -> finished -> reconnect
duplicate MQTT event
out-of-order MQTT event
credential expires mid-cycle
daemon restarts mid-cycle
command accepted by cloud, device never changes
reconciliation disagrees with last MQTT state
delivery succeeds but crash precedes the delivered record
```

Tests assert on **emitted semantic events and delivery records**, not on parsed
fields.

### Anonymisation: allowlist, not blacklist

Fixtures are generated from an **allowlist of fields known safe to retain**.
Blacklisting cannot anticipate every email, account id, appliance id, token,
Wi-Fi identifier, nickname, endpoint or new field Haier may add.

---

## 14. Feature priorities

| Feature | Priority | Note |
|---|---|---|
| **Fault alerting** | **High** | Currently only reaches a log. High value, low cost |
| Energy and cost per cycle | Medium | Counters already exposed |
| Maintenance reminders | Low | Needs **verified per-model** schedules; generic rules are wrong |
| Cheap-rate delayed start | Low | Interacts with arming, model-specific delay semantics, DST and cloud interruption. Do not build merely because `delayTime` accepts a number |
| Phone web UI | Deferred | Until the authentication model exists |

---

## 15. Validation gates

De-risking spikes, not delivery phases. The build can still be one pass *after*
they resolve.

> **Author's note:** this reverses the earlier "build in one pass" instruction.
> Retained because the audit endorsed it and because these resolve facts that
> cannot be known from design alone. **Still yours to overrule.**

| Gate | What must be proved |
|---|---|
| **0 — Spikes** | §1 product boundary; MQTT reconnect and backoff behaviour; whether hOn exposes a **cycle counter or session id** (§5.2 depends on it); whether the Hue v1 key works as a v2 application key; whether `pyhon-revived` and `awscrt` behave correctly **as a service** |
| **1 — Reliable TD agent** | One appliance: MQTT plus reconciliation, normalised state, command lifecycle |
| **2 — Event correctness** | Restart, reconnect, duplicate, out-of-order, recovered transitions, delivery records |
| **3 — Multi-appliance** | A genuinely different second appliance proves the descriptor abstraction |
| **4 — Integration boundary** | HA, webhook or native notifiers, driven by actual unmet need |
| **5 — Packaging** | Installer signing, virtual service account provisioning, upgrade and migration, SBOM, security review |

---

## 16. Decisions required

1. **§1 — A1, A2, or B?** Everything else follows. B assumed here.
2. **Service identity** — per-user with `keyring`, or Windows service under a
   virtual service account? **Not `LocalSystem`.**
3. **Local IPC** — named pipe (default), or authenticated REST because other
   clients are genuinely wanted?
4. **Windows only, or cross-platform?**
5. **Do the validation gates stand, or is this one pass?**

---

## 17. Non-goals

- Reimplementing Google Home or Alexa integrations Haier ships free
- Native LIFX, WiZ, Tuya or Nanoleaf support without demonstrated need
- Third-party Python plugins in the first release
- Becoming a general-purpose home-automation hub
- Controlling appliances around manufacturer safety interlocks
- Unauthenticated network interfaces of any kind
- Forking or vendoring `pyhon-revived` pre-emptively
- Cloud hosting, user accounts, or telemetry beyond opt-in crash reports

---

## Appendix — provenance

Findings cited here were measured against **one** real appliance during the
prototype session, not inferred: the `remoteCtrValid` gate and its per-cycle
expiry, the `machMode` values, `.send()` returning `True` without device action,
`dryTimeMM` versus `remainingTimeMM`, and the appliance having no local listener.

The `prPhase` 15/19 inversion versus the community mapping is an observation from
repeated cycles on one machine and is provisional until seen on another.

PyPI metadata for `pyhon-revived` 0.19.2 (Beta classifier, no Trusted Publishing,
MIT licence) was verified directly on 2026-08-31.

Everything concerning other appliance types is unverified by definition — we own
one appliance.
