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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pastie.service.config import SettingsStore
from pastie.service.secrets import Credentials, SecretStore

log = logging.getLogger(__name__)


@dataclass
class Migration:
    """What was found, and what was done with it."""

    account: str = ""
    messengers: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

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
            # v1 numbered its lights; v2 uses an id string. The number is kept so
            # the settings screen can show what was chosen, and the user picks the
            # matching light from a list that now has names on it.
            hue["light"] = ""
            migration.notes.append(
                f"Hue light {alert['light']} was chosen in the prototype. The current "
                "API identifies lights differently, so pick it again from the list - "
                "your bridge key still works, so there is no button to press."
            )
        for key in ("colour", "brightness", "seconds"):
            if alert.get(key) is not None:
                hue[key] = alert[key]
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
    folder: Path, secrets: SecretStore, settings: SettingsStore, migration: Migration | None = None
) -> Migration:
    """Carry out a plan. The prototype's own files are not touched."""
    migration = migration or plan(folder)
    credentials = read_credentials_file(folder / ".credentials")

    if migration.account and credentials.get("password"):
        secrets.save(Credentials(migration.account, credentials["password"]))

    for name, values in migration.messengers.items():
        settings.update_messenger(name, values)
    return migration


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        log.warning("could not read %s: %s", path, error)
        return {}
    return parsed if isinstance(parsed, dict) else {}
