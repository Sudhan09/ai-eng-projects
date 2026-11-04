from fastapi.testclient import TestClient

from stream_svc.lab import lab_app


def test_the_twins_all_answer():
    lab = TestClient(lab_app(delay=0.0))
    for path in ("/slow_async", "/slow_sync", "/slow_blocking"):
        assert lab.get(path).json() == {"slept": 0.0}
