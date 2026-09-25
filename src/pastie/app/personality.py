"""Personality sheets: every character in the cast, configurable by the owner.

docs/UI-SPEC.md 7.9. It is the owner's house and their fiction, so everything
about how Pastie speaks of an appliance, the Household or itself can be set:
names, temperament, Pastie's stance, the personality level, the lines, the
meters. What no sheet can do is enforced in the presenter, not here, and not by
good behaviour: change a fact, a stamp or a pose's link to real state, or put a
joke on anything needing action.

Sheets are TOML, one file per cast member, in the window's own folder under
the user's profile: presentation belongs to the window, never to the service.
They can be exported and imported, so a household can share "Pastie, but it
despises the projector". An import applies what is valid and reports the rest.
"""

from __future__ import annotations

import logging
import re
import string
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

from pastie.app import voice

log = logging.getLogger(__name__)

HOUSEHOLD = "household"
PASTIE = "pastie"

LEVELS = ("follow", "plain", "dry", "departmental")
CURVES = ("rising", "peaking", "late")

#: Pools an appliance sheet may edit: the narration stages and the reactive
#: asides. There is deliberately no pool for faults, the tank, logins or
#: anything else somebody must act on, so there is nothing to edit there.
APPLIANCE_POOLS = (*voice.NARRATION.keys(), *voice.ASIDES.keys())
#: The Household's own lines join the idle and finished narration.
HOUSEHOLD_POOLS = ("household",)
#: Pastie's signature lines join the three-click aside.
PASTIE_POOLS = ("poked",)

#: Keys that could only ever be about something needing action. A line keyed
#: to one of these is refused when saved, with the reason (UI-SPEC 7.9, limit 2).
PLAIN_KEYS = ("fault", "tank", "needs_emptying", "auth", "login", "error", "safety", "warning")

#: What a line may contain in braces - the placeholders the presenter fills.
PLACEHOLDERS = {"name", "Name", "minutes", "before", "after", "count", "household", "household_s"}

LONG = 160


@dataclass
class Pool:
    """The owner's changes to one shipped pool."""

    #: Shipped lines switched off, by their exact text (robust to reordering).
    disabled: list[str] = field(default_factory=list)
    #: The owner's own lines, stored exactly as written.
    added: list[str] = field(default_factory=list)
    #: Use only the owner's lines, ignoring every shipped one.
    replace: bool = False


@dataclass
class Meter:
    label: str
    curve: str


@dataclass
class Sheet:
    """One cast member's personality."""

    key: str
    #: What Pastie calls it inside asides ("the dryer", "Big Dave"). Never facts.
    name: str = ""
    temperament: str = "Indecisive"
    stance: str = "Professional"
    #: follow (the global level) | plain | dry | departmental
    level: str = "follow"
    #: Up to three joke meters replacing the programme's shipped set.
    meters: list[Meter] = field(default_factory=list)
    #: Whether this personality reaches spoken announcements. Needs a service
    #: change before it can do anything (UI-SPEC 11, question 8).
    speech: bool = False
    pools: dict[str, Pool] = field(default_factory=dict)


# ============================================================ validation


@dataclass
class Check:
    """What the editor shows as a line is typed."""

    refused: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.refused is None


