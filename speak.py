#!/usr/bin/env python3
r"""
speak.py - announce a message on a Google Home / Chromecast speaker.

A Chromecast will not accept raw audio - it needs a URL it can fetch. So this
renders the text to MP3, serves it from a short-lived local HTTP server bound
to this machine's LAN address, tells the speaker to play it, waits, and shuts
the server down again.

Settings live in hue_alert.json alongside the light settings:
    speak_enabled   true/false
    speak_device    friendly name of the speaker
    speak_text      what to say
    speak_volume    0.0-1.0, or null to leave the speaker's volume alone
"""
import hashlib
import http.server
import json
import socket
import sys
import socketserver
import tempfile
import threading
import time
from pathlib import Path
from uuid import UUID

import pychromecast
from gtts import gTTS

# Discovery by mDNS is unreliable from a service context, so cached addresses
# are read from cast_hosts.json when present:
#     {"Speaker name": "192.168.1.50"}
# Absent or unmatched, we fall back to a normal network search. Kept out of the
# source so no one's LAN layout ends up in the repository.
def _known_hosts():
    try:
        base = (Path(sys.executable) if getattr(sys, "frozen", False)
                else Path(__file__)).resolve().parent
        f = base / "cast_hosts.json"
        if f.exists():
            raw = json.loads(f.read_text(encoding="utf-8"))
            return {name: (ip, 8009,
                           UUID("00000000-0000-0000-0000-000000000000"),
                           "", name)
                    for name, ip in raw.items()}
    except Exception:                                      # noqa: BLE001
        pass
    return {}


DEFAULTS = {
    "speak_enabled": False,
    "speak_device": "Living Room speaker",
    "speak_text": "Tumble dryer finished. Go empty it.",
    "speak_volume": None,
}


def lan_ip():
    """The address this machine presents on the LAN - the speaker must reach it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))          # no traffic sent, just picks the route
        return s.getsockname()[0]
    finally:
        s.close()


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass                                 # keep the console quiet


def cache_dir():
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    d = base / "tts_cache"
    d.mkdir(exist_ok=True)
    return d


def is_cached(text):
    """True if this exact text has already been rendered."""
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    mp3 = cache_dir() / f"{key}.mp3"
    return mp3.exists() and mp3.stat().st_size > 0


def render(text, log=print):
    """MP3 for this text, rendered once and cached.

    gTTS is a network call to Google and takes ~20s - by far the slowest part
    of an announcement. The message rarely changes, so cache by content hash.
    """
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    mp3 = cache_dir() / f"{key}.mp3"
    if mp3.exists() and mp3.stat().st_size > 0:
        log("speak: using cached audio")
        return mp3
    log(f"speak: rendering \"{text}\" (first time, ~20s)")
    gTTS(text=text, lang="en", tld="co.uk").save(str(mp3))
    return mp3


def prerender(text, log=print):
    """Warm the cache ahead of time so the real alert is instant."""
    try:
        render(text, log=log)
        return True
    except Exception as exc:                               # noqa: BLE001
        log(f"speak: prerender failed - {exc}")
        return False


def announce(text, device_name, volume=None, log=print, timeout=45):
    mp3 = render(text, log=log)
    tmp = mp3.parent

    handler = lambda *a, **k: _Handler(*a, directory=str(tmp), **k)  # noqa: E731
    srv = socketserver.TCPServer(("", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://{lan_ip()}:{port}/{mp3.name}"

    cast, browser = None, None
    try:
        # mDNS discovery often finds nothing when running as a service, so try
        # the known host first and only fall back to a network search.
        host = _known_hosts().get(device_name)
        if host:
            try:
                cast = pychromecast.get_chromecast_from_host(host, timeout=8)
                log(f"speak: connected directly to {device_name} at {host[0]}")
            except Exception as exc:                       # noqa: BLE001
                log(f"speak: direct connect failed ({exc}), searching ...")
                cast = None
        if cast is None:
            casts, browser = pychromecast.get_chromecasts(timeout=10)
            cast = next((c for c in casts
                         if c.cast_info.friendly_name == device_name), None)
            if cast is None:
                names = ", ".join(c.cast_info.friendly_name for c in casts) or "none"
                log(f"speak: '{device_name}' not found (saw: {names})")
                return False

        cast.wait(timeout=15)
        previous = cast.status.volume_level if cast.status else None
        if volume is not None:
            cast.set_volume(float(volume))

        log(f"speak: casting to {device_name}")
        cast.media_controller.play_media(url, "audio/mp3")
        cast.media_controller.block_until_active(timeout=15)

        # Wait for playback to actually finish: first for it to start, then for
        # it to go back to IDLE. The old version compared against the deadline
        # in a way that made it sit out the whole timeout every single time.
        started = time.time()
        while time.time() - started < 8:
            if cast.media_controller.status.player_state == "PLAYING":
                break
            time.sleep(0.2)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cast.media_controller.status.player_state in ("IDLE", "UNKNOWN"):
                break
            time.sleep(0.3)

        if volume is not None and previous is not None:
            cast.set_volume(previous)
        log("speak: done")
        return True

    except Exception as exc:                               # noqa: BLE001
        log(f"speak: failed - {type(exc).__name__}: {exc}")
        return False
    finally:
        try:
            if cast:
                cast.quit_app()                # release the speaker
        except Exception:                                  # noqa: BLE001
            pass
        try:
            if browser:
                browser.stop_discovery()
        except Exception:                                  # noqa: BLE001
            pass
        srv.shutdown()
        srv.server_close()   # cached mp3 is deliberately kept


def list_speakers(timeout=8):
    casts, browser = pychromecast.get_chromecasts(timeout=timeout)
    out = [(c.cast_info.friendly_name, c.cast_info.model_name,
            c.cast_info.cast_type) for c in casts]
    browser.stop_discovery()
    return sorted(out)


if __name__ == "__main__":
    import sys
    msg = sys.argv[1] if len(sys.argv) > 1 else DEFAULTS["speak_text"]
    dev = sys.argv[2] if len(sys.argv) > 2 else DEFAULTS["speak_device"]
    announce(msg, dev)
