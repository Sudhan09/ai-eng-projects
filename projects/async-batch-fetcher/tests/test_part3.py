import asyncio
import io
from datetime import UTC, datetime

from async_batch_fetcher.batch import run_all, run_with_progress
from async_batch_fetcher.errors import TransientError
from async_batch_fetcher.results import Result, failure_kinds, log_line, partition
from async_batch_fetcher.server import MockServer


def run_against(server, make_batch):
    async def main():
        port = await server.start()
        try:
            return await make_batch(port)
        finally:
            await server.stop()

    return asyncio.run(main())


def test_one_failure_does_not_sink_the_batch():
    results = run_against(
        MockServer(delay=0.01, fail_every=10),
        lambda port: run_all(list(range(20)), port),
    )
    ok, failed = partition(results)
    assert [r.job_id for r in results] == list(range(20))
    assert (len(ok), [r.job_id for r in failed]) == (18, [9, 19])
    assert failure_kinds(results) == {"TransientError": 1, "PermanentError": 1}


def test_progress_comes_in_finishing_order_and_results_in_input_order():
    out = io.StringIO()
    results = run_against(
        MockServer(delay=0.01), lambda port: run_with_progress([3, 1, 2], port, out)
    )
    lines = out.getvalue().splitlines()
    assert [line.split()[1] for line in lines] == ["1/3", "2/3", "3/3"]
    assert sorted(line.split()[3] for line in lines) == ["1", "2", "3"]
    assert [r.job_id for r in results] == [3, 1, 2]


def test_each_result_is_one_logparse_line():
    when = datetime(2026, 10, 2, 9, 15, 3, tzinfo=UTC)
    assert log_line(Result(7, value="payload-7"), when) == (
        "2026-10-02T09:15:03Z INFO fetch: job 7 ok"
    )
    failed = Result(9, error=TransientError(9, "503"))
    assert log_line(failed, when) == (
        "2026-10-02T09:15:03Z ERROR fetch: job 9 failed TransientError 503"
    )
