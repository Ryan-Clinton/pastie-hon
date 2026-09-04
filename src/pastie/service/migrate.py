"""Moving a prototype installation onto the real thing.

The prototype kept its account in a plain text `.credentials` file and its alert
settings in `hue_alert.json`, both next to the script. Anyone who has been
running it has those files, and asking them to type everything in again - and to
find their Hue key a second time - is a poor welcome.

So this reads them once and writes them where they belong: the password into the
encrypted store under the service's own identity, everything else into the
settings document. The prototype's files are left alone; deleting somebody's
credentials file on their behalf is not this program's decision, and the advice
to remove it belongs in what we print, not in what we do.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pastie.service.config import SettingsStore
from pastie.service.secrets import Credentials, SecretStore

log = logging.getLogger(__name__)

#: (bridge address, key, v1 light number) -> that light's name, and every v2
#: light's id and name. Injected so the matching can be tested without a bridge.
LightLookup = Callable[[str, str, str], tuple[str, dict[str, str]]]


@dataclass
class Migration:
    """What was found, and what was done with it."""

    account: str = ""
    messengers: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: A v1 Hue light number still to be matched to its v2 id. Set by `plan`,
    #: which does no network; resolved by `apply`, which may.
    pending_light: str = ""

    @property
    def anything(self) -> bool:
        return bool(self.account or self.messengers)


def read_credentials_file(path: Path) -> dict[str, str]:
    """The prototype's `key=value` file, with comments and blank lines ignored."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


def plan(folder: Path) -> Migration:
    """Work out what a prototype folder has to offer. Reads only."""
    migration = Migration()
    credentials = read_credentials_file(folder / ".credentials")

    if credentials.get("user") and credentials.get("password"):
        migration.account = credentials["user"]

    if credentials.get("hue_bridge") and credentials.get("hue_key"):
        hue: dict[str, Any] = {
            "enabled": True,
            "address": credentials["hue_bridge"],
            "key": credentials["hue_key"],
        }
        alert = _read_json(folder / "hue_alert.json")
        if alert.get("light") is not None:
            # v1 numbered its lights; v2 identifies them by a long id. The number
            # on its own means nothing to v2 - but both APIs know the light's
            # *name*, and the bridge still answers v1, so the two can be matched
            # up without asking the user to find their light again.
            hue["light"] = ""
            migration.pending_light = str(alert["light"])
        for key in ("colour", "seconds"):
            if alert.get(key) is not None:
                hue[key] = alert[key]
        if alert.get("brightness") is not None:
            hue["brightness"] = _brightness_to_v2(alert["brightness"])
        if alert.get("restore") is not None:
            hue["restore"] = bool(alert["restore"])
        migration.messengers["hue"] = hue

    alert = _read_json(folder / "hue_alert.json")
    if alert.get("speak_enabled") or alert.get("speak_device"):
        cast: dict[str, Any] = {
            "enabled": bool(alert.get("speak_enabled")),
            "device": str(alert.get("speak_device", "")),
            "text": str(alert.get("speak_text", "The tumble dryer has finished.")),
        }
        if alert.get("speak_volume") is not None:
            cast["volume"] = alert["speak_volume"]
        hosts = _read_json(folder / "cast_hosts.json")
        address = hosts.get(cast["device"])
        if isinstance(address, str):
            cast["address"] = address
        migration.messengers["cast"] = cast

    return migration


def apply(
    folder: Path,
    secrets: SecretStore,
    settings: SettingsStore,
    migration: Migration | None = None,
    *,
    lookup: LightLookup | None = None,
) -> Migration:
    """Carry out a plan. The prototype's own files are not touched."""
    migration = migration or plan(folder)
    credentials = read_credentials_file(folder / ".credentials")

    if migration.account and credentials.get("password"):
        secrets.save(Credentials(migration.account, credentials["password"]))

    hue = migration.messengers.get("hue")
    if hue and migration.pending_light:
        _match_light(migration, hue, lookup or _bridge_lookup)

    for name, values in migration.messengers.items():
        settings.update_messenger(name, values)
    return migration


def _match_light(migration: Migration, hue: dict[str, Any], lookup: LightLookup) -> None:
    """Find the v2 id of the light the prototype was flashing.

    Both APIs know the light by the same name, so the number the prototype
    stored can be turned back into something v2 understands. If the bridge is
    unreachable, or somebody has renamed the light since, the setting is left
    empty and the user is told what to pick - a failed lookup must not fail the
    migration, which is mostly about the password.
    """
    number = migration.pending_light
    try:
        name, choices = lookup(str(hue.get("address", "")), str(hue.get("key", "")), number)
    except Exception as error:  # noqa: BLE001 - a bridge on a shelf is not an error here
        log.info("could not reach the bridge to match Hue light %s: %s", number, error)
        migration.notes.append(
            f"Hue light {number} could not be matched - the bridge did not answer. "
            "Pick the light in Settings; your key still works, so there is no button to press."
        )
        return

    for light_id, light_name in choices.items():
        if light_name.strip().casefold() == (name or "").strip().casefold():
            hue["light"] = light_id
            migration.notes.append(f"Hue light {number} matched to '{light_name}'.")
            return

    migration.notes.append(
        f"Hue light {number} was '{name}' in the prototype, and no light on the bridge "
        "has that name now. Pick it again in Settings."
    )


def _bridge_lookup(address: str, key: str, number: str) -> tuple[str, dict[str, str]]:
    """Ask the bridge for a v1 light's name, and for every v2 light's name.

    The only place in Pastie that speaks v1, and it exists purely to close the
    gap between the two APIs during an upgrade.
    """
    import urllib.request

    from pastie.messengers.hue import Bridge

    url = f"http://{address}/api/{key}/lights/{number}"
    with urllib.request.urlopen(url, timeout=10) as response:
        name = str(json.load(response).get("name", ""))

    lights = Bridge(address, key).lights()
    return name, {
        str(light.get("id", "")): str(light.get("metadata", {}).get("name", "")) for light in lights
    }


def _brightness_to_v2(value: Any) -> float:
    """Convert a v1 brightness to the v2 one.

    The two APIs use different scales for the same idea: v1 `bri` is 1-254, v2
    `dimming.brightness` is a percentage. Carrying the number across unchanged
    sends 254 to a field whose maximum is 100 - which the bridge either clamps
    or rejects, and either way the first real alert behaves oddly for a reason
    nobody would think to look for.

    Anything already inside 0-100 is left alone, so migrating twice is safe.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 100.0
    if number <= 100:
        return max(1.0, number)
    return round(min(100.0, number / 254 * 100), 1)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        log.warning("could not read %s: %s", path, error)
        return {}
    return parsed if isinstance(parsed, dict) else {}
