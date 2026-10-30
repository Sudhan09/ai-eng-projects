from conftest import HEADERS, FakeSource
from sse import frames

from stream_svc.deps import get_token_source

PARAMS = {"prompt": "hello", "max_tokens": 3}


def test_each_token_is_a_frame_and_done_comes_once_at_the_end(client):
    got = frames(client.get("/generate/stream", params=PARAMS, headers=HEADERS).text)
    assert [f["event"] for f in got] == ["token", "token", "token", "done"]
    assert [f["data"] for f in got] == [" soon", " one", " by", "[DONE]"]
    assert [f.get("id") for f in got] == ["1", "2", "3", None]


def test_every_frame_ends_with_a_blank_line(client):
    body = client.get("/generate/stream", params=PARAMS, headers=HEADERS).text
    assert body.count("\r\n\r\n") == 4
    assert body.endswith("\r\n\r\n")


def test_an_override_streams_the_fake_tokens(app, client):
    app.dependency_overrides[get_token_source] = lambda: FakeSource([" a", " b"])
    got = frames(client.get("/generate/stream", params=PARAMS, headers=HEADERS).text)
    assert [f["data"] for f in got] == [" a", " b", "[DONE]"]


def test_a_missing_prompt_is_refused_before_streaming(client):
    assert client.get("/generate/stream", headers=HEADERS).status_code == 422


def test_an_empty_source_sends_only_done(app, client):
    app.dependency_overrides[get_token_source] = lambda: FakeSource([])
    got = frames(client.get("/generate/stream", params=PARAMS, headers=HEADERS).text)
    assert got == [{"event": "done", "data": "[DONE]"}]


def test_zero_max_tokens_is_refused_before_any_frame(client):
    answer = client.get("/generate/stream", params={"prompt": "hi", "max_tokens": 0}, headers=HEADERS)
    assert answer.status_code == 422
