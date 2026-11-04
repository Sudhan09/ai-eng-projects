from conftest import HEADERS

BODY = {"prompt": "hello", "max_tokens": 16}


def test_health_shows_the_shared_clients_counters(client):
    client.post("/generate", json=BODY, headers=HEADERS)  # 16 tokens: two pages of 8
    upstream = client.get("/health").json()["upstream"]
    assert upstream == {"breaker_state": "CLOSED", "attempts": 2, "retries": 0}
