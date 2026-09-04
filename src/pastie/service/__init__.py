"""The long-running half: one connection to Haier, and a private channel to the app.

The app never talks to Haier. It asks the service, over a Windows named pipe
locked down to named accounts - so there is only ever one connection, the app
and the service cannot disagree about what the appliance is doing, and nothing
listens on a network address that a web page could reach.
"""

from pastie.service.config import Settings, SettingsStore
from pastie.service.protocol import Dispatcher, Reply, Request
from pastie.service.secrets import Credentials, SecretStore, SecretsUnavailableError
from pastie.service.watcher import ApplianceStatus, Status, Watcher

__all__ = [
    "ApplianceStatus",
    "Credentials",
    "Dispatcher",
    "Reply",
    "Request",
    "SecretStore",
    "SecretsUnavailableError",
    "Settings",
    "SettingsStore",
    "Status",
    "Watcher",
]
