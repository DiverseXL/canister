"""API tests. The fail-closed test needs no database, only an unreachable host."""

from __future__ import annotations

from canister_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_reports_graph_state() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "graph_reachable" in body


def test_ground_fails_closed_when_graph_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", "1")
    response = client.post(
        "/ground", json={"question": "What is the starter plan price for Acme Corp?"}
    )
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "TEMPORAL_GRAPH_UNAVAILABLE"


def test_ground_rejects_unknown_mode() -> None:
    response = client.post("/ground", json={"question": "hi", "mode": "nonsense"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "BAD_REQUEST"
