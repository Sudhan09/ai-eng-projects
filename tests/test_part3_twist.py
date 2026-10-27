import asyncio
import io

from async_batch_fetcher.batch import run_with_progress
from async_batch_fetcher.server import MockServer


def test_progress_counts_the_failures_so_far():
    async def main(out):
        server = MockServer(delay=0.01, fail_every=10)
        port = await server.start()
        try:
            await run_with_progress(list(range(20)), port, out)
        finally:
            await server.stop()

    out = io.StringIO()
    asyncio.run(main(out))
    counts = [
        int(line.split("(")[1].split()[0]) for line in out.getvalue().splitlines()
    ]
    assert counts[-1] == 2
    assert counts == sorted(counts)
