from logparse.config import ParserConfig
from logparse.pipeline import run

# 30 lines across three minutes, mixed: 09:15, 09:16, 09:17, 09:15, 09:16, ...
LINES = [f"2026-10-02T09:{15 + i % 3}:{i:02d}Z INFO api: call {i}" for i in range(30)]


def report_for(tmp_path, name, lines):
    log = tmp_path / name
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = run([str(log)], ParserConfig())
    return {key: report[key] for key in ("total", "by_level", "per_minute")}


def test_any_line_order_gives_the_same_counts(tmp_path):
    expected = report_for(tmp_path, "sorted.log", sorted(LINES))
    assert report_for(tmp_path, "mixed.log", LINES) == expected
    assert expected["per_minute"] == {
        "2026-10-02T09:15": 10,
        "2026-10-02T09:16": 10,
        "2026-10-02T09:17": 10,
    }
