"""Saying it out loud on a Google Home or Chromecast.

Two things about this path are fragile, and both are worth knowing before
relying on it:

* **The speech library is unofficial.** gTTS drives an undocumented Google
  Translate endpoint, and its own project says it can break without warning. So
  a failed announcement is contained here and never stops the light flashing.
* **Finding Cast devices depends on multicast**, which needs the speaker on the
  same subnet and frequently finds nothing at all when the calling program runs
  as a Windows service. The prototype worked around that by connecting straight
  to a known address, and that workaround stays - it is the difference between
  working and not working in the configuration this is meant to run in.

Rendering is the slow part: about twenty seconds for a sentence, which is most
of the delay in an announcement. The audio is cached by the hash of its text, so
it is paid once, and the cache is warmed when the message is edited rather than
when the dryer finishes.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from pastie.core.events import Event
from pastie.messengers.base import Kind, Result, Setting, Target, sample_event
from pastie.messengers.fileserve import ServedFile
from pastie.messengers.flash import TargetLocks

log = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 8
_PLAY_TIMEOUT = 45


class SpeechError(RuntimeError):
    pass


class SpeechCache:
    """Rendered sentences, keyed by what they say.

    The message changes rarely and the render is the expensive part, so the same
    words are never paid for twice.
    """

    def __init__(self, directory: Path, renderer: Callable[[str], bytes] | None = None) -> None:
        self._directory = directory
        self._render = renderer or _render_with_gtts

    def _path(self, text: str) -> Path:
        key = hashlib.sha256(text.encode()).hexdigest()[:16]
        return self._directory / f"{key}.mp3"

    def cached(self, text: str) -> bool:
        path = self._path(text)
        return path.exists() and path.stat().st_size > 0

    def audio(self, text: str) -> bytes:
        path = self._path(text)
        if self.cached(text):
            return path.read_bytes()
        log.info("rendering speech (about 20 seconds, once per phrase)")
        audio = self._render(text)
        if not audio:
            raise SpeechError("the speech service returned nothing")
        self._directory.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return audio


def _render_with_gtts(text: str) -> bytes:
    from io import BytesIO

    from gtts import gTTS

    buffer = BytesIO()
    gTTS(text=text, lang="en", tld="co.uk").write_to_fp(buffer)
    return buffer.getvalue()


class CastMessenger:
    """Announces an event on a named speaker."""

    name = "cast"
    label = "Google Home / Chromecast"

    def __init__(
        self,
        cache: SpeechCache,
        *,
        connect: Callable[[str, str | None], Any] | None = None,
    ) -> None:
        self._cache = cache
        self._connect = connect or _connect_to_speaker
        self._locks = TargetLocks()

    def settings(self) -> Iterable[Setting]:
        return (
            Setting("enabled", "Say it on a speaker", Kind.BOOL, default=False),
            Setting("device", "Speaker", Kind.TARGET),
            Setting(
                "address",
                "Speaker address",
                Kind.TEXT,
                help=(
                    "Optional, and worth filling in: finding speakers by name needs "
                    "multicast, which often fails from a Windows service"
                ),
            ),
            Setting("text", "What to say", Kind.TEXT, default="The tumble dryer has finished."),
            Setting(
                "volume",
                "Volume",
                Kind.NUMBER,
                default=None,
                help="Left alone if empty - the speaker keeps whatever it was set to",
            ),
        )

    async def discover(self, config: Mapping[str, Any]) -> list[Target]:  # noqa: ARG002
        return await asyncio.to_thread(_discover_speakers)

    async def test(self, config: Mapping[str, Any]) -> Result:
        return await self.react(sample_event(str(config.get("text") or "Pastie test.")), config)

    async def react(self, event: Event, config: Mapping[str, Any]) -> Result:
        device = str(config.get("device", ""))
        if not device:
            return Result.failed("no speaker chosen")
        # The configured sentence wins over the event's own wording: people
        # choose what their house says. An event with no configured text - a
        # fault, most likely - falls back to the event's own message.
        text = str(config.get("text") or event.message)

        async with self._locks.for_target(device):
            try:
                return await asyncio.to_thread(self._announce, device, text, config)
            except SpeechError as error:
                return Result.failed(str(error))

    def _announce(self, device: str, text: str, config: Mapping[str, Any]) -> Result:
        audio = self._cache.audio(text)
        speaker = self._connect(device, str(config.get("address") or "") or None)
        if speaker is None:
            raise SpeechError(f"could not reach '{device}'")

        previous = None
        with ServedFile(audio, "audio/mp3") as url:
            try:
                volume = config.get("volume")
                if volume is not None:
                    previous = getattr(getattr(speaker, "status", None), "volume_level", None)
                    speaker.set_volume(float(volume))

                speaker.media_controller.play_media(url, "audio/mp3")
                speaker.media_controller.block_until_active(timeout=15)
                _wait_for_playback(speaker)
            finally:
                if previous is not None:
                    speaker.set_volume(previous)
                # Release the speaker so whatever was playing before can resume.
                _quietly(speaker.quit_app)
        return Result.worked(f"announced on {device}")

    def warm(self, text: str) -> bool:
        """Render ahead of time, so the real announcement is not the slow one."""
        try:
            self._cache.audio(text)
        except Exception as error:  # noqa: BLE001 - warming is best-effort by design
            log.debug("could not warm the speech cache: %s", error)
            return False
        return True


def _wait_for_playback(speaker: Any) -> None:
    """Wait for it to start, then for it to finish.

    The prototype compared against its deadline in a way that made every
    announcement sit out the whole timeout; this returns as soon as the speaker
    goes back to idle.
    """
    started = time.time()
    while time.time() - started < 8:
        if getattr(speaker.media_controller.status, "player_state", "") == "PLAYING":
            break
        time.sleep(0.2)

    deadline = time.time() + _PLAY_TIMEOUT
    while time.time() < deadline:
        if getattr(speaker.media_controller.status, "player_state", "") in ("IDLE", "UNKNOWN"):
            return
        time.sleep(0.3)


def _connect_to_speaker(name: str, address: str | None) -> Any:
    """Connect directly if we know where it is, and search only if we must."""
    import pychromecast

    if address:
        try:
            speaker = pychromecast.get_chromecast_from_host(
                (address, 8009, uuid.UUID(int=0), "", name), timeout=_CONNECT_TIMEOUT
            )
            speaker.wait(timeout=15)
        except Exception as error:  # noqa: BLE001 - fall back to searching
            log.info("direct connection to %s failed (%s); searching instead", name, error)
        else:
            return speaker

    speakers, browser = pychromecast.get_chromecasts(timeout=10)
    try:
        for speaker in speakers:
            if speaker.cast_info.friendly_name == name:
                speaker.wait(timeout=15)
                return speaker
    finally:
        browser.stop_discovery()
    return None


def _discover_speakers() -> list[Target]:
    import pychromecast

    speakers, browser = pychromecast.get_chromecasts(timeout=8)
    try:
        return sorted(
            (
                Target(
                    id=str(speaker.cast_info.friendly_name),
                    label=str(speaker.cast_info.friendly_name),
                    detail=str(speaker.cast_info.model_name or ""),
                )
                for speaker in speakers
            ),
            key=lambda target: target.label,
        )
    finally:
        browser.stop_discovery()


def _quietly(action: Callable[[], Any]) -> None:
    try:
        action()
    except Exception as error:  # noqa: BLE001 - tidying up must not raise
        log.debug("ignored while tidying up after an announcement: %s", error)
