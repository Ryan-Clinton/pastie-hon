"""Settings shared by the whole test run.

Pastie is a Windows program, and its tests run on Linux anyway - that is the
point of the Linux leg of the CI matrix. It exists to prove `pastie.core` stays
free of Windows, and it only proves that if the suite actually runs there.
"""

from __future__ import annotations

import os
import sys

import pytest


@pytest.fixture(autouse=True, scope="session")
def _allow_plain_secrets() -> None:
    """Let the secret store use its development path when DPAPI is absent.

    `SecretStore.save` encrypts with DPAPI and refuses to write a password any
    other way unless this is set - which is correct for a user's machine, and
    would otherwise make every test that saves an account fail everywhere except
    Windows.

    Setting it here changes nothing on Windows: `save` checks the platform
    first, so the encrypted path is still the one being tested there. On Linux
    it selects the plaintext development path, which is a real supported mode
    and says so in the file it writes.
    """
    if sys.platform != "win32":
        os.environ.setdefault("PASTIE_ALLOW_PLAIN_SECRETS", "1")
