def test_health_reports_ok_and_the_version(client):
    answer = client.get("/health")
    assert answer.status_code == 200
    assert answer.json()["status"] == "ok"
    assert answer.json()["version"] == "0.1.0"