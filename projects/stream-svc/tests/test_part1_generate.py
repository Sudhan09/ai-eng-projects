from conftest import HEADERS


def test_generate_returns_the_text_and_its_token_count(client):
    answer = client.post("/generate", json={"prompt": "hello", "max_tokens": 5}, headers=HEADERS)
    assert answer.status_code == 200
    assert answer.json() == {"text": "soon one by waiting of", "tokens": 5}


def test_generate_keeps_the_fields_clients_rely_on(client):
    published = client.get("/openapi.json").json()["components"]["schemas"]["GenerateResponse"]
    answer = client.post("/generate", json={"prompt": "hi", "max_tokens": 2}, headers=HEADERS)
    assert set(published["properties"]) == {"text", "tokens"}  # the contract, pinned
    assert set(answer.json()) == {"text", "tokens"}  # and what really arrives

def test_bad_bodies_are_422(client):
    zero = client.post("/generate", json={"prompt": "hello", "max_tokens": 0}, headers=HEADERS)
    extra = client.post("/generate", json={"prompt": "hi", "temperature": 0.5}, headers=HEADERS)
    assert zero.status_code == 422
    assert extra.status_code == 422