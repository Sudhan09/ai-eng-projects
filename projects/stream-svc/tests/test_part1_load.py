import asyncio

from stream_svc.lab import lab_app, load
from stream_svc.serving import running


def test_load_times_every_request():
    with running(lab_app(delay=0.0)) as url:
        seconds = asyncio.run(load(url, "/slow_async", requests=20, concurrency=5))
    assert len(seconds) == 20
    assert all(s > 0 for s in seconds)
