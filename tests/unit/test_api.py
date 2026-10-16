"""API tests.

No database is needed: the "graph stopped" path is emulated by pointing the client
at an unreachable port, which must fail closed with 503.
"""

from __future__ import annotations

import pytest
from canister_api import receipts
from canister_api.main import MODE_ALIASES, app
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Never touch a real graph or the real receipts directory."""
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", "1")
    monkeypatch.setenv("CANISTER_RECEIPTS_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("CANISTER_INDEX_PATH", str(tmp_path / "index.sqlite3"))


def test_health_reports_graph_state() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "graph_reachable" in response.json()


@pytest.mark.parametrize("mode", sorted(MODE_ALIASES))
def test_ground_accepts_each_mode(mode: str) -> None:
    response = client.post("/ground", json={"question": "What is the starter price?", "mode": mode})
    # Accepted mode + stopped graph -> 503, never a 400.
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "TEMPORAL_GRAPH_UNAVAILABLE"


def test_ground_rejects_unknown_mode() -> None:
    response = client.post("/ground", json={"question": "hi", "mode": "nonsense"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "BAD_REQUEST"


def test_claims_fail_closed_when_graph_unreachable() -> None:
    response = client.get("/claims", params={"tenant_id": "demo"})
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "TEMPORAL_GRAPH_UNAVAILABLE"


def test_grounding_record_missing_returns_404() -> None:
    response = client.get("/grounding/doesnotexist")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "NOT_FOUND"


def test_grounding_record_alias_served() -> None:
    response = client.get("/receipt/doesnotexist")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "NOT_FOUND"


def test_grounding_record_invalid_id_returns_400() -> None:
    response = client.get("/grounding/..%2fescape")
    assert response.status_code in (400, 404)


def test_receipts_roundtrip() -> None:
    receipts.save("abc123", {"sha256": "deadbeef", "final_size": 10})
    assert receipts.load("abc123") == {"sha256": "deadbeef", "final_size": 10}
    assert receipts.load("missing") is None
    assert not receipts.valid_id("../etc/passwd")
