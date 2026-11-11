from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_returns_200():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert {p["name"] for p in body["providers"]} == {"同花顺", "东方财富", "Yahoo", "Stooq"}
