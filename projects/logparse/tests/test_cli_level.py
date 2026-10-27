import json

from logparse.cli import main


def test_level_keeps_that_level_and_above(tmp_path, capsys):
    log = tmp_path / "app.log"
    log.write_text(
        "2026-10-02T09:15:01Z INFO auth: login ok\n"
        "2026-10-02T09:15:02Z WARNING cache: slow\n"
        "2026-10-02T09:15:03Z ERROR db: refused\n"
        "2026-10-02T09:15:04Z CRITICAL disk: full\n",
        encoding="utf-8",
    )
    assert main([str(log), "--level", "WARNING", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total"] == 3
    assert report["by_level"] == {"WARNING": 1, "ERROR": 1, "CRITICAL": 1}
