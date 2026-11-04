def test_an_unknown_model_is_a_model_not_found_envelope(client):
    answer = client.get("/models/tiny-9")
    assert answer.status_code == 404
    error = {
        "code": "model_not_found",
        "message": "No model has that id.",
        "request_id": answer.headers["x-request-id"],
        "details": [],
    }
    assert answer.json() == {"error": error}
