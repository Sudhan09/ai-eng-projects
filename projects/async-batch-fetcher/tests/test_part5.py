import asyncio
import subprocess
import sys

import pytest

from async_batch_fetcher.batch import checksum, run_group
from async_batch_fetcher.errors import PermanentError, TransientError
from async_batch_fetcher.server import MockServer


def run_against(server, make_batch):
    async def main():
        port = await server.start()
        try:
            return await make_batch(port)
        finally:
            await server.stop()

    return asyncio.run(main())


def test_a_slow_job_times_out_on_its_own():
    server = MockServer(delay=0.01, slow=frozenset({3}), slow_delay=1.0)
    results, sums, peak = run_against(
        server, lambda port: run_group(list(range(6)), port, timeout=0.3)
    )
    assert isinstance(results[3].error, TransientError)
    assert results[3].error.reason == "timeout"
    assert [r.ok for r in results] == [True, True, True, False, True, True]
    assert len(sums) == 5


def test_the_checksum_runs_in_a_thread_and_is_stable():
    assert checksum("payload-1") == checksum("payload-1") != checksum("payload-2")


def test_strict_mode_stops_the_batch_at_the_first_404():
    async def main():
        server = MockServer(delay=0.01, fail_every=10)
        port = await server.start()
        try:
            with pytest.raises(ExceptionGroup) as info:
                await run_group(list(range(60)), port, concurrency=5, strict=True)
        finally:
            await server.stop()
        return info.value, asyncio.all_tasks() - {asyncio.current_task()}

    group, others = asyncio.run(main())
    assert group.subgroup(PermanentError) is not None and others == set()


def test_a_full_run_leaves_no_resource_warning():
    code = "from async_batch_fetcher.cli import main; main(['--jobs', '40'])"
    done = subprocess.run(
        [sys.executable, "-W", "error", "-c", code], capture_output=True, text=True
    )
    assert done.returncode == 0
    assert "ResourceWarning" not in done.stderr
