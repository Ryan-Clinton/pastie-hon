"""Handing one file to one device, and nothing else to anybody.

A Chromecast or Google Home cannot be handed audio directly - it needs a URL it
can fetch. So an announcement has to be served over HTTP on the local network,
and that is the one place Pastie is allowed to listen for connections.

The prototype got this wrong in a way worth spelling out, because it is the
obvious way to do it: it bound to **every** network interface and served the
**whole** speech cache directory with no authentication. The practical risk was
small - a few seconds of uptime, containing your own "the dryer's finished"
recordings - but it is exactly the shape of thing that is fine until it isn't.

This serves:

* only one file, held in memory, never a directory;
* at an unguessable path, not a predictable filename;
* for seconds, shutting down immediately afterwards;
* with no other endpoints - nothing here controls anything;
* bound as narrowly as the device allows, which for a speaker on the LAN means
  this machine's LAN address rather than everything.
"""

from __future__ import annotations

import http.server
import logging
import secrets
import socket
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType

log = logging.getLogger(__name__)

#: Long enough for a speaker to fetch and play a short announcement.
DEFAULT_TTL = timedelta(seconds=120)


def lan_address() -> str:
    """This machine's address on the LAN - the one a speaker can reach.

    No traffic is sent; connecting a UDP socket only picks the route the
    operating system would use, which is how you find the right interface on a
    machine that has several.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


@dataclass
class _Payload:
    path: str
    body: bytes
    content_type: str
    expires_at: datetime


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves the one payload, and 404s everything else including a bare /."""

    payload: _Payload
    # HTTP/1.1 so a speaker gets a Content-Length it trusts, but every response
    # closes its connection: this server exists for one fetch and then goes
    # away, and a kept-alive socket would outlive it.
    protocol_version = "HTTP/1.1"
    close_connection = True

    def do_GET(self) -> None:  # the name is fixed by the base class
        self._respond(include_body=True)

    def do_HEAD(self) -> None:  # the name is fixed by the base class
        self._respond(include_body=False)

    def _respond(self, *, include_body: bool) -> None:
        payload = self.payload
        expired = datetime.now(UTC) >= payload.expires_at
        # Comparing with `secrets.compare_digest` rather than == so a wrong path
        # cannot be narrowed down by timing. The window is seconds and the
        # payload is a recording of your own tumble dryer, but this is the file
        # everybody copies when they write the next messenger.
        wanted = secrets.compare_digest(self.path, payload.path)
        if expired or not wanted:
            self.send_error(404)
            self.close_connection = True
            return
        self.send_response(200)
        self.send_header("Content-Type", payload.content_type)
        self.send_header("Content-Length", str(len(payload.body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if include_body:
            self.wfile.write(payload.body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        log.debug("fileserve: " + format, *args)


class ServedFile:
    """A single file, served at an unguessable URL, for a few seconds.

    Used as a context manager, so the server cannot outlive the announcement
    even if the announcement fails:

        with ServedFile(mp3_bytes, "audio/mp3") as url:
            speaker.play(url)
    """

    def __init__(
        self,
        body: bytes,
        content_type: str,
        *,
        host: str | None = None,
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        self._payload = _Payload(
            path=f"/{secrets.token_urlsafe(16)}",
            body=body,
            content_type=content_type,
            expires_at=datetime.now(UTC) + ttl,
        )
        self._host = host or lan_address()
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("the file is not being served yet")
        return f"http://{self._host}:{self._server.server_address[1]}{self._payload.path}"

    def __enter__(self) -> str:
        handler = type("_Bound", (_Handler,), {"payload": self._payload})
        # Port 0: the operating system picks a free one, so nothing is predictable
        # and nothing collides with whatever else is running.
        self._server = http.server.ThreadingHTTPServer((self._host, 0), handler)
        self._server.timeout = 5
        self._server.daemon_threads = True
        self._server.block_on_close = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="pastie-fileserve", daemon=True
        )
        self._thread.start()
        return self.url

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