def check_line(pool: str, line: str) -> Check:
    """Validate an owner's line for a pool (UI-SPEC 7.9 limits 2, 6 and 7)."""
    text = line.strip()
    if not text:
        return Check(refused="A line can't be empty.")
    if any(plain in pool.lower() for plain in PLAIN_KEYS):
        return Check(
            refused="Faults, a full tank and anything somebody must act on are always plain, "
            "so they have no lines to add to."
        )
    try:
        fields = {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError:
        return Check(refused="A brace isn't closed. Use {name} for the appliance's name.")
    unknown = sorted(f for f in fields if f not in PLACEHOLDERS)
    if unknown:
        return Check(
            refused=f"Pastie doesn't know what to put in {{{unknown[0]}}}. "
            "You can use {name}, {Name}, {household} and, where they make sense, "
            "{minutes}, {before} and {after}."
        )
    warnings = []
    if len(text) > LONG:
        warnings.append(f"This is {len(text)} characters; the screen fits {LONG} at its narrowest.")
    lowered = text.lower()
    borrowed = [term for term in voice.BORROWED if term in lowered]
    if borrowed:
        warnings.append(
            f"This borrows from somebody else's books ({borrowed[0]}). It's your house, "
            "so it's allowed, but Pastie's own lines don't."
        )
    return Check(warnings=warnings)


# ============================================================ effective pools


def shipped(pool: str) -> tuple[str, ...]:
    if pool in voice.NARRATION:
        return voice.NARRATION[pool]
    if pool in voice.ASIDES:
        return voice.ASIDES[pool]
    if pool == "poked":
        return voice.POKED
    return ()


def effective(
    sheet: Sheet | None, pool: str, base: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    """The lines a pool actually offers, with the owner's changes applied.

    Never empty while there is anything to offer: if every line is switched off
    and nothing is added, the shipped pool is used rather than falling silent
    in a way that would look like a fault.
    """
    lines = tuple(base if base is not None else shipped(pool))
    changes = sheet.pools.get(pool) if sheet else None
    if changes is None:
        return lines
    kept = () if changes.replace else tuple(line for line in lines if line not in changes.disabled)
    own = tuple(line for line in changes.added if check_line(pool, line).ok)
    return (kept + own) or lines


def temperament_lines(sheet: Sheet | None, group: str) -> tuple[str, ...]:
    if sheet is None:
        return ()
    return voice.TEMPERAMENT_LINES.get(sheet.temperament, {}).get(group, ())


def stance_lines(sheet: Sheet | None) -> tuple[str, ...]:
    return voice.STANCE_LINES.get(sheet.stance if sheet else "Professional", ())


# ============================================================ storage


def key_for(appliance_name: str) -> str:
    """ "tumble dryer" -> "tumble-dryer": one sheet per appliance type."""
    return re.sub(r"[^a-z0-9]+", "-", appliance_name.lower()).strip("-") or "appliance"


def default_sheet(key: str) -> Sheet:
    if key == HOUSEHOLD:
        return Sheet(key=key, name="the Household")
    if key == PASTIE:
        return Sheet(key=key, name="Pastie")
    return Sheet(key=key, name=f"the {key.replace('-', ' ')}")


def to_toml(sheet: Sheet) -> str:
    data: dict[str, Any] = {
        "sheet": {
            "key": sheet.key,
            "name": sheet.name,
            "temperament": sheet.temperament,
            "stance": sheet.stance,
            "level": sheet.level,
            "speech": sheet.speech,
        }
    }
    if sheet.meters:
        data["meters"] = [{"label": m.label, "curve": m.curve} for m in sheet.meters]
    if sheet.pools:
        data["pools"] = {
            name: {"disabled": pool.disabled, "added": pool.added, "replace": pool.replace}
            for name, pool in sorted(sheet.pools.items())
            if pool.disabled or pool.added or pool.replace
        }
    return tomli_w.dumps(data)


def from_toml(text: str, *, key: str | None = None) -> tuple[Sheet, list[str]]:
    """A sheet from TOML, keeping what is valid and saying what was dropped."""
    dropped: list[str] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"That isn't a personality pack Pastie can read: {error}") from error
    raw_head = data.get("sheet")
    head: dict[str, Any] = raw_head if isinstance(raw_head, dict) else {}
    sheet_key = key or str(head.get("key") or "")
    if not sheet_key:
        raise ValueError("The pack doesn't say who it's for.")
    sheet = default_sheet(sheet_key)

    name = head.get("name")
    if isinstance(name, str) and name.strip():
        sheet.name = name.strip()[:60]
    for attribute, allowed in (
        ("temperament", voice.TEMPERAMENTS),
        ("stance", voice.STANCES),
        ("level", LEVELS),
    ):
        value = head.get(attribute)
        if value is None:
            continue
        if value in allowed:
            setattr(sheet, attribute, value)
        else:
            dropped.append(f"{attribute} {value!r} isn't one Pastie knows")
    if isinstance(head.get("speech"), bool):
        sheet.speech = head["speech"]

    for item in data.get("meters") or []:
        if not isinstance(item, dict):
            continue
        label, curve = str(item.get("label") or "").strip(), item.get("curve")
        if label and curve in CURVES and len(sheet.meters) < 3:
            sheet.meters.append(Meter(label[:40], str(curve)))
        else:
            dropped.append(f"meter {label or '?'!r}")

    allowed_pools = _pools_for(sheet_key)
    for pool_name, raw in (data.get("pools") or {}).items():
        if pool_name not in allowed_pools or not isinstance(raw, dict):
            dropped.append(f"lines for {pool_name!r}, which has no pool")
            continue
        pool = Pool(replace=bool(raw.get("replace")))
        pool.disabled = [str(x) for x in raw.get("disabled") or [] if isinstance(x, str)]
        for line in raw.get("added") or []:
            check = check_line(pool_name, str(line))
            if check.ok:
                pool.added.append(str(line).strip())
            else:
                dropped.append(f"a line for {pool_name}: {check.refused}")
        sheet.pools[pool_name] = pool
    return sheet, dropped


def _pools_for(key: str) -> tuple[str, ...]:
    if key == HOUSEHOLD:
        return HOUSEHOLD_POOLS
    if key == PASTIE:
        return PASTIE_POOLS
    return APPLIANCE_POOLS


class PersonalityStore:
    """The sheets, loaded from and saved to one folder of TOML files."""

    def __init__(self, folder: Path | None) -> None:
        self._folder = folder
        self._sheets: dict[str, Sheet] = {}
        if folder is not None and folder.is_dir():
            for path in sorted(folder.glob("*.toml")):
                try:
                    sheet, dropped = from_toml(path.read_text(encoding="utf-8"), key=path.stem)
                except (OSError, ValueError) as error:
                    log.warning(
                        "personality %s unreadable, using the default: %s", path.name, error
                    )
                    continue
                if dropped:
                    log.warning("personality %s: ignored %s", path.name, "; ".join(dropped))
                self._sheets[sheet.key] = sheet

    def members(self) -> list[str]:
        """Every cast member with a sheet of the owner's."""
        return sorted(self._sheets)

    def get(self, key: str) -> Sheet | None:
        """The owner's sheet, or None when they haven't made one."""
        return self._sheets.get(key)

    def sheet(self, key: str) -> Sheet:
        """The owner's sheet, or the default to start editing from."""
        return self._sheets.get(key) or default_sheet(key)

    def save(self, sheet: Sheet) -> None:
        self._sheets[sheet.key] = sheet
        if self._folder is None:
            return
        self._folder.mkdir(parents=True, exist_ok=True)
        (self._folder / f"{sheet.key}.toml").write_text(to_toml(sheet), encoding="utf-8")

    def reset(self, key: str, pool: str | None = None) -> Sheet:
        """Reset a whole sheet, or one pool of it, to exactly what ships."""
        if pool is None:
            self._sheets.pop(key, None)
            if self._folder is not None:
                (self._folder / f"{key}.toml").unlink(missing_ok=True)
            return default_sheet(key)
        sheet = self.sheet(key)
        sheet.pools.pop(pool, None)
        self.save(sheet)
        return sheet

    def import_pack(self, text: str, key: str | None = None) -> tuple[Sheet, list[str]]:
        sheet, dropped = from_toml(text, key=key)
        self.save(sheet)
        return sheet, dropped
