"""One reading from Haier, and how it becomes a `Snapshot`.

`translate` is a pure function: raw fields in, plain-language snapshot out, no
network and no clock of its own. That is what lets the recorded sequences in
`tests/fixtures` stand in for an appliance - and it is where the field names
`machMode`, `prPhase` and `remoteCtrValid` stop. Past this point they do not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pastie.connector.profiles import Profile
from pastie.core.state import ApplianceState, Maintenance, Snapshot

#: Values of the error field that mean "no error". The machine reports a fault
#: code as a non-zero string; zeroes and blanks are the quiet case.
_NO_FAULT = {"", "0", "00", "0.0", "none", "null"}

#: Statistics key -> what to call it in a sentence a person reads.
_MAINTENANCE_LABELS = {
    "filterCleaning": "a filter clean",
    "drumCleaning": "a drum clean",
    "sprayArmsCleaning": "a spray-arm clean",
}


@dataclass(frozen=True)
class RawReading:
    """Exactly what came back, already stripped to the allow-list.

    This is the recorded unit: a fixture is a list of these, and replaying one
    through `translate` and the tracker exercises the whole pipeline without an
    appliance, a network or a Windows service.
    """

    appliance_id: str
    observed_at: datetime
    parameters: dict[str, str] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    programme_name: str | None = None
    #: The name the owner gave the appliance. Never recorded in a fixture.
    nickname: str | None = None

    @property
    def appliance_type(self) -> str:
        return str(self.identity.get("applianceTypeName", ""))

    @property
    def model(self) -> str:
        return str(self.identity.get("modelName", ""))

    def to_json(self) -> dict[str, Any]:
        return {
            "appliance_id": self.appliance_id,
            "observed_at": self.observed_at.isoformat(),
            "identity": self.identity,
            "parameters": self.parameters,
            "statistics": self.statistics,
            "programme_name": self.programme_name,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RawReading:
        return cls(
            appliance_id=str(data["appliance_id"]),
            observed_at=datetime.fromisoformat(str(data["observed_at"])),
            parameters=dict(data.get("parameters") or {}),
            identity=dict(data.get("identity") or {}),
            statistics=dict(data.get("statistics") or {}),
            programme_name=data.get("programme_name"),
        )


def translate(reading: RawReading, profile: Profile) -> Snapshot:
    """Turn one raw reading into plain language, saying only what we can stand up."""
    state = profile.state_for(reading.parameters.get("machMode"))
    running = state in (ApplianceState.RUNNING, ApplianceState.PAUSED)

    total = _minutes(reading.parameters.get("dryTimeMM"))
    # Outside a running cycle the machine reports the selected programme's
    # nominal length here, not a countdown. Presenting that as "time remaining"
    # would put a number on something that is not happening.
    remaining = _minutes(reading.parameters.get("remainingTimeMM")) if running else None

    # Early in a cycle the machine is still measuring how wet the load is, and
    # its estimate wanders - it can exceed the fixed total for the programme.
    # Once it is inside the total it is counting down honestly, about a minute a
    # minute. That comparison is the only settled-ness test the appliance gives
    # us that does not require remembering earlier readings.
    settled = remaining is not None and total is not None and remaining <= total

    return Snapshot(
        appliance_id=reading.appliance_id,
        observed_at=reading.observed_at,
        state=state,
        trust=profile.trust,
        name=_name(reading, profile),
        model=reading.model,
        programme=profile.programme_for(reading.programme_name),
        remaining=remaining,
        total=total,
        remaining_is_settled=settled,
        progress=_progress(remaining, total) if settled else None,
        door_open=_flag(reading.parameters.get("doorStatus")),
        remote_allowed=_flag(reading.parameters.get("remoteCtrValid")),
        fault_code=_fault(reading, profile, state),
        attention=profile.attention_for(reading.parameters.get("message")),
        cycle_count=_counter(reading.statistics.get("programsCounter")),
        maintenance=_maintenance(reading.statistics),
        raw=_diagnostics(reading, profile),
    )


def _name(reading: RawReading, profile: Profile) -> str:
    """What to call the appliance in a sentence.

    Whatever the owner named it, unless they never named it - hOn then hands
    back the model number, and "The HD90-A2959R-UK has finished" is a worse
    sentence than "The tumble dryer has finished".
    """
    nickname = (reading.nickname or "").strip()
    if not nickname or nickname.casefold() == reading.model.strip().casefold():
        return profile.label
    return nickname


def _fault(reading: RawReading, profile: Profile, state: ApplianceState) -> str | None:
    """The fault code, but only where somebody has confirmed what it means.

    An unverified appliance reaching a state we would call a fault gets nothing:
    mode 6 meaning an error on a dryer is no reason to alarm the owner of an
    oven that happens to report a 6.
    """
    if not profile.faults_verified or state is not ApplianceState.FAULT:
        return None
    code = str(reading.parameters.get("errors", "")).strip()
    return None if code.lower() in _NO_FAULT else code


def _diagnostics(reading: RawReading, profile: Profile) -> dict[str, Any]:
    """Raw values for the diagnostics view, labelled as raw.

    The phase is included as a number *and* as words, with the words marked
    unconfirmed where they are: on the tested dryer the phase numbers look like
    they run the opposite way from the community's shared mapping, and printing
    a confident "drying" over the top of that would bury the discrepancy instead
    of surfacing it.
    """
    out: dict[str, Any] = dict(reading.parameters)
    phase = reading.parameters.get("prPhase")
    if phase is not None and phase in profile.phases:
        words = profile.phases[phase]
        out["phase"] = words if profile.phases_verified else f"{words} (unconfirmed)"
    return out


def _maintenance(statistics: dict[str, Any]) -> tuple[Maintenance, ...]:
    """Service intervals the appliance keeps for itself.

    The machine reports its own schedule - filter every 15 cycles, drum every
    100 - so nobody has to carry per-model service knowledge to use this.
    """
    out = []
    for key, label in _MAINTENANCE_LABELS.items():
        item = statistics.get(key)
        if not isinstance(item, dict):
            continue
        interval = _counter(item.get("tot"))
        used = _counter(item.get("count"))
        if interval is None or used is None or interval <= 0:
            continue
        out.append(Maintenance(name=label, interval=interval, used=used))
    return tuple(out)


def _minutes(value: str | None) -> timedelta | None:
    number = _counter(value)
    return timedelta(minutes=number) if number is not None and number >= 0 else None


def _counter(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _flag(value: str | None) -> bool | None:
    if value is None:
        return None
    return str(value).strip() not in ("0", "", "false", "False")


def _progress(remaining: timedelta | None, total: timedelta | None) -> float | None:
    if remaining is None or total is None or total.total_seconds() <= 0:
        return None
    done = 1.0 - (remaining.total_seconds() / total.total_seconds())
    return min(1.0, max(0.0, done))
