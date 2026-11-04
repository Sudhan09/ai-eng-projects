from conftest import HEADERS, KEY
from sse import frames


def test_the_stream_accepts_the_key_from_the_demo_pages_cookie(client):
    client.cookies.set("stream_key", KEY)
    answer = client.get("/generate/stream", params={"prompt": "hi", "max_tokens": 2})
    assert [f["event"] for f in frames(answer.text)] == ["token", "token", "done"]


def test_a_wrong_header_key_is_refused_even_with_the_right_cookie(client):
    client.cookies.set("stream_key", KEY)
    wrong = {"X-API-Key": "test-key-0001"}
    answer = client.post("/generate", json={"prompt": "hi"}, headers=wrong)
    assert answer.status_code == 401
    assert answer.json()["error"]["code"] == "unauthorized"
    assert (
        client.post("/generate", json={"prompt": "hi"}, headers=HEADERS).status_code
        == 200
    )
