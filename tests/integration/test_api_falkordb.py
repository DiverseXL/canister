"""API integration tests against a real FalkorDB (marker: falkordb)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from canister_api.main import app
from canister_evaluation import build_fts_documents, build_ingest_documents
from canister_graph import GraphWriter, select_graph
from canister_retrieval import FtsStore
from fastapi.testclient import TestClient

pytestmark = pytest.mark.falkordb

client = TestClient(app)


@pytest.fixture
def api_env(db, corpus_dir: Path, gold: dict, tmp_path, monkeypatch):
    tenant = "canister_api_" + uuid.uuid4().hex[:8]
    writer = GraphWriter(select_graph(tenant, db=db))
    writer.ensure_schema()
    writer.ingest(build_ingest_documents(corpus_dir, gold))
    writer.canonize_all()

    index_path = tmp_path / "index.sqlite3"
    store = FtsStore(index_path)
    store.reset()
    store.add_documents(build_fts_documents(corpus_dir, gold))

    monkeypatch.setenv("CANISTER_DEFAULT_TENANT", tenant)
    monkeypatch.setenv("CANISTER_INDEX_PATH", str(index_path))
    monkeypatch.setenv("CANISTER_RECEIPTS_DIR", str(tmp_path / "receipts"))
    yield tenant, gold
    db.select_graph(tenant).delete()


def test_ground_then_replay_grounding_record(api_env) -> None:
    tenant, gold = api_env
    question = next(q for q in gold["questions"] if q["kind"] == "answerable")
    response = client.post("/ground", json={"question": question["question"], "mode": "current"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["sha256"]) == 64
    assert body["final_size"] == 10
    assert set(body["cypher_queries"]) == {
        "READ_KEY_INFO",
        "READ_STATE",
        "READ_DOC_VALUES",
        "READ_WALKED_PATH",
    }
    assert body["mode_requested"] == "current"

    replay = client.get(f"/grounding/{body['receipt_id']}")
    assert replay.status_code == 200
    assert replay.json()["sha256"] == body["sha256"]


def test_ground_historical_recovers_retired_evidence(api_env) -> None:
    tenant, gold = api_env
    conflict = next(q for q in gold["questions"] if q["kind"] == "answerable")
    response = client.post("/ground", json={"question": conflict["question"], "mode": "historical"})
    assert response.status_code == 200
    body = response.json()
    assert any(entry["label"] == "superseded" for entry in body["final_context"])
    assert all(entry["reason"] != "superseded" for entry in body["cut_set"])


def test_claims_lists_state(api_env) -> None:
    tenant, _ = api_env
    response = client.get("/claims", params={"tenant_id": tenant})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 40
    assert len(body["sha256"]) == 64
    assert set(body["cypher_queries"]) == {"READ_KEY_INFO", "READ_STATE"}
    assert all("decision" in claim for claim in body["claims"])
