"""The window you look at.

It has no connection to Haier of its own and no password of its own. It asks the
service over the private channel and draws the answer, which is what keeps a
single connection to Haier's servers and stops the window and the service
disagreeing about what the appliance is doing.

`client` is the whole conversation with no window attached, so the app's
behaviour can be tested against the real service handlers without a screen.
"""

from pastie.app.client import MessengerDescription, ServiceClient, ServiceUnavailableError

__all__ = ["MessengerDescription", "ServiceClient", "ServiceUnavailableError"]
