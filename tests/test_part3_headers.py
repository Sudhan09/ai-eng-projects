from conftest import HEADERS

PARAMS = {"prompt": "hello", "max_tokens": 3}


def test_the_stream_headers_turn_off_caching_and_proxy_buffering(client):
    answer = client.get("/generate/stream", params=PARAMS, headers=HEADERS)
    assert answer.headers["content-type"].startswith("text/event-stream")
    assert answer.headers["cache-control"] == "no-cache"
    assert answer.headers["x-accel-buffering"] == "no"
