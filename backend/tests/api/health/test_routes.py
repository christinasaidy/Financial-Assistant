from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.app import create_app


def test_health_returns_ok():
    # /health uses no collaborators, so a stand-in container is enough.
    client = TestClient(create_app(Mock()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
