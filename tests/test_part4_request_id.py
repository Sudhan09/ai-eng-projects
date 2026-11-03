from fastapi.testclient import TestClient

WEB = {"Origin": "http://web.test"}


def test_every_response_carries_its_own_request_id(client):
    ids = {client.get("/health").headers["x-request-id"] for _ in range(3)}
    assert len(ids) == 3
    assert all(len(i) == 32 for i in ids)


def test_a_crash_is_a_generic_500_envelope_with_cors_headers(app):
    @app.get("/crash")
    async def crash():
        raise RuntimeError("cannot open /srv/stream-svc/state.db")

    with TestClient(app) as client:
        answer = client.get("/crash", headers=WEB)
    assert answer.status_code == 500
    assert answer.json()["error"]["code"] == "internal_error"
    assert answer.json()["error"]["request_id"] == answer.headers["x-request-id"]
    assert "/srv" not in answer.text
    assert answer.headers["access-control-allow-origin"] == "http://web.test"


def test_a_crash_logs_its_traceback(app, caplog):
    @app.get("/crash")
    async def crash():
        raise RuntimeError("boom")

    with TestClient(app) as client:
        client.get("/crash")
    crashes = [record for record in caplog.records if record.exc_info]
    assert len(crashes) == 1
    assert crashes[0].exc_info[0] is RuntimeError
