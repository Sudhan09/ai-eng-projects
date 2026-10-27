import json

from logparse.config import ParserConfig
from logparse.pipeline import run


def test_sidecar_adds_source(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("2026-10-02T09:15:04Z ERROR db: refused\n", encoding="utf-8")
    meta = tmp_path / "app.log.meta.json"
    meta.write_text(json.dumps({"source": "server-1"}), encoding="utf-8")
    report = run([str(log)], ParserConfig())
    assert report["sources"] == {str(log): "server-1"}


def test_missing_sidecar_leaves_report_unchanged(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("2026-10-02T09:15:04Z ERROR db: refused\n", encoding="utf-8")
    report = run([str(log)], ParserConfig())
    assert "sources" not in report


def test_sidecar_without_source_is_ignored(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("2026-10-02T09:15:04Z ERROR db: refused\n", encoding="utf-8")
    meta = tmp_path / "app.log.meta.json"
    meta.write_text(json.dumps({"host": "server-1"}), encoding="utf-8")
    report = run([str(log)], ParserConfig())
    assert "sources" not in report


def test_broken_sidecar_json_is_ignored(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("2026-10-02T09:15:04Z ERROR db: refused\n", encoding="utf-8")
    meta = tmp_path / "app.log.meta.json"
    meta.write_text("{not json", encoding="utf-8")
    report = run([str(log)], ParserConfig())
    assert "sources" not in report
