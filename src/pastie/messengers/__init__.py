"""Things that react when something happens.

Adding one is the contribution most people will want to make, and it is meant to
be small: write a file, put it in this folder, add it to `build_registry` below,
send a pull request. You do not write any interface code - a messenger describes
its settings and the settings screen draws itself.

Genuinely useful ones nobody has written yet: LIFX, WiZ and Nanoleaf lights (all
talk directly over your network, no accounts needed), phone notifications
through ntfy or Telegram, and a plain Windows desktop notification.

The rules every messenger follows are in `base`, and they are enforced there
rather than left to each author: isolation and timeouts, one alert at a time per
target, a central cap on flash rate, and never logging a secret.
"""

from pastie.messengers.base import (
    Delivery,
    Kind,
    Messenger,
    MessengerRunner,
    Registry,
    Result,
    Setting,
    Target,
    redact,
    sample_event,
)
from pastie.messengers.cast import CastMessenger, SpeechCache
from pastie.messengers.fileserve import ServedFile
from pastie.messengers.hue import HueMessenger
from pastie.messengers.webhook import WebhookMessenger

__all__ = [
    "CastMessenger",
    "Delivery",
    "HueMessenger",
    "Kind",
    "Messenger",
    "MessengerRunner",
    "Registry",
    "Result",
    "ServedFile",
    "Setting",
    "SpeechCache",
    "Target",
    "WebhookMessenger",
    "build_registry",
    "redact",
    "sample_event",
]


def build_registry(speech_cache: SpeechCache) -> Registry:
    """Every messenger this build knows about.

    A new one is added here and nowhere else. Registration is explicit rather
    than a scan of the folder, because the packaged .exe has to be able to see
    what it contains at build time.
    """
    registry = Registry()
    registry.add(HueMessenger())
    registry.add(CastMessenger(speech_cache))
    registry.add(WebhookMessenger())
    return registry
