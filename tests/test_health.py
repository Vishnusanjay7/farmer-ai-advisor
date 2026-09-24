from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify that GET /api/v1/health returns status ok and correct service metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "farmer-ai-backend"
    assert data["version"] == "0.1.0"


def test_root_endpoint():
    """Verify root endpoint returns service name and health check link."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert data["health_check"] == "/api/v1/health"
