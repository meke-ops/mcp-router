def test_health_endpoint(client):
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "mcp-router"


def test_ready_endpoint(client):
    response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert len(response.json()["dependencies"]) == 2
