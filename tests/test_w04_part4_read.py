import tempfile
from pathlib import Path

from aiofetch.storage import ReadStats, read_jsonl, write_jsonl


def test_a_hundred_thousand_records_round_trip(tmp_path):
    path = tmp_path / "results.jsonl"
    records = ({"url": f"/items/{n}", "seconds": n / 1000} for n in range(100_000))
    assert write_jsonl(path, records) == 100_000
    stats = ReadStats()
    back = sum(1 for _ in read_jsonl(path, stats))
    assert back == stats.records == 100_000 and stats.malformed == 0


def test_read_jsonl_reads_a_line_only_when_asked(tmp_path):
    path = tmp_path / "results.jsonl"
    write_jsonl(path, [{"n": 1}, {"n": 2}, {"n": 3}])
    stats = ReadStats()
    reader = read_jsonl(path, stats)
    assert stats.records == 0
    assert next(reader) == {"n": 1}
    assert stats.records == 1


def test_malformed_lines_are_skipped_and_counted(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text('{"n": 1}\n{"n": 2\n[1, 2]\n\n{"n": 3}\n')
    stats = ReadStats()
    assert list(read_jsonl(path, stats)) == [{"n": 1}, {"n": 3}]
    assert stats.malformed == 2


# my own: an empty file yields no records and counts nothing
def test_an_empty_file_yields_nothing():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "empty.jsonl"
        path.write_text("")
        stats = ReadStats()
        assert list(read_jsonl(path, stats)) == []
        assert stats == ReadStats(records=0, malformed=0)


# my own, for the flowmap: two rows out and back, with one torn line in between
def test_two_rows_round_trip_past_a_torn_line():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "rows.jsonl"
        write_jsonl(path, [{"url": "/items/7"}, {"url": "/items/8"}])
        with path.open("a") as sink:
            sink.write('{"url": "/items/9", "sec\n')
        stats = ReadStats()
        assert [row["url"] for row in read_jsonl(path, stats)] == ["/items/7", "/items/8"]
        assert stats == ReadStats(records=2, malformed=1)
