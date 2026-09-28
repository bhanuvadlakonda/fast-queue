from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import api


def test_healthz_without_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(api) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_index_and_enqueue_without_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(api) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Procrastinate" in home.text
        denied = client.post("/jobs/demo", json={"seconds": 1, "message": "x"})
        assert denied.status_code == 503
        ready = client.get("/readyz")
        assert ready.status_code == 503
