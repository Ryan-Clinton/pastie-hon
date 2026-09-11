"""Keeping only what is known to be safe.

Haier's response about your appliance contains its registered **GPS
coordinates**, its MAC address, its serial number and an account identifier.
Anything that leaves this machine - a recorded test fixture, a diagnostic
attached to an issue, a log line - has to have those gone.

The rule is an allow-list, and that is not a stylistic preference. Removing
known-bad fields one at a time fails the moment Haier adds a new one, and they
can add whatever they like whenever they like. Keeping only fields that have
been looked at cannot fail that way: a new field is simply absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Identity fields that are safe to keep. Nothing here identifies a person, a
#: household or a specific unit - only what kind of machine it is.
SAFE_IDENTITY_FIELDS = frozenset(
    {
        "applianceTypeName",
        "applianceTypeId",
        "applianceModelId",
        "modelName",
        "brand",
        "series",
        "fwVersion",
        "eepromName",
    }
)

#: Live parameters that are safe to keep. All of them are small numbers
#: describing what the machine is doing this minute.
SAFE_PARAMETERS = frozenset(
    {
        "machMode",
        "prPhase",
        "prCode",
        "programClass",
        "dryLevel",
        "tempLevel",
        "texture",
        "remainingTimeMM",
        "dryTimeMM",
        "delayTime",
        "remainingStandbyTime",
        "antiCreaseTime",
        "doorStatus",
        "lockStatus",
        "onOffStatus",
        "pause",
        "remoteCtrValid",
        "errors",
        # The dryer's notification channel. Observed on the HD90: 1 when
        # lightweight items reach iron-dry, 4 when the water tank is full. It was
        # missing from this list, which meant the change journal - built to catch
        # exactly this - saw the tank fill and recorded only "paused".
        "message",
        "buzzerDisabled",
        "dryMode",
        "airWashMode",
        "anionStatus",
        "delicateStatus",
        "fastDryStatus",
        "ironingStatus",
        "ironRemindStatus",
        "mitesRemovalStatus",
        "sterilizationStatus",
        "steamLevel",
        "spinSpeed",
        "temp",
        "waterHard",
    }
)

#: Statistics that are safe to keep: counters and service schedules.
SAFE_STATISTICS = frozenset(
    {
        "programsCounter",
        "filterCleaning",
        "drumCleaning",
        "sprayArmsCleaning",
        "loadingPercentage",
        "mostUsedPrograms",
    }
)


def scrub_identity(appliance: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the identity fields on the allow-list.

    The dropped ones include `coords`, `macAddress`, `serialNumber`, `PK` and
    `sfPersonAccountId`. They are not named in the code that removes them,
    because naming them is what makes a stripper go stale.
    """
    return {key: appliance[key] for key in sorted(appliance) if key in SAFE_IDENTITY_FIELDS}


def scrub_parameters(parameters: Mapping[str, Any]) -> dict[str, str]:
    """Keep only allow-listed parameters, as plain strings."""
    return {
        key: _as_text(parameters[key])
        for key in sorted(parameters)
        if key in SAFE_PARAMETERS and parameters[key] is not None
    }


def scrub_statistics(statistics: Mapping[str, Any] | None) -> dict[str, Any]:
    if not statistics:
        return {}
    return {key: statistics[key] for key in sorted(statistics) if key in SAFE_STATISTICS}


def _as_text(value: Any) -> str:
    """The client hands back its own attribute objects as often as plain values."""
    return str(getattr(value, "value", value))
