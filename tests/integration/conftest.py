"""Integration fixtures: a real FalkorDB and fresh per-test tenant graphs."""

from __future__ import annotations

import uuid

import pytest
from canister_graph.client import GraphUnavailable, build_client, ping


@pytest.fixture(scope="session")
def db():
    try:
        client = build_client()
        ping(client)
    except GraphUnavailable as exc:  # pragma: no cover - depends on environment
        pytest.skip(f"FalkorDB not available: {exc}")
    return client


@pytest.fixture
def graph(db):
    name = "canister_test_" + uuid.uuid4().hex[:8]
    g = db.select_graph(name)
    yield g
    try:
        db.select_graph(name).delete()
    except Exception:  # pragma: no cover - graph may be empty
        pass
