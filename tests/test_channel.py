"""The app's channel to the service, over a real Windows named pipe.

These start an actual `PipeServer` on a pipe of their own and talk to it with a
real `PipeClient`. Nothing is mocked, because the bug worth catching here was
not in the logic - it was in how many clients the pipe would accept at once,
which no amount of mocking would have shown.

Windows only, and skipped everywhere else: the whole point of the thing is that
it is a named pipe rather than a socket.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from pastie.service.channel import PipeClient, PipeServer
from pastie.service.protocol import Dispatcher, Reply, Request

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="named pipes are Windows-only")


def _pipe_exists(name: str, seconds: float = 5.0) -> bool:
    """Wait for the server's first instance to exist.

    The event loop starting is not the same moment as the pipe existing, and a
    client that arrives in between is told - correctly - that there is nothing
    to talk to. Windows lists live pipes as a directory, so this asks rather
    than sleeping and hoping.
    """
    wanted = name.rsplit("\\", 1)[-1]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if any(pipe.name == wanted for pipe in Path(r"\\.\pipe").iterdir()):
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def channel() -> Any:
    """A running server on a pipe nobody else is using, and a client for it."""
    name = rf"\\.\pipe\pastie-test-{uuid.uuid4().hex}"
    dispatcher = Dispatcher()

    async def slow(arguments: dict[str, Any]) -> Reply:
        # Stands in for a Hue bridge or a speaker search: seconds, not
        # milliseconds, and the whole reason concurrency matters here.
        await asyncio.sleep(0.4)
        return Reply.worked(answer="slow", **arguments)

    async def quick(arguments: dict[str, Any]) -> Reply:
        return Reply.worked(answer="quick", **arguments)

    dispatcher.on("slow", slow)
    dispatcher.on("quick", quick)

    stop = asyncio.Event()
    server = PipeServer(dispatcher, name=name)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_until_complete(server.serve(stop))

    thread = threading.Thread(target=run, name="pipe-server", daemon=True)
    thread.start()
    ready.wait(timeout=5)
    assert _pipe_exists(name), "the server never created its first pipe instance"

    try:
        yield PipeClient(name=name, timeout=10.0)
    finally:
        loop.call_soon_threadsafe(stop.set)
        thread.join(timeout=5)
        loop.close()


def ask(client: PipeClient, action: str, **arguments: Any) -> dict[str, Any]:
    reply = Reply.parse(client.ask(Request(action, arguments).to_line()))
    assert reply.ok, reply.error
    return reply.data or {}


def test_a_request_gets_its_reply(channel: PipeClient) -> None:
    assert ask(channel, "quick", tag="one")["answer"] == "quick"


def test_several_requests_at_once_all_get_answered(channel: PipeClient) -> None:
    """The regression: the window asks three things at the same moment.

    With a single pipe instance the first was served and the rest were told the
    service was not running - so a service that was plainly working reported
    itself as down on half the screen.
    """
    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda n: ask(channel, "quick", tag=str(n)), range(6)))

    assert [reply["tag"] for reply in sorted(replies, key=lambda r: r["tag"])] == [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_a_slow_request_does_not_block_a_quick_one(channel: PipeClient) -> None:
    """Finding speakers takes seconds; the status must keep updating meanwhile."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(ask, channel, "slow")
        quick = pool.submit(ask, channel, "quick")

        assert quick.result(timeout=2)["answer"] == "quick"
        assert slow.result(timeout=5)["answer"] == "slow"


def test_an_unknown_action_comes_back_as_an_error_not_a_hang(channel: PipeClient) -> None:
    reply = Reply.parse(channel.ask(Request("nonsense", {}).to_line()))
    assert not reply.ok
    assert "nonsense" in reply.error


def test_the_reply_is_one_line_of_json(channel: PipeClient) -> None:
    raw = channel.ask(Request("quick", {}).to_line())
    assert "\n" not in raw.strip()
    assert json.loads(raw)["ok"] is True


def test_a_client_with_nothing_to_talk_to_says_the_service_is_not_running() -> None:
    from pastie.service.channel import ChannelUnavailableError

    lonely = PipeClient(name=rf"\\.\pipe\pastie-nothing-{uuid.uuid4().hex}", timeout=0.2)

    with pytest.raises(ChannelUnavailableError, match="not running"):
        lonely.ask(Request("quick", {}).to_line())
