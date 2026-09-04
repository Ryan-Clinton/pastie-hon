"""Where the hOn password lives, and why it is not in a file you can read.

The prototype keeps the account password in a plain text file next to the
script. That is the one thing about the prototype that is genuinely wrong, and
it is the first job on the list.

What replaces it:

* The password is encrypted with **DPAPI**, Windows' own facility, under the
  identity of whoever writes it. The service writes it, so the service can read
  it back and nobody else on the machine can - not another account, and not
  somebody who copies the file to a different PC.
* **The app never reads a password and never stores one.** It hands a new one to
  the service over the private channel, and the service is what encrypts it.
  This matters because the service and the logged-in user are different
  accounts: a secret saved under your profile would be unreadable to the service
  that actually needs it.

`PASTIE_ALLOW_PLAIN_SECRETS` exists for development on machines without DPAPI,
and it says so loudly in the file it writes. It is not a supported way to run.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from pastie.core.store import atomic_write_text

log = logging.getLogger(__name__)

WINDOWS = sys.platform == "win32"
_PLAIN_ALLOWED = "PASTIE_ALLOW_PLAIN_SECRETS"

#: Written into a plaintext store so anyone who opens the file knows what it is.
_PLAIN_WARNING = "NOT ENCRYPTED - development only, see pastie.service.secrets"


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str

    def __repr__(self) -> str:
        """Never let a password reach a log through a stack trace or a debug print."""
        return f"Credentials(username={self.username!r}, password='***')"


class SecretsUnavailableError(RuntimeError):
    """No safe place to keep a secret on this machine."""


def _protect(plaintext: str) -> str:
    import win32crypt

    blob = win32crypt.CryptProtectData(plaintext.encode("utf-8"), "Pastie", None, None, None, 0)
    return base64.b64encode(blob).decode("ascii")


def _unprotect(stored: str) -> str:
    import win32crypt

    _, plaintext = win32crypt.CryptUnprotectData(base64.b64decode(stored), None, None, None, 0)
    return str(plaintext.decode("utf-8"))


class SecretStore:
    """The account details, encrypted at rest under the writing account.

    Reading back from a *different* Windows account fails, by design. That is
    not a bug to work around: it is the property that makes the file useless to
    anyone who copies it.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, credentials: Credentials) -> None:
        if WINDOWS:
            document = {
                "username": credentials.username,
                "password": _protect(credentials.password),
                "protection": "dpapi",
            }
        elif os.environ.get(_PLAIN_ALLOWED):
            document = {
                "username": credentials.username,
                "password": credentials.password,
                "protection": _PLAIN_WARNING,
            }
        else:
            raise SecretsUnavailableError(
                "storing a password needs Windows DPAPI; set "
                f"{_PLAIN_ALLOWED}=1 to keep it in plain text for development"
            )
        atomic_write_text(self._path, json.dumps(document, indent=2))
        _restrict(self._path)

    def load(self) -> Credentials | None:
        if not self._path.exists():
            return None
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SecretsUnavailableError(
                f"the saved account could not be read: {error}"
            ) from error

        username = str(document.get("username", ""))
        stored = str(document.get("password", ""))
        if not username or not stored:
            return None
        if document.get("protection") == "dpapi":
            try:
                return Credentials(username, _unprotect(stored))
            except Exception as error:
                raise SecretsUnavailableError(
                    "the saved password could not be decrypted - it was saved by a "
                    "different Windows account, or on a different machine. Enter it again."
                ) from error
        return Credentials(username, stored)

    def forget(self) -> None:
        self._path.unlink(missing_ok=True)


def _restrict(path: Path) -> None:
    """Take the file's permissions down to its owner and administrators.

    Encryption already makes the contents useless to another account. Removing
    the inherited "everyone can read this" from ProgramData means they cannot
    even take a copy to work on later.
    """
    if not WINDOWS:
        path.chmod(0o600)
        return
    import subprocess

    try:
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                "*S-1-5-18:(F)",  # SYSTEM
                "/grant:r",
                "*S-1-5-32-544:(F)",  # Administrators
                "/grant:r",
                f"{os.environ.get('USERNAME', '')}:(F)",
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("could not restrict permissions on the account file: %s", error)
