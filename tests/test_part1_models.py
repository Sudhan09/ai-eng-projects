def test_a_model_by_id_hides_its_notes_unless_verbose(client):
    assert client.get("/models/tiny-1").json() == {
        "id": "tiny-1",
        "context_tokens": 4096,
        "notes": None,
    }
    verbose = client.get("/models/tiny-1", params={"verbose": "true"})
    assert verbose.json()["notes"] == "fast, for drafts"


def test_an_unknown_model_is_404_and_a_bad_flag_is_422(client):
    assert client.get("/models/tiny-9").status_code == 404
    assert client.get("/models/tiny-1", params={"verbose": "maybe"}).status_code == 422

def test_the_docs_list_the_model_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/models/{model_id}" in paths