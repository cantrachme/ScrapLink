
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import settings


client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == f"{settings.APP_NAME} API"
    assert data["environment"] == settings.APP_ENV
    assert data["version"] == "0.1.0"


def test_cors_allowed_origin():
    response = client.options(
        "/health",
        headers={
            "Origin": settings.FRONTEND_URL,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == settings.FRONTEND_URL
    )


def test_cors_disallowed_origin():
    response = client.options(
        "/health",
        headers={
            "Origin": "https://unauthorized.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
