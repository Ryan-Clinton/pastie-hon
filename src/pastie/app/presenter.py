"""Turns the service's status into everything the window shows.

All wording and every decision about the screen live here, so they are tested
with pytest like the rest of Pastie, and the page that draws them does nothing
clever (docs/UI-SPEC.md 5.5). The output is a plain dictionary, the ScreenState.

The rules, in the order they are applied:

1. **Facts first, and plain at every personality level.** State, programme,
   time, progress, faults, the tank, commands. Nothing configurable touches
   them.
2. **Then, at most one aside**, and only where the level allows it and the
   severity is info or maintenance. Warning, error and safety carry none, at any
   level (SPEC 17, rule 5).
3. **Pastie never gives the thumbs-up unless Pastie knows.** The Confirmed pose
   appears only on machine-confirmed state (SPEC 17, Pastie's laws).
4. **Nothing is invented.** Every "why" is built from the real rule and its
   inputs; anything the service does not send is left out, not guessed.

Haier's own field names never appear here (SPEC 4): raw values are shown in
Diagnostics as data, never read as meaning.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pastie import __version__
from pastie.app import voice
from pastie.app.memory import WindowMemory

LEVELS = ("plain", "dry", "departmental")

#: Most urgent first (UI-SPEC 6.10). Needs-action outranks everything.
_URGENCY = {"fault": 1, "running": 2, "paused": 3, "finished": 4, "scheduled": 5, "idle": 6}

STATE_WORDS = {
    "idle": "IDLE",
    "running": "RUNNING",
    "paused": "PAUSED",
    "finished": "FINISHED",
    "fault": "FAULT",
    "scheduled": "SCHEDULED",
}

HEALTH_WORDS = {
    "ok": "Working normally",
    "slow": "Working, but updates are slow",
    "auth": "Can't log in",
    "schema": "Can't understand Haier's response",
    "offline": "Can't reach the internet",
    "down": "The service isn't running",
}

#: How long a finished command's full paper trail stays open (UI-SPEC 6.5).
TRAIL_OPEN = timedelta(seconds=8)
#: How long its collapsed last line stays on the main screen afterwards.
TRAIL_LINGER = timedelta(minutes=10)
#: How long "Everything appears to be in order." and "Connection restored." show.
READY_FOR = timedelta(seconds=1.5)
RECONNECTED_FOR = timedelta(seconds=6)
#: A pinned hero gives way to urgency after this long (UI-SPEC 6.10).
PIN_FOR = timedelta(minutes=5)
#: The three-click aside's cooldown (UI-SPEC 7.7).
POKE_COOLDOWN = timedelta(minutes=30)


def _seed(text: str) -> int:
    """Stable across runs, unlike hash(), which is salted per process."""
    return zlib.crc32(text.encode())


def _when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _clock(at: datetime | None, seconds: bool = False) -> str:
    if at is None:
        return ""
    local = at.astimezone()
    return f"{local:%H:%M:%S}" if seconds else f"{local:%H:%M}"


def curve(kind: str, progress: float) -> int:
    """A joke meter's value, always 0-100, always driven by real progress."""
    p = min(max(progress, 0.0), 1.0)
    if kind == "rising":
        value = 1 - (1 - p) ** 2
    elif kind == "peaking":
        value = math.sin(math.pi * p)
    else:  # late
        value = p**4
    return round(100 * value)


