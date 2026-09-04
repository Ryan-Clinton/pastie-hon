"""The boundary with Haier.

Everything that knows Haier's vocabulary lives in this package, and nothing
outside it may. If `machMode` appears in the interface code, that is a rejected
pull request - not because the name is ugly, but because it is the difference
between a breaking change costing one file and costing the whole codebase.

`profiles` records what the numbers mean, and how sure we are. `reading`
translates. `hon` is the only module that opens a connection.
"""

from pastie.connector.hon import CommandRejectedError, ConnectorError, HonConnector, appliance_key
from pastie.connector.profiles import TUMBLE_DRYER, Profile, for_appliance
from pastie.connector.reading import RawReading, translate

__all__ = [
    "TUMBLE_DRYER",
    "CommandRejectedError",
    "ConnectorError",
    "HonConnector",
    "Profile",
    "RawReading",
    "appliance_key",
    "for_appliance",
    "translate",
]
