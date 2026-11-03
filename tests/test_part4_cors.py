WEB = {"Origin": "http://web.test"}


def test_cors_answers_the_preflight_for_allowed_origins_only(client):
    ask = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-api-key",
    }
    allowed = client.options("/generate", headers={**WEB, **ask})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://web.test"
    other = client.options("/generate", headers={"Origin": "http://other.test", **ask})
    assert "access-control-allow-origin" not in other.headers
