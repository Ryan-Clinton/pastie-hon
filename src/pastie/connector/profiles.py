"""What an appliance's numbers mean.

This is the only place in Pastie where Haier's numbers are given meanings, and
it is deliberately declarative: adding an appliance type should be writing down
what you have confirmed, not writing code.

**Two different questions, which are easy to confuse:**

    Does Haier's data say this setting can be changed?
    Have *we* actually checked what changing it does?

Only the second one is recorded here, and only for hardware somebody owns.
Verification is per-mapping, not per-appliance: you do not have to prove out an
entire oven before anything works. Confirm what "running" looks like, mark that
mapping verified, and leave the rest raw until somebody gets to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pastie.core.state import ApplianceState, Trust


@dataclass(frozen=True)
class Profile:
    """A description of one appliance type, as far as anyone has confirmed it.

    `states_verified` is the load-bearing flag. False means the whole appliance
    is treated as unverified: detection and raw diagnostics only, no interpreted
    state, no fault alerts, no commands.
    """

    appliance_type: str
    label: str
    states: Mapping[str, ApplianceState] = field(default_factory=dict)
    states_verified: bool = False
    #: Whether the error field has been confirmed to mean what we think.
    #: Unverified faults are shown as raw diagnostics and never alerted on.
    faults_verified: bool = False
    #: Raw phase number -> words. Cosmetic; never drives an alert.
    phases: Mapping[str, str] = field(default_factory=dict)
    phases_verified: bool = False
    #: Haier's programme identifiers -> something a person would say.
    programmes: Mapping[str, str] = field(default_factory=dict)
    dry_levels: Mapping[str, str] = field(default_factory=dict)
    temperatures: Mapping[str, str] = field(default_factory=dict)
    #: Commands confirmed to work on real hardware of this type. Anything not
    #: listed here is not offered, whatever Haier's data claims is available.
    commands: frozenset[str] = frozenset()
    #: Notification code -> what somebody needs to do about it. Only codes that
    #: stop the machine and wait for a person belong here; each one confirmed
    #: against real hardware, never inferred from a translation file.
    messages: Mapping[str, str] = field(default_factory=dict)

    @property
    def trust(self) -> Trust:
        return Trust.VERIFIED if self.states_verified else Trust.UNVERIFIED

    def state_for(self, machine_mode: str | None) -> ApplianceState:
        if not self.states_verified or machine_mode is None:
            return ApplianceState.UNKNOWN
        return self.states.get(str(machine_mode), ApplianceState.UNKNOWN)

    def attention_for(self, code: str | None) -> str | None:
        """What the machine is waiting for, if its notification code says.

        Unverified appliances get nothing, for the same reason they get no
        interpreted state: a 4 meaning "empty the tank" on a dryer is no reason
        to tell the owner of an oven to go and empty something.
        """
        if not self.states_verified or code is None:
            return None
        return self.messages.get(str(code).strip())

    def programme_for(self, name: str | None) -> str | None:
        if not name or name.lower() in _NO_PROGRAMME:
            return None
        return self.programmes.get(name, name)


_NO_PROGRAMME = {"no program", "no programme", "none", ""}


# --------------------------------------------------------------------- dryer

#: Confirmed on a Haier HD90-A2959R-UK over repeated cycles, and cross-checked
#: against the community's shared constants.
#:
#: One difference from those constants is deliberate and load-bearing: upstream
#: labels mode 7 (END_MODE) as "ready", grouping it with 0 and 1. On this machine
#: 7 is the finish signal - it is what the appliance sits in after a completed
#: cycle, and what the working prototype has alerted on for months. Treating it
#: as "ready" would mean never noticing a cycle had ended.
TUMBLE_DRYER = Profile(
    appliance_type="TD",
    label="tumble dryer",
    states={
        "0": ApplianceState.IDLE,  # NO_STATE
        "1": ApplianceState.IDLE,  # SELECTION_MODE
        "2": ApplianceState.RUNNING,  # EXECUTION_MODE
        "3": ApplianceState.PAUSED,  # PAUSE_MODE
        "4": ApplianceState.SCHEDULED,  # DELAY_START_SELECTION_MODE
        "5": ApplianceState.SCHEDULED,  # DELAY_START_EXECUTION_MODE
        "6": ApplianceState.FAULT,  # ERROR_MODE
        "7": ApplianceState.FINISHED,  # END_MODE - see the note above
        "8": ApplianceState.IDLE,  # TEST_MODE
        "9": ApplianceState.RUNNING,  # STOP_MODE - still winding down
    },
    states_verified=True,
    faults_verified=True,
    # Flagged unconfirmed in the specification's appendix: on this machine the
    # phase numbers appear to be the opposite way round from the shared mapping,
    # with "drying" behaving like the early sensing stage. Until somebody with a
    # second HD90 confirms it either way, phases are shown as raw diagnostics.
    phases={
        "0": "ready",
        "1": "heating",
        "2": "drying",
        "3": "cooling down",
        "11": "ready",
        "13": "cooling down",
        "14": "heating",
        "15": "heating",
        "16": "cooling down",
        "18": "tumbling",
        "19": "drying",
        "20": "drying",
    },
    phases_verified=False,
    programmes={
        "iot_dry_mixed": "Mixed load",
        "iot_dry_cotton": "Cotton",
        "iot_dry_bed_linen": "Bed linen",
        "hqd_towel": "Towels",
        "iot_dry_synthetics": "Synthetics",
        "iot_dry_delicates": "Delicates",
        "hqd_wool": "Wool",
        "iot_dry_rapid_30": "Rapid 30",
        "iot_dry_rapid_59": "Rapid 59",
        "iot_dry_shirts": "Shirts",
        "iot_dry_duvet": "Duvet",
        "hqd_night_dry": "Night dry",
        "hqd_mix": "Mixed load",
        "hqd_cotton": "Cotton",
    },
    dry_levels={
        "0": "No dry",
        "11": "No dry",
        "12": "Iron dry",
        "13": "Cupboard dry",
        "14": "Ready to wear",
        "15": "Extra dry",
    },
    # No "1" (Cool): the machine rejects it outright - "Allowed: min 2 max 4
    # step 1 But was: 1" - so offering it only produces a start that quietly
    # drops the setting. What the appliance refuses, we do not put in a dropdown.
    temperatures={"2": "Low", "3": "Middle", "4": "High"},
    # Both confirmed against the machine. `stopProgram` is in the list because it
    # was tested - and the test is what proved it can be accepted and ignored.
    commands=frozenset({"startProgram", "stopProgram"}),
    # Observed 2026-09-11, 22:07:45, in a single pushed update, the moment the
    # machine's own tank alarm sounded:
    #
    #     pause 0 -> 1,  message 0 -> 4,  machMode 2 -> 3
    #
    # prPhase stayed at 19 throughout. Haier's translations carry a
    # PHASE_ERROR_FULL_TANK string, which led to a guess that the tank was one of
    # the community's "unknown" phases 8, 12 or 17. On this machine it is not a
    # phase at all.
    #
    # And it cleared just as cleanly, the moment the tank was emptied and the
    # machine restarted - 22:17:59, one pushed update, the exact mirror:
    #
    #     pause 1 -> 0,  message 4 -> 0,  machMode 3 -> 2
    #
    # Also seen, and deliberately *not* listed because nothing is waiting on a
    # person: message 1, arriving with ironingStatus 1 and clearing two minutes
    # later - Haier's "lightweight items are dry" notification.
    messages={"4": "the water tank is full"},
)


#: Every other appliance type Haier's system covers. Detected, named, and shown
#: as raw numbers - because guessing what a value means on an oven or an
#: induction hob is a different proposition from guessing on a dryer.
KNOWN_TYPES = {
    "WM": "washing machine",
    "WD": "washer dryer",
    "DW": "dishwasher",
    "OV": "oven",
    "IH": "induction hob",
    "HO": "cooker hood",
    "REF": "fridge",
    "AC": "air conditioner",
    "WC": "wine cellar",
    "AP": "air purifier",
}

_PROFILES = {TUMBLE_DRYER.appliance_type: TUMBLE_DRYER}


def unverified(appliance_type: str) -> Profile:
    """A profile for hardware nobody here has confirmed.

    It still gets a name, so the window can say "washing machine" rather than
    "WM", and its raw values are still shown as diagnostics. It gets nothing
    that would require understanding them.
    """
    return Profile(
        appliance_type=appliance_type,
        label=KNOWN_TYPES.get(appliance_type, appliance_type.lower() or "appliance"),
    )


def for_appliance(appliance_type: str | None) -> Profile:
    """The profile for an appliance type, verified or otherwise. Never fails."""
    key = (appliance_type or "").upper()
    return _PROFILES.get(key) or unverified(key)


def verified_types() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))