class Presenter:
    """One per window. Holds the session's observations; `memory` holds the rest."""

    def __init__(
        self,
        memory: WindowMemory,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._memory = memory
        self._now = now
        #: appliance id -> the previous reply's view of it (this session only).
        self._previous: dict[str, dict[str, Any]] = {}
        #: appliance id -> (before, after, event id) of the latest rise this cycle.
        self._rise: dict[str, tuple[int, int, str]] = {}
        #: appliance id -> the largest rise shown this cycle (Dry repetition rule).
        self._biggest_rise: dict[str, int] = {}
        self._health: str | None = None
        self._ever_ready = False
        self._ready_until: datetime | None = None
        self._reconnected_at: datetime | None = None
        self._recent_before_drop: set[str] = set()
        self._fault_open: set[str] = set()
        self._last_poke: datetime | None = None
        self._last_status: dict[str, Any] | None = None

    # ============================================================ settings

    @property
    def level(self) -> str:
        return self._memory.state.appearance.level

    def set_level(self, level: str) -> None:
        if level in LEVELS:
            self._memory.state.appearance.level = level
            self._memory.touch()
            self._memory.save()

    def level_for(self, appliance_id: str) -> str:  # noqa: ARG002 - see below
        """The personality level for one appliance.

        The global level until personality sheets arrive (UI-SPEC 7.9), which
        let the owner override it per appliance.
        """
        return self.level

    def name_for(self, appliance: dict[str, Any]) -> str:
        """What Pastie calls an appliance inside asides. Never used in facts."""
        return f"the {appliance.get('name') or 'appliance'}"

    def pin(self, appliance_id: str) -> None:
        self._memory.state.pinned = {"id": appliance_id, "at": self._now().isoformat()}
        self._memory.touch()

    # ========================================================== observing

    def observe(self, status: dict[str, Any] | None) -> None:
        """Record what this reply shows. Canonical facts only (UI-SPEC A15)."""
        now = self._now()
        health = "down" if status is None else str(status.get("health") or "ok")
        # A reconnect only once Pastie has been properly connected: the first
        # start-up passing through "slow" on its way to "ok" is not a return.
        if self._ever_ready and self._health not in (None, "ok") and health == "ok":
            self._reconnected_at = now
        if health != "ok" and self._health == "ok" and self._last_status is not None:
            self._recent_before_drop = {
                str(e.get("at")) for e in self._last_status.get("recent") or []
            }
        self._health = health
        if status is None:
            return
        self._last_status = status

        for appliance in status.get("appliances") or []:
            self._observe_appliance(appliance, now)

        for event in status.get("recent") or []:
            if event.get("kind") == "cycle_finished_while_away":
                self._record_once(
                    {
                        "t": event.get("at"),
                        "appliance": None,
                        "kind": "gap",
                        "message": event.get("message"),
                    }
                )
                self._memory.unlock("coming_back", now.isoformat())

        detail = status.get("command_detail")
        if isinstance(detail, dict) and detail.get("outcome") in (
            "confirmed",
            "timed_out",
            "rejected",
            "refused",
        ):
            self._record_once({"kind": "command", **detail, "t": detail.get("requested_at")})

        self._memory.unlock("pasties", now.isoformat())
        self._memory.save()

    def _observe_appliance(self, appliance: dict[str, Any], now: datetime) -> None:
        aid = str(appliance.get("id"))
        state = str(appliance.get("state") or "unknown")
        verified = appliance.get("trust") == "verified"
        stamp = now.isoformat()
        previous = self._previous.get(aid)
        last_state = self._last_observed(aid, "state")

        if verified and (last_state is None or last_state.get("state") != state):
            self._memory.observe(
                {
                    "t": appliance.get("updated_at") or stamp,
                    "appliance": aid,
                    "kind": "state",
                    "state": state,
                    "programme": appliance.get("programme"),
                }
            )
            if state == "running":
                self._memory.unlock("round", stamp)
                self._rise.pop(aid, None)
                self._biggest_rise.pop(aid, None)
                if appliance.get("programme") == "Duvet":
                    self._memory.unlock("duvets", stamp)

        count = appliance.get("cycle_count")
        last_count = self._last_observed(aid, "counter")
        if isinstance(count, int):
            before = last_count.get("after") if last_count else None
            if before is None or count != before:
                self._memory.observe(
                    {
                        "t": stamp,
                        "appliance": aid,
                        "kind": "counter",
                        "before": before,
                        "after": count,
                    }
                )
            if count >= 50:
                self._memory.unlock("milestones", stamp)

        minutes = appliance.get("remaining_minutes")
        if (
            state == "running"
            and previous is not None
            and previous.get("state") == "running"
            and isinstance(minutes, int)
            and isinstance(previous.get("remaining_minutes"), int)
            and minutes > previous["remaining_minutes"]
        ):
            before = int(previous["remaining_minutes"])
            event_id = f"{aid}/rose/{self._cycle_marker(aid)}/{before}/{minutes}"
            self._rise[aid] = (before, minutes, event_id)
            self._memory.observe(
                {
                    "t": stamp,
                    "appliance": aid,
                    "kind": "estimate",
                    "before": before,
                    "after": minutes,
                }
            )
            self._memory.unlock("estimates", stamp)

        attention = str(appliance.get("attention") or "")
        if "tank" in attention.lower():
            self._memory.unlock("water", stamp)
            if not (previous and "tank" in str(previous.get("attention") or "").lower()):
                self._memory.observe(
                    {"t": stamp, "appliance": aid, "kind": "attention", "what": attention}
                )

        if state == "fault":
            if aid not in self._fault_open:
                self._memory.observe(
                    {
                        "t": stamp,
                        "appliance": aid,
                        "kind": "fault",
                        "code": appliance.get("fault_code"),
                    }
                )
            self._fault_open.add(aid)
        elif aid in self._fault_open:
            self._fault_open.discard(aid)
            self._memory.unlock("faults", stamp)

        if any(item.get("due") for item in appliance.get("maintenance") or []):
            self._memory.unlock("lint", stamp)

        self._previous[aid] = dict(appliance)

    def _last_observed(self, appliance_id: str, kind: str) -> dict[str, Any] | None:
        for row in reversed(self._memory.state.observations):
            if row.get("appliance") == appliance_id and row.get("kind") == kind:
                return row
        return None

    def _record_once(self, row: dict[str, Any]) -> None:
        key = (row.get("kind"), row.get("t"), row.get("id"))
        for existing in reversed(self._memory.state.observations[-200:]):
            if (existing.get("kind"), existing.get("t"), existing.get("id")) == key:
                return
        self._memory.observe(row)

    def _cycle_marker(self, appliance_id: str) -> str:
        """The start of the current cycle, as a stable id for its events."""
        for row in reversed(self._memory.state.observations):
            if (
                row.get("appliance") == appliance_id
                and row.get("kind") == "state"
                and row.get("state") == "running"
            ):
                return str(row.get("t"))
        return "unknown"

    # ============================================================ the screen

    def screen(self, status: dict[str, Any] | None) -> dict[str, Any]:
        """The whole main window, as data. Observes the reply first."""
        self.observe(status)
        now = self._now()
        level = self.level
        header = self._header(status)

        appliances = list((status or {}).get("appliances") or [])
        stage = self._connecting_stage(status, appliances)
        screen: dict[str, Any] = {
            "level": level,
            "header": header,
            "caseload_heading": voice.CASELOAD_HEADING if level == "departmental" else None,
            "caseload": [],
            "hero": None,
            "connecting": None,
            "where": self._where(status),
            "trail": None,
            "guide_new": self.guide_has_new(),
            "version": __version__,
        }

        if stage is not None:
            screen["connecting"] = {
                "stage": stage,
                "line": voice.CONNECTING_PLAIN if level == "plain" else voice.CONNECTING[stage],
                "pose": "waiting",
            }
        elif self._reconnected_at and now - self._reconnected_at < RECONNECTED_FOR:
            screen["connecting"] = self._reconnect_notice(level)

        if not appliances:
            if status is not None and stage is None:
                screen["connecting"] = {
                    "stage": "empty",
                    "line": voice.EMPTY_NO_APPLIANCE[level],
                    "pose": "normal",
                }
            self._memory.save()
            return screen

        hero_id = self._hero_id(appliances)
        screen["caseload"] = [
            {
                "id": str(a.get("id")),
                "name": _sentence(str(a.get("name") or "appliance")),
                "state": self._state(a),
                "state_word": self._state_word(a),
                "pose": self._pose(a, level, status),
                "unverified": a.get("trust") != "verified",
                "selected": str(a.get("id")) == hero_id,
            }
            for a in sorted(appliances, key=self._urgency)
        ]
        hero = next(a for a in appliances if str(a.get("id")) == hero_id)
        screen["hero"] = self._hero(hero, status or {}, level)
        screen["trail"] = self._trail(hero, status or {}, level)
        self._memory.save()
        return screen

    # ------------------------------------------------------------ header

    def _header(self, status: dict[str, Any] | None) -> dict[str, Any]:
        health = "down" if status is None else str(status.get("health") or "ok")
        tone = "ok" if health == "ok" else ("warn" if health == "slow" else "bad")
        return {"health": health, "words": HEALTH_WORDS.get(health, health), "tone": tone}

    def _connecting_stage(
        self, status: dict[str, Any] | None, appliances: list[dict[str, Any]]
    ) -> str | None:
        """The observable connecting stage, or None once connected (UI-SPEC 6.8)."""
        now = self._now()
        if self._ever_ready:
            if self._ready_until and now < self._ready_until:
                return "ready"
            return None
        if status is None:
            return "service"
        if status.get("health") != "ok":
            return None if status.get("health") in ("auth", "offline", "schema") else "haier"
        if not appliances:
            return "appliances"
        if not any(
            a.get("trust") == "verified" and self._state(a) != "unknown" for a in appliances
        ):
            return "reading"
        self._ever_ready = True
        self._ready_until = now + READY_FOR
        return "ready"

    def _reconnect_notice(self, level: str) -> dict[str, Any]:
        if level == "plain":
            return {"stage": "reconnected", "line": voice.RECONNECTED_PLAIN, "pose": "normal"}
        line = voice.RECONNECTED
        at = self._reconnected_at.isoformat() if self._reconnected_at else ""
        event_id = f"reconnect/{at}"
        recent_now = {str(e.get("at")) for e in (self._last_status or {}).get("recent") or []}
        quiet = recent_now <= self._recent_before_drop
        if quiet and _seed(event_id) % 20 == 0:
            pool = voice.ASIDES["reconnect_quiet"]
            line = f"{line} {pool[self._memory.pick(event_id, len(pool), _seed(event_id))]}"
        return {"stage": "reconnected", "line": line, "pose": "waiting"}

    def _where(self, status: dict[str, Any] | None) -> dict[str, Any] | None:
        """Where matters currently stand (UI-SPEC 6.6). Plain at every level."""
        health = "down" if status is None else str(status.get("health") or "ok")
        if health in ("ok", "slow"):
            return None
        if status is None and not self._ever_ready:
            return None  # still starting up: the connecting line covers it
        layers = [("Pastie service", "NOT RUNNING" if health == "down" else "WORKING")]
        if health != "down":
            layers.append(("Internet", "NOT REACHABLE" if health == "offline" else "CONNECTED"))
        if health in ("auth", "schema"):
            layers.append(("Haier account", "CAN'T LOG IN" if health == "auth" else "CONNECTED"))
        if health == "schema":
            layers.append(("Haier's response", "NOT UNDERSTOOD"))
        tries = {
            "down": ["Start Pastie's background service. Alerts don't work until it's running."],
            "offline": ["Check this PC's internet connection."],
            "auth": ["Check your hOn password in Settings → Account."],
            "schema": [
                "Haier has changed something and Pastie needs an update. "
                "Alerts may be unreliable until then."
            ],
        }[health]
        return {
            "title": "WHERE MATTERS CURRENTLY STAND",
            "layers": [{"name": n, "status": s} for n, s in layers],
            "try": tries,
            "pose": "fault",
            "aside": None,
        }

    # ------------------------------------------------------------ appliances

    def _state(self, appliance: dict[str, Any]) -> str:
        if appliance.get("trust") != "verified":
            return "unknown"
        return str(appliance.get("state") or "unknown")

    def _state_word(self, appliance: dict[str, Any]) -> str:
        return STATE_WORDS.get(self._state(appliance), "STATE UNKNOWN")

    def _needs_action(self, appliance: dict[str, Any]) -> bool:
        return (
            self._state(appliance) == "fault"
            or "tank" in str(appliance.get("attention") or "").lower()
        )

    def _urgency(self, appliance: dict[str, Any]) -> tuple[int, str]:
        if appliance.get("trust") != "verified":
            return (9, str(appliance.get("name")))
        if self._needs_action(appliance):
            return (0, str(appliance.get("name")))
        return (_URGENCY.get(self._state(appliance), 8), str(appliance.get("name")))

    def _hero_id(self, appliances: list[dict[str, Any]]) -> str:
        ids = {str(a.get("id")) for a in appliances}
        pinned = self._memory.state.pinned
        at = _when(pinned.get("at"))
        if pinned.get("id") in ids and at and self._now() - at < PIN_FOR:
            return str(pinned["id"])
        verified = [a for a in appliances if a.get("trust") == "verified"]
        return str(min(verified or appliances, key=self._urgency).get("id"))

    def _severity(self, appliance: dict[str, Any]) -> str:
        if self._state(appliance) == "fault":
            return "error"
        if "tank" in str(appliance.get("attention") or "").lower():
            return "warning"
        if any(item.get("due") for item in appliance.get("maintenance") or []):
            return "maintenance"
        return "info"

    def _finish_evidenced(self, appliance_id: str) -> bool:
        """A finish proven by the state change *and* the cycle counter moving.

        Both must have been observed since the cycle started. Either order: the
        counter comes from statistics, which refresh on their own schedule.
        """
        start = _when(self._cycle_marker(appliance_id))
        saw_finish = saw_counter = False
        for row in self._memory.state.observations:
            if row.get("appliance") != appliance_id:
                continue
            at = _when(row.get("t"))
            if start and at and at < start:
                continue
            if row.get("kind") == "state" and row.get("state") == "finished":
                saw_finish = True
            if (
                row.get("kind") == "counter"
                and isinstance(row.get("before"), int)
                and row.get("after") != row.get("before")
            ):
                saw_counter = True
        return saw_finish and saw_counter

    def _pose(self, appliance: dict[str, Any], level: str, status: dict[str, Any] | None) -> str:
        severity = self._severity(appliance)
        if severity in ("warning", "error"):
            return "fault"
        if level == "plain":
            return "normal"
        state = self._state(appliance)
        if state == "unknown":
            return "unknown"
        detail = (status or {}).get("command_detail") or {}
        if detail.get("appliance_id") == appliance.get("id"):
            outcome = detail.get("outcome")
            if outcome in ("requested", "accepted"):
                return "working"
            confirmed = _when(detail.get("confirmed_at"))
            if outcome == "confirmed" and confirmed and self._now() - confirmed < TRAIL_OPEN:
                return "confirmed"
        if state == "finished":
            return "confirmed" if self._finish_evidenced(str(appliance.get("id"))) else "normal"
        if state == "running":
            return "working" if appliance.get("progress") is not None else "waiting"
        if state in ("paused", "scheduled"):
            return "waiting"
        return "normal"

    # ------------------------------------------------------------ the hero

    def _hero(
        self, appliance: dict[str, Any], status: dict[str, Any], level: str
    ) -> dict[str, Any]:
        aid = str(appliance.get("id"))
        state = self._state(appliance)
        verified = appliance.get("trust") == "verified"
        severity = self._severity(appliance)
        name = self.name_for(appliance)

        facts: dict[str, Any] = {"lines": []}
        showing_cycle = state in ("running", "paused", "finished")
        if showing_cycle and appliance.get("programme"):
            facts["programme"] = str(appliance["programme"])
        minutes = appliance.get("remaining_minutes")
        settled = bool(appliance.get("remaining_settled"))
        progress = appliance.get("progress")
        if state in ("running", "paused") and isinstance(minutes, int):
            facts["remaining"] = f"{minutes} min" if settled else f"about {minutes} min"
            facts["confidence"] = "settled" if settled else "still estimating"
            read_at = _when(appliance.get("updated_at")) or self._now()
            finish = read_at + timedelta(minutes=minutes)
            facts["completion"] = ("" if settled else "about ") + _clock(finish)
        elif state in ("running", "paused") and "remaining_minutes" not in appliance:
            # An older service sends only its own phrasing. Show that, as sent.
            text = str(appliance.get("remaining") or "unknown")
            if text != "unknown":
                estimating = "estimating" in text
                facts["remaining"] = text.replace(" (still estimating)", "")
                facts["confidence"] = "still estimating" if estimating else "settled"
            elif state == "running":
                facts["remaining"] = None
                facts["confidence"] = "still estimating"
        elif state == "running":
            facts["remaining"] = None
            facts["confidence"] = "still estimating"
        if state == "finished":
            facts["progress"] = 100
            finished_at = self._finished_at(aid)
            if finished_at:
                facts["finished_at"] = _clock(finished_at)
        elif isinstance(progress, (int, float)):
            facts["progress"] = round(float(progress) * 100)
        else:
            facts["progress"] = None

        # Plain sentences that carry an instruction. The same at every level.
        type_name = _sentence(f"the {appliance.get('name') or 'appliance'}")
        if state == "fault":
            facts["lines"].append(
                f"{type_name} has reported a fault and stopped. Check the machine's display."
            )
            if appliance.get("fault_code"):
                facts["lines"].append(f"Fault code {appliance['fault_code']}")
        attention = str(appliance.get("attention") or "")
        if "tank" in attention.lower():
            facts["lines"].append(
                f"The water tank is full, so {type_name[:1].lower()}{type_name[1:]} has "
                "stopped. Empty it and press start."
            )
        elif attention:
            facts["lines"].append(f"Waiting for: {attention}")
        if not verified:
            facts["lines"].append(
                "State unknown. Pastie has data, but no verified mapping for what this "
                "appliance means by it."
            )
        if status.get("health") == "slow":
            facts["lines"].append(
                f"Not reporting since {_clock(_when(appliance.get('updated_at')))}"
            )
        maintenance = [
            _maintenance_line(item)
            for item in appliance.get("maintenance") or []
            if item.get("due")
            or (isinstance(item.get("remaining"), int) and item["remaining"] <= 2)
        ]
        facts["maintenance"] = maintenance

        aside = None
        if severity in ("info", "maintenance") and level != "plain":
            aside = self._aside(appliance, status, level, name)

        meters: list[dict[str, Any]] = []
        if (
            level == "departmental"
            and severity in ("info", "maintenance")
            and verified
            and state in ("running", "paused", "finished")
            and (facts.get("progress") is not None)
        ):
            p = (facts["progress"] or 0) / 100
            specs = voice.METERS.get(str(appliance.get("programme") or ""), voice.METERS["default"])
            meters = [{"label": m.label, "value": curve(m.curve, p)} for m in specs]

        return {
            "id": aid,
            "name": _sentence(str(appliance.get("name") or "appliance")),
            "model": appliance.get("model") or "",
            "state": state,
            "state_word": self._state_word(appliance),
            "severity": severity,
            "pose": self._pose(appliance, level, status),
            "unverified": not verified,
            "stamps": ["UNVERIFIED"] if not verified else [],
            "facts": facts,
            "aside": aside,
            "meters": meters,
            "why": self._why(appliance),
            "actions": self._actions(appliance, level, name),
        }

    def _finished_at(self, appliance_id: str) -> datetime | None:
        row = self._last_observed(appliance_id, "state")
        if row and row.get("state") == "finished":
            return _when(row.get("t"))
        return None

    def _aside(
        self, appliance: dict[str, Any], status: dict[str, Any], level: str, name: str
    ) -> str | None:
        aid = str(appliance.get("id"))
        state = self._state(appliance)
        today = self._now().astimezone().date().isoformat()

        def say(key: str, event_id: str, **values: object) -> str:
            pool = voice.ASIDES[key]
            line = pool[self._memory.pick(event_id, len(pool), _seed(event_id))]
            return _fill(line, name, **values)

        if appliance.get("trust") != "verified":
            return say("unknown_state", f"{aid}/unknown")
        if status.get("health") == "slow":
            return say("where_dryer_silent", f"{aid}/silent/{appliance.get('updated_at')}")

        detail = status.get("command_detail") or {}
        if (
            detail.get("appliance_id") == aid
            and detail.get("outcome") == "confirmed"
            and detail.get("name") == "Start"
        ):
            confirmed = _when(detail.get("confirmed_at"))
            key = f"start_confirmed/{detail.get('id')}"
            if (
                confirmed
                and self._now() - confirmed < TRAIL_LINGER
                and (
                    key in self._memory.state.picks or self._memory.first("start_confirmed", today)
                )
            ):
                return say("start_confirmed", key)

        if state == "running":
            rise = self._rise.get(aid)
            if rise and not appliance.get("remaining_settled"):
                before, after, event_id = rise
                size = after - before
                shown = self._biggest_rise.get(aid, 0)
                if level == "departmental" or size > shown or event_id in self._memory.state.picks:
                    self._biggest_rise[aid] = max(shown, size)
                    return say("estimate_rose", event_id, before=before, after=after)
            if level == "departmental":
                minutes = appliance.get("remaining_minutes")
                if isinstance(minutes, int) and not appliance.get("remaining_settled"):
                    return say(
                        "estimate_unsettled",
                        f"{aid}/unsettled/{self._cycle_marker(aid)}",
                        minutes=minutes,
                    )
                return self._narration(aid, appliance, name)

        if any(item.get("due") for item in appliance.get("maintenance") or []):
            key = f"maintenance/{aid}/{self._cycle_marker(aid)}"
            if key in self._memory.state.picks or self._memory.first_today(
                f"maintenance/{aid}", today
            ):
                return say("maintenance_due", key)

        if state == "finished":
            key = f"finished/{aid}/{self._cycle_marker(aid)}"
            if level == "departmental":
                return self._narration(aid, appliance, name)
            if key in self._memory.state.picks or self._memory.first_today(
                f"finished/{aid}", today
            ):
                return say("finished", key)
            return None

        if state == "idle":
            if appliance.get("remote_allowed") and level == "departmental":
                return self._narration(aid, appliance, name)
            # At most one variant a day, the same all day (UI-SPEC 6.9).
            if _seed(f"{aid}/{today}") % 3 == 0:
                return self._narration(aid, appliance, name)
            return voice.IDLE_LINE[level]

        if level == "departmental" and state in ("paused", "scheduled"):
            return self._narration(aid, appliance, name)
        return None

    def _narration(self, aid: str, appliance: dict[str, Any], name: str) -> str | None:
        state = self._state(appliance)
        today = self._now().astimezone().date().isoformat()
        if state == "running":
            progress = appliance.get("progress")
            if progress is None:
                stage = "estimating"
            elif progress < 0.34:
                stage = "running_early"
            elif progress < 0.67:
                stage = "running_middle"
            else:
                stage = "running_late"
            event_id = f"narration/{aid}/{self._cycle_marker(aid)}/{stage}"
        elif state == "idle":
            stage = "armed" if appliance.get("remote_allowed") else "idle"
            event_id = f"idle/{aid}/{today}"
        elif state in ("finished", "paused", "scheduled"):
            stage = state
            event_id = f"narration/{aid}/{self._cycle_marker(aid)}/{stage}"
        else:
            return None
        pool = voice.NARRATION[stage]
        index = self._memory.pick_narration(stage, event_id, len(pool), _seed(event_id))
        return _fill(pool[index], name)

    # ------------------------------------------------------------ why

    def _why(self, appliance: dict[str, Any]) -> dict[str, Any]:
        """Explanations built from the real rule and its real inputs (UI-SPEC 6.7)."""
        out: dict[str, Any] = {}
        state = self._state(appliance)
        type_name = _sentence(f"the {appliance.get('name') or 'appliance'}")
        minutes = appliance.get("remaining_minutes")
        if state in ("running", "paused") and isinstance(minutes, int):
            if appliance.get("remaining_settled"):
                out["remaining"] = {
                    "title": f"{minutes} min · settled",
                    "body": [
                        f"{type_name} reports {minutes} minutes remaining. That is within the "
                        "programme's own length, which is the point at which this appliance "
                        "counts down about a minute a minute."
                    ],
                    "source": "Appliance telemetry",
                    "confidence": "Settled estimate",
                }
            else:
                out["remaining"] = {
                    "title": f"about {minutes} min · still estimating",
                    "body": [
                        f"{type_name} reports about {minutes} minutes. It is still measuring "
                        "the load. Until its figure falls within the programme's own length, "
                        "Pastie treats it as an estimate."
                    ],
                    "source": "Appliance telemetry",
                    "confidence": "Still estimating",
                }
        if state == "finished":
            aid = str(appliance.get("id"))
            finished_at = self._finished_at(aid)
            body = []
            if finished_at:
                body.append(
                    f"{type_name} changed to FINISHED at {_clock(finished_at, seconds=True)}."
                )
            else:
                body.append(f"{type_name} reports FINISHED.")
            counter = self._counter_move_since_start(aid)
            if counter:
                body.append(
                    f"Its completed-cycle counter also increased from {counter[0]} to {counter[1]}."
                )
            out["finished"] = {
                "title": "Finished",
                "body": body,
                "source": "Appliance state and cycle counter" if counter else "Appliance state",
                "confidence": "Confirmed" if counter else "Reported by the appliance",
            }
        if state == "unknown":
            out["state"] = {
                "title": "State unknown",
                "body": [
                    "This appliance sent values Pastie has no verified mapping for. Pastie "
                    "shows them exactly as received, in Diagnostics, and does not guess what "
                    "they mean."
                ],
                "source": "Appliance telemetry",
                "confidence": "Not known",
            }
        return out

    def _counter_move_since_start(self, appliance_id: str) -> tuple[int, int] | None:
        start = _when(self._cycle_marker(appliance_id))
        for row in reversed(self._memory.state.observations):
            if row.get("appliance") != appliance_id or row.get("kind") != "counter":
                continue
            at = _when(row.get("t"))
            if start and at and at < start:
                return None
            if isinstance(row.get("before"), int) and row.get("after") != row.get("before"):
                return (int(row["before"]), int(row["after"]))
        return None

    # ------------------------------------------------------------ actions

    def _actions(self, appliance: dict[str, Any], level: str, name: str) -> dict[str, Any]:
        commands = appliance.get("commands") or []
        state = self._state(appliance)
        if appliance.get("trust") != "verified" or not commands:
            return {"mode": "none"}
        if state in ("running", "paused") and "stopProgram" in commands:
            label = appliance.get("programme") or "current"
            return {
                "mode": "stop",
                "button": "Stop",
                "confirm": f"Stop the {label} cycle?",
            }
        if "startProgram" not in commands or state not in ("idle", "finished", "unknown"):
            return {"mode": "none"}
        if not appliance.get("remote_allowed"):
            aside = None
            if level != "plain":
                pool = voice.ASIDES["remote_not_armed"]
                event_id = f"remote/{appliance.get('id')}"
                aside = _fill(pool[self._memory.pick(event_id, len(pool), _seed(event_id))], name)
            return {
                "mode": "not_armed",
                "button": "Waiting for Remote mode",
                "fact": "Remote start is unavailable. Turn the programme dial to Remote on the "
                f"{appliance.get('name') or 'appliance'} first.",
                "aside": aside,
            }
        return {"mode": "start", "programmes": _tiles(appliance.get("programmes") or [])}

    # ------------------------------------------------------------ trail

    def _trail(
        self, appliance: dict[str, Any], status: dict[str, Any], level: str
    ) -> dict[str, Any] | None:
        """The paper trail for the hero's latest command (UI-SPEC 6.5)."""
        detail = status.get("command_detail")
        if not isinstance(detail, dict) or detail.get("appliance_id") != appliance.get("id"):
            return None
        now = self._now()
        outcome = str(detail.get("outcome"))
        requested = _when(detail.get("requested_at"))
        accepted = _when(detail.get("accepted_at"))
        confirmed = _when(detail.get("confirmed_at"))
        rejected = _when(detail.get("rejected_at"))
        deadline = float(detail.get("deadline_seconds") or 20)
        verb = str(detail.get("name") or "Command")
        rows = [{"time": _clock(requested, True), "text": "Requested", "stamp": None}]
        if accepted:
            waiting = outcome == "accepted"
            rows.append(
                {
                    "time": _clock(accepted, True),
                    "text": "Haier accepted the request"
                    + (" · Waiting for the machine itself" if waiting else ""),
                    "stamp": "AWAITING APPLIANCE" if waiting else "RECEIVED",
                }
            )
        if confirmed:
            state_word = "RUNNING" if verb == "Start" else "STOPPED"
            rows.append(
                {
                    "time": _clock(confirmed, True),
                    "text": f"Machine confirmed {state_word}",
                    "stamp": "CONFIRMED",
                }
            )

        panel = None
        if outcome == "timed_out":
            panel = {
                "title": "COMMAND NOT CONFIRMED",
                "rows": [
                    ("Haier accepted", _clock(accepted, True)),
                    ("Machine confirmation", "NOT RECEIVED"),
                    ("Waited", f"{int(deadline)} seconds"),
                ],
                "lines": [
                    "Pastie cannot establish that the machine "
                    + ("started." if verb == "Start" else "stopped."),
                    "Nothing has been marked successful.",
                ],
            }
        elif outcome == "rejected":
            panel = {
                "title": "HAIER REFUSED THE REQUEST",
                "rows": [],
                "lines": [str(detail.get("reason") or "Haier refused the request.")],
            }
        elif outcome == "refused":
            panel = {
                "title": "NOT SENT",
                "rows": [],
                "lines": [str(detail.get("reason") or "Pastie did not send the request.")],
            }

        final_at = (
            confirmed
            or rejected
            or (
                accepted + timedelta(seconds=deadline)
                if outcome == "timed_out" and accepted
                else None
            )
            or (requested if outcome == "refused" else None)
        )
        is_final = outcome in ("confirmed", "timed_out", "rejected", "refused")
        if is_final and final_at and now - final_at > TRAIL_OPEN + TRAIL_LINGER:
            return None
        collapsed = bool(is_final and final_at and now - final_at > TRAIL_OPEN)
        return {
            "title": f"{verb.upper()} CYCLE",
            "rows": rows,
            "outcome": outcome,
            "panel": panel,
            "collapsed": collapsed,
            "pose": {
                "requested": "working",
                "accepted": "working",
                "confirmed": "confirmed" if level != "plain" else "normal",
            }.get(outcome, "fault"),
        }

    # ============================================================ pages

    def history(self) -> dict[str, Any]:
        level = self.level
        rows = []
        for row in reversed(self._memory.state.observations):
            rendered = _history_row(row)
            if rendered:
                rows.append(rendered)
        return {
            "title": "History",
            "subtitle": voice.HISTORY_SUBTITLE if level == "departmental" else None,
            "rows": rows[:300],
            "empty": voice.HISTORY_EMPTY[level] if not rows else None,
            "cases": self.cases(),
        }

    def cases(self) -> list[dict[str, Any]]:
        """Case files: one per observed cycle, newest first (UI-SPEC 8)."""
        level = self.level
        cases: list[dict[str, Any]] = []
        open_case: dict[str, Any] | None = None
        observations = self._memory.state.observations
        for row in observations:
            kind = row.get("kind")
            if kind == "state" and row.get("state") == "running":
                open_case = {
                    "appliance": row.get("appliance"),
                    "opened": row.get("t"),
                    "programme": row.get("programme"),
                    "evidence": [(row.get("t"), "Machine reported RUNNING", "CONFIRMED")],
                    "closed": None,
                    "counter": None,
                    "pending": None,
                }
                cases.append(open_case)
                continue
            if open_case is None or row.get("appliance") not in (open_case["appliance"], None):
                continue
            if kind == "estimate":
                open_case["evidence"].append(
                    (
                        row.get("t"),
                        f"Estimate revised {row.get('before')} → {row.get('after')} min",
                        None,
                    )
                )
            elif kind == "attention":
                open_case["evidence"].append(
                    (row.get("t"), f"Waiting for: {row.get('what')}", None)
                )
            elif kind == "fault":
                open_case["evidence"].append(
                    (row.get("t"), f"Fault {row.get('code') or ''}".strip(), None)
                )
            elif kind == "state" and row.get("state") == "finished":
                open_case["closed"] = row.get("t")
                open_case["evidence"].append((row.get("t"), "Machine reported FINISHED", None))
                if open_case["pending"]:
                    before, after, at = open_case["pending"]
                    open_case["counter"] = after
                    open_case["evidence"].append(
                        (at, f"Cycle counter {before} → {after}", "CONFIRMED")
                    )
                    open_case = None
            elif (
                kind == "counter"
                and not open_case["closed"]
                and isinstance(row.get("before"), int)
                and row.get("after") != row.get("before")
            ):
                open_case["pending"] = (row.get("before"), row.get("after"), row.get("t"))
            elif (
                kind == "counter"
                and open_case["closed"]
                and isinstance(row.get("before"), int)
                and row.get("after") != row.get("before")
            ):
                open_case["counter"] = row.get("after")
                open_case["evidence"].append(
                    (
                        row.get("t"),
                        f"Cycle counter {row.get('before')} → {row.get('after')}",
                        "CONFIRMED",
                    )
                )
                open_case = None
            elif kind == "state" and row.get("state") not in ("running", "paused"):
                if not open_case["closed"]:
                    open_case["evidence"].append(
                        (row.get("t"), f"Machine reported {str(row.get('state')).upper()}", None)
                    )
                open_case = None

        out = []
        for case in reversed(cases):
            number = case["counter"]
            closing: list[str] = []
            if level != "plain" and case["closed"]:
                closing = list(voice.CASE_CLOSING)
                if isinstance(number, int) and number in (50, 100):
                    closing.append(voice.CASE_MILESTONE.format(count=number))
            out.append(
                {
                    "number": f"CASE {number:06d}"
                    if isinstance(number, int)
                    else "CASE (unnumbered)",
                    "title": "Completion of drying operation"
                    if case["closed"]
                    else "Drying operation",
                    "opened": _clock(_when(case["opened"]), True),
                    "closed": (
                        _clock(_when(case["closed"]), True)
                        + ("" if number is not None else " (not confirmed by counter)")
                    )
                    if case["closed"]
                    else None,
                    "programme": case["programme"],
                    "evidence": [
                        {"time": _clock(_when(t), True), "text": text, "stamp": stamp}
                        for t, text, stamp in case["evidence"]
                    ],
                    "closing": closing,
                }
            )
        return out[:100]

    def diagnostics(self, status: dict[str, Any] | None) -> dict[str, Any]:
        """What Pastie knows, infers and will not guess. Same at every level."""
        knows: list[tuple[str, str]] = []
        infers: list[tuple[str, str]] = []
        will_not: list[tuple[str, str]] = []
        for appliance in (status or {}).get("appliances") or []:
            name = _sentence(str(appliance.get("name") or "appliance"))
            if appliance.get("trust") == "verified":
                knows.append(
                    (
                        f"{name} · last reading",
                        f"{_clock(_when(appliance.get('updated_at')), True)} · verified",
                    )
                )
                knows.append((f"{name} · state", f"{self._state_word(appliance)} · verified"))
                if appliance.get("programme"):
                    knows.append((f"{name} · programme", f"{appliance['programme']} · verified"))
                if isinstance(appliance.get("remaining_minutes"), int):
                    knows.append(
                        (
                            f"{name} · remaining",
                            f"{appliance['remaining_minutes']} min · reported by the appliance",
                        )
                    )
                    infers.append(
                        (
                            f"{name} · estimate settled",
                            "yes" if appliance.get("remaining_settled") else "no",
                        )
                    )
                if isinstance(appliance.get("cycle_count"), int):
                    infers.append((f"{name} · cycle counter", str(appliance["cycle_count"])))
                if self._state(appliance) == "unknown":
                    will_not.append(
                        (f"{name} · state", "no verified mapping for the reported value")
                    )
            else:
                for key, value in sorted((appliance.get("raw") or {}).items()):
                    will_not.append((f"{name} · {key} {value}", "no verified mapping · UNVERIFIED"))
        return {
            "sections": [
                {"title": "WHAT PASTIE KNOWS", "rows": knows},
                {"title": "WHAT PASTIE IS INFERRING", "rows": infers},
                {"title": "WHAT PASTIE WILL NOT GUESS", "rows": will_not},
            ]
        }

    def guide(self, status: dict[str, Any] | None) -> dict[str, Any]:
        level = self.level
        unlocked = self._memory.state.unlocked
        footnote = self._guide_footnote(status)
        entries = []
        for entry in voice.GUIDE:
            is_open = entry.key in unlocked
            entries.append(
                {
                    "key": entry.key,
                    "title": entry.title,
                    "unlocked": is_open,
                    "condition": entry.condition,
                    "body": entry.body if is_open and level != "plain" else None,
                    "footnote": footnote if is_open else None,
                    "new": is_open and entry.key not in self._memory.state.seen_guide,
                }
            )
        return {"entries": entries}

    def guide_seen(self, key: str) -> None:
        if key not in self._memory.state.seen_guide:
            self._memory.state.seen_guide.append(key)
            self._memory.touch()
            self._memory.save()

    def guide_has_new(self) -> bool:
        seen = set(self._memory.state.seen_guide)
        return any(key not in seen for key in self._memory.state.unlocked if key != "pasties")

    def _guide_footnote(self, status: dict[str, Any] | None) -> str:
        parts = []
        for appliance in (status or {}).get("appliances") or []:
            if isinstance(appliance.get("cycle_count"), int):
                parts.append(f"Cycles observed: {appliance['cycle_count']}")
            for item in appliance.get("maintenance") or []:
                if isinstance(item.get("remaining"), int):
                    parts.append(f"{_sentence(str(item.get('name')))} due in {item['remaining']}")
        return " · ".join(parts)

    def about(self) -> dict[str, Any]:
        departmental = self.level == "departmental"
        return {
            "name": "Pastie",
            "version": __version__,
            "licence": "MIT",
            "unofficial": "Unofficial. Not affiliated with, endorsed by, or supported by Haier.",
            "repository": "https://github.com/Ryan-Clinton/pastie-hon",
            "changelog": "https://github.com/Ryan-Clinton/pastie-hon/blob/main/CHANGELOG.md",
            "changelog_label": voice.MINUTES_HEADING if departmental else "Release notes",
            "institution": voice.INSTITUTION if departmental else None,
            "institution_note": voice.INSTITUTION_NOTE if departmental else None,
            "division": voice.DIVISION if departmental else None,
            "org_chart": [list(row) for row in voice.ORG_CHART] if departmental else [],
        }

    def poke(self) -> str | None:
        """Three clicks on the pastie (UI-SPEC 7.7). Departmental, with a cooldown."""
        now = self._now()
        if self.level != "departmental":
            return None
        if self._last_poke and now - self._last_poke < POKE_COOLDOWN:
            return None
        self._last_poke = now
        event_id = f"poke/{now.isoformat()}"
        pool = voice.POKED
        return pool[self._memory.pick(event_id, len(pool), _seed(event_id))]


# ================================================================ helpers


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _fill(line: str, name: str, **values: object) -> str:
    return line.format(name=name, Name=_sentence(name), **values)


def _maintenance_line(item: dict[str, Any]) -> str:
    """ "a filter clean" becomes "Due now: filter clean" or "Filter clean due in 2 cycles"."""
    noun = str(item.get("name") or "maintenance")
    for article in ("a ", "an ", "the "):
        if noun.lower().startswith(article):
            noun = noun[len(article) :]
            break
    remaining = item.get("remaining")
    if item.get("due"):
        return f"Due now: {noun}"
    if isinstance(remaining, int):
        return f"{_sentence(noun)} due in {remaining} cycle{'s' if remaining != 1 else ''}"
    return _sentence(noun)


def _tiles(programmes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Start panel's programme tiles, with each setting marked (UI-SPEC 6.5)."""
    out = []
    for programme in programmes:
        settings = []
        for key, label, empty in (
            ("dry_levels", "Dryness", "Set by the time"),
            ("temperatures", "Temperature", None),
            ("durations", "Time", "Until dry"),
        ):
            options = programme.get(key)
            if options is None:
                continue
            settings.append(
                {
                    "key": {
                        "dry_levels": "dryLevel",
                        "temperatures": "tempLevel",
                        "durations": "dryTimeMM",
                    }[key],
                    "label": label,
                    "fixed": len(options) == 1,
                    "empty": empty if not options else None,
                    "options": [
                        {
                            "id": str(o.get("id")),
                            "label": str(o.get("label")),
                            "recommended": bool(o.get("recommended")) and len(options) > 1,
                        }
                        for o in options
                    ],
                }
            )
        out.append(
            {
                "id": str(programme.get("id")),
                "label": str(programme.get("label")),
                "button": f"Start {programme.get('label')}",
                "settings": settings,
            }
        )
    return out


def _history_row(row: dict[str, Any]) -> dict[str, Any] | None:
    at = _clock(_when(row.get("t")))
    kind = row.get("kind")
    if kind == "state":
        state = str(row.get("state"))
        text = {
            "running": "Cycle started",
            "finished": "Cycle finished",
            "paused": "Cycle paused",
            "fault": "Fault reported",
            "idle": "Idle",
        }.get(state, f"State {state.upper()}")
        detail = row.get("programme") if state == "running" else None
        return {
            "time": at,
            "text": text,
            "detail": detail,
            "stamp": "CONFIRMED" if state == "running" else None,
        }
    if kind == "estimate":
        return {
            "time": at,
            "text": f"Remaining time changed {row.get('before')} → {row.get('after')} min",
            "detail": None,
            "stamp": None,
        }
    if kind == "counter" and isinstance(row.get("before"), int):
        return {
            "time": at,
            "text": f"Cycle counter {row.get('before')} → {row.get('after')}",
            "detail": None,
            "stamp": None,
        }
    if kind == "gap":
        return {
            "time": at,
            "text": str(row.get("message") or "A cycle completed while Pastie was offline"),
            "detail": "Evidenced by the cycle counter",
            "stamp": "RECOVERED",
        }
    if kind == "attention":
        return {
            "time": at,
            "text": f"Waiting for: {row.get('what')}",
            "detail": None,
            "stamp": None,
        }
    if kind == "fault":
        return {
            "time": at,
            "text": f"Fault {row.get('code') or ''}".strip(),
            "detail": None,
            "stamp": None,
        }
    if kind == "command":
        outcome = str(row.get("outcome"))
        stamp = {
            "confirmed": "CONFIRMED",
            "timed_out": None,
            "rejected": None,
            "refused": None,
        }.get(outcome)
        text = f"{row.get('name')} requested"
        detail = {
            "confirmed": "confirmed by the machine",
            "timed_out": "accepted by Haier, not confirmed by the machine",
            "rejected": "refused by Haier",
            "refused": "not sent",
        }.get(outcome)
        return {"time": at, "text": text, "detail": detail, "stamp": stamp}
    return None
