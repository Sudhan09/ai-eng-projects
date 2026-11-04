from conftest import HEADERS


def test_an_overlong_stream_prompt_is_refused_too(client):
    too_long = {"prompt": "x" * 4001}
    assert (
        client.get("/generate/stream", params=too_long, headers=HEADERS).status_code
        == 422
    )


def test_too_many_tokens_on_generate_is_refused(client):
    body = {"prompt": "hi", "max_tokens": 513}
    assert client.post("/generate", json=body, headers=HEADERS).status_code == 422
