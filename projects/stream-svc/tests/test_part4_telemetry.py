from conftest import HEADERS


def test_telemetry_is_recorded_after_the_stream_ends(app, client):
    client.get(
        "/generate/stream", params={"prompt": "hi", "max_tokens": 4}, headers=HEADERS
    )
    record = app.state.telemetry[-1]
    assert (record.outcome, record.tokens) == ("done", 4)


def test_the_record_carries_the_streams_request_id(app, client):
    answer = client.get(
        "/generate/stream", params={"prompt": "hi", "max_tokens": 2}, headers=HEADERS
    )
    assert app.state.telemetry[-1].request_id == answer.headers["x-request-id"]
