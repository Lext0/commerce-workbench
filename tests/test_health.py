def test_health_is_available_without_external_services(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ready"
    assert response.headers["cache-control"] == "no-store"


def test_unknown_api_route_returns_404(client):
    assert client.get("/api/missing").status_code == 404
