from fastapi.testclient import TestClient

from commerce_workbench.app import create_app


def test_health_is_available_without_external_services():
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_unknown_api_route_returns_404():
    with TestClient(create_app()) as client:
        response = client.get("/api/missing")
        assert response.status_code == 404
