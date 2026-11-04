import asyncio
import time

from conftest import HEADERS

from stream_svc.fakes import FakeProvider
from stream_svc.lab import read_then_leave
from stream_svc.main import create_app
from stream_svc.serving import running
from stream_svc.stream import StreamRecord, frames


def test_a_client_that_leaves_stops_the_stream_within_one_heartbeat(caplog):
    provider = FakeProvider(
        delay=0.01
    )  # the real UpstreamSource asks it for pages of 8
    app = create_app(transport=provider)
    with running(app) as url:
        left = asyncio.run(read_then_leave(url, "hello", 200, 5, headers=HEADERS))
        deadline = time.monotonic() + 15  # one heartbeat
        while not app.state.telemetry:  # written once the stream has ended
            assert time.monotonic() < deadline
            time.sleep(0.01)
        time.sleep(0.3)  # time for 20 more pages, if anything were still fetching
    record = app.state.telemetry[-1]
    assert record.outcome == "disconnected"
    assert record.started + record.seconds - left < 15  # stopped within one heartbeat
    assert provider.calls <= 3  # counted at the source: 3 pages at most, not 25
    assert f"client disconnected after {record.tokens} tokens" in caplog.text


class StillHere:
    async def is_disconnected(self):
        return False


class Words:
    async def stream(self, prompt, max_tokens):
        for i in range(max_tokens):
            yield f" w{i}"


def test_a_stream_closed_from_outside_is_marked_disconnected():
    async def main():
        record = StreamRecord(request_id="abc")
        stream = frames(StillHere(), Words(), "hi", 10, record)
        await stream.__anext__()
        await stream.aclose()  # what the server does when it just stops reading
        return record

    record = asyncio.run(main())
    assert (record.outcome, record.tokens) == ("disconnected", 1)
