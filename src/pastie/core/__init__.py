"""The part of Pastie that has no idea Haier exists.

Everything in here is plain Python: no network, no Windows, no third-party
client. That is what makes the awkward cases - restarts, duplicate updates,
readings arriving out of order, a cycle that finished while the PC was off -
testable against recorded sequences instead of against a real appliance.
"""

from pastie.core.events import Event, EventKind
from pastie.core.health import Health, HealthMonitor, HealthReport
from pastie.core.ledger import Ledger
from pastie.core.memory import ApplianceMemory, MemoryStore
from pastie.core.state import ApplianceState, Maintenance, Snapshot, Trust
from pastie.core.tracker import Tracker

__all__ = [
    "ApplianceMemory",
    "ApplianceState",
    "Event",
    "EventKind",
    "Health",
    "HealthMonitor",
    "HealthReport",
    "Ledger",
    "Maintenance",
    "MemoryStore",
    "Snapshot",
    "Tracker",
    "Trust",
]
