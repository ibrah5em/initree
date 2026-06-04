from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("${app.healthcheck_path}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
