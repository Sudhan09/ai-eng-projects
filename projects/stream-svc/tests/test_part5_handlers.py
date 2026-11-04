from conftest import HEADERS


def test_validation_details_never_echo_the_input(client):
    answer = client.post("/generate", json={"prompt": "x" * 4001}, headers=HEADERS)
    assert "xxxx" not in answer.text


def test_an_unknown_path_gets_the_envelope_too(client):
    answer = client.get("/nowhere")
    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "not_found"


def test_a_wrong_method_is_a_method_not_allowed_envelope(client):
    answer = client.delete("/health")
    assert answer.status_code == 405
    assert answer.json()["error"]["code"] == "method_not_allowed"
    assert answer.json()["error"]["request_id"] == answer.headers["x-request-id"]
