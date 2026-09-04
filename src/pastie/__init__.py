"""Pastie - an appliance companion for Haier hOn appliances.

Pastie is an unofficial community project. It is not affiliated with, endorsed by,
or supported by Haier.

The package is layered, and the layering is load-bearing:

    pastie.connector   the only code that knows Haier's field names
    pastie.core        what state the appliance is in and what just happened
    pastie.messengers  things that react - lights, speakers, webhooks
    pastie.service     the long-running watcher, and its private channel to the app
    pastie.app         the window you look at

`pastie.core` imports nothing from the layers around it and no third-party
client, which is what makes the awkward parts - restarts, duplicate updates,
gaps while Pastie was switched off - testable without an appliance.
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
