def test_the_demo_page_is_served_and_kept_out_of_the_schema(client):
    page = client.get("/demo")
    assert page.headers["content-type"].startswith("text/html")
    assert "new EventSource(" in page.text
    assert "/demo" not in client.get("/openapi.json").json()["paths"]
