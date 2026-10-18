"""Integration tests requiring a running FalkorDB (marker: falkordb)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from canister_evaluation import (
    build_fts_documents,
    build_ingest_documents,
    sha256_text,
)
from canister_graph import (
    ArtifactInput,
    AssertionInput,
    GraphClaimProvider,
    GraphWriter,
    IngestDocument,
    ids,
)
from canister_graph import ground as run_ground
from canister_retrieval import FtsStore

pytestmark = pytest.mark.falkordb


def make_doc(
    doc_id: str,
    entity: str,
    attribute: str,
    label: str,
    value_type: str,
    value_raw: str,
    value_norm: str,
    *,
    stance: str = "assert",
    explicit: bool = False,
    prior: str | None = None,
    date: str = "2025-01-01",
    source: str = "test",
) -> IngestDocument:
    text = f"{entity} {label} {value_raw}"
    artifact = ArtifactInput(
        doc_id=doc_id,
        title=f"{entity} {label}",
        source=source,
        published_at=date,
        content_sha256=sha256_text(text),
        path=f"documents/{doc_id}.md",
    )
    assertion = AssertionInput(
        doc_id=doc_id,
        entity=entity,
        attribute=attribute,
        attribute_label=label,
        value_type=value_type,
        value_raw=value_raw,
        value_norm=value_norm,
        stance=stance,
        explicit_supersession=explicit,
        prior_value=prior,
        span_start=0,
        span_end=len(text),
        quote=text,
        structured=False,
        source=source,
        published_at=date,
    )
    return IngestDocument(artifact=artifact, assertions=(assertion,))


def test_write_read_and_idempotent(graph) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    docs = [
        make_doc(
            f"d{i}", "Acme", "starter_price", "starter plan price", "money", f"$0.0{i}", f"0.0{i}"
        )
        for i in range(1, 6)
    ]
    writer.ingest(docs)
    writer.canonize_all()
    nodes = writer.count_nodes()
    rels = writer.count_relationships()
    assert nodes > 0

    writer.ingest(docs)
    writer.canonize_all()
    assert writer.count_nodes() == nodes, "re-ingest must create 0 new nodes"
    assert writer.count_relationships() == rels, "re-ingest must create 0 new relationships"

    result = graph.query("MATCH (a:Artifact) RETURN count(a)")
    assert result.result_set[0][0] == 5


def test_supersession_chain_and_residue(graph) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    ckid = ids.claim_key_id("Acme", "starter_price")

    writer.ingest(
        [
            make_doc(
                "d-old",
                "Acme",
                "starter_price",
                "starter plan price",
                "money",
                "$0.08",
                "0.08",
                date="2025-01-01",
            )
        ]
    )
    writer.canonize_all()
    first = graph.query(
        "MATCH (ce:CanonEvent {claim_key_id:$ck}) RETURN ce.id, ce.selected_value, ce.current",
        {"ck": ckid},
    ).result_set
    assert len(first) == 1
    assert first[0][1] == "0.08"
    assert first[0][2] is True

    writer.ingest(
        [
            make_doc(
                "d-new",
                "Acme",
                "starter_price",
                "starter plan price",
                "money",
                "$0.06",
                "0.06",
                stance="supersede",
                explicit=True,
                prior="0.08",
                date="2025-06-01",
            )
        ]
    )
    writer.canonize_all()

    current = graph.query(
        "MATCH (ce:CanonEvent {claim_key_id:$ck}) WHERE ce.current=true RETURN ce.selected_value",
        {"ck": ckid},
    ).result_set
    assert len(current) == 1
    assert current[0][0] == "0.06"

    chain = graph.query(
        "MATCH (a:CanonEvent)-[:SUPERSEDES]->(b:CanonEvent) "
        "WHERE a.claim_key_id=$ck RETURN a.selected_value, b.selected_value",
        {"ck": ckid},
    ).result_set
    assert len(chain) == 1
    assert chain[0] == ["0.06", "0.08"]

    events = graph.query(
        "MATCH (ce:CanonEvent {claim_key_id:$ck}) RETURN ce.id", {"ck": ckid}
    ).result_set
    assert len(events) == 2, "history must be preserved, not overwritten"


def test_majority_adversarial_on_graph(graph) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    docs = [
        make_doc(
            f"old{i}",
            "Globex",
            "starter_price",
            "starter plan price",
            "money",
            "$0.15",
            "0.15",
            date=f"2025-01-{i + 1:02d}",
        )
        for i in range(9)
    ]
    docs.append(
        make_doc(
            "new",
            "Globex",
            "starter_price",
            "starter plan price",
            "money",
            "$0.07",
            "0.07",
            stance="supersede",
            explicit=True,
            prior="0.15",
            date="2025-06-01",
        )
    )
    writer.ingest(docs)
    decisions = writer.canonize_all()
    majority = [d for d in decisions if d.claim_key == ids.claim_key_id("Globex", "starter_price")]
    assert len(majority) == 1
    assert majority[0].selected_value == "0.07"
    assert majority[0].priority == 1
    assert len(majority[0].superseded_assertion_ids) == 9


def test_contested_on_graph(graph) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    docs = [
        make_doc(
            "c1",
            "Initech",
            "refund_window",
            "refund window",
            "duration_days",
            "30 days",
            "30d",
            date="2025-03-01",
        ),
        make_doc(
            "c2",
            "Initech",
            "refund_window",
            "refund window",
            "duration_days",
            "14 days",
            "14d",
            date="2025-03-01",
        ),
    ]
    writer.ingest(docs)
    decisions = writer.canonize_all()
    contested = [
        d for d in decisions if d.claim_key == ids.claim_key_id("Initech", "refund_window")
    ]
    assert contested[0].decision == "CONTESTED"
    assert contested[0].selected_value is None


def test_unknown_on_graph(graph) -> None:
    GraphWriter(graph).ensure_schema()
    provider = GraphClaimProvider(graph)
    assert (
        provider.relevant_claim_keys("What is the current starter plan price for Nonexistent Co?")
        == []
    )
    state = provider.claim_state(ids.claim_key_id("Nonexistent Co", "starter_price"))
    assert state.decision == "UNKNOWN"


def test_full_corpus_round_trip(graph, corpus_dir: Path, gold: dict) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    documents = build_ingest_documents(corpus_dir, gold)

    writer.ingest(documents)
    decisions = writer.canonize_all()
    nodes = writer.count_nodes()

    assert len(decisions) == 40
    assert sum(1 for d in decisions if d.decision == "CONTESTED") == 2

    writer.ingest(documents)
    writer.canonize_all()
    assert writer.count_nodes() == nodes

    provider = GraphClaimProvider(graph)
    question = next(q for q in gold["questions"] if q["kind"] == "answerable")
    keys = provider.relevant_claim_keys(question["question"])
    assert keys, "the question's claim key must be discoverable in the graph"
    assert provider.claim_state(keys[0]).selected_value == question["expected"]


def test_ground_end_to_end(graph, corpus_dir: Path, gold: dict, tmp_path: Path) -> None:
    writer = GraphWriter(graph)
    writer.ensure_schema()
    writer.ingest(build_ingest_documents(corpus_dir, gold))
    writer.canonize_all()

    index_path = tmp_path / "index.sqlite3"
    store = FtsStore(index_path)
    store.reset()
    store.add_documents(build_fts_documents(corpus_dir, gold))

    provider = GraphClaimProvider(graph)
    question = next(q for q in gold["questions"] if q["kind"] == "answerable")
    receipt = run_ground(question["question"], "temporal", provider=provider, retrieve=store.bm25)

    assert receipt["final_size"] == 10
    assert all(entry["label"] != "superseded" for entry in receipt["final_context"])
    assert len(receipt["sha256"]) == 64
    decision = receipt["decisions"][receipt["claim_keys"][0]]
    assert decision["selected_value"] == question["expected"]


def test_three_step_supersession_lineage(db) -> None:
    tenant = f"canister_chain_3step_{uuid.uuid4().hex[:8]}"
    graph = db.select_graph(tenant)
    try:
        writer = GraphWriter(graph)
        writer.ensure_schema()
        ckid = ids.claim_key_id("Acme", "starter_price")

        # Step 1: Ingest document with value A ($0.15) and canonize
        writer.ingest(
            [
                make_doc(
                    "d-a",
                    "Acme",
                    "starter_price",
                    "starter plan price",
                    "money",
                    "$0.15",
                    "0.15",
                    date="2025-01-01",
                )
            ]
        )
        writer.canonize_all()

        # Step 2: Ingest document with value B ($0.10) superseding A and canonize
        writer.ingest(
            [
                make_doc(
                    "d-b",
                    "Acme",
                    "starter_price",
                    "starter plan price",
                    "money",
                    "$0.10",
                    "0.10",
                    stance="supersede",
                    explicit=True,
                    prior="0.15",
                    date="2025-03-01",
                )
            ]
        )
        writer.canonize_all()

        # Step 3: Ingest document with value C ($0.05) superseding B and canonize
        writer.ingest(
            [
                make_doc(
                    "d-c",
                    "Acme",
                    "starter_price",
                    "starter plan price",
                    "money",
                    "$0.05",
                    "0.05",
                    stance="supersede",
                    explicit=True,
                    prior="0.10",
                    date="2025-06-01",
                )
            ]
        )
        writer.canonize_all()

        # Verify current CanonEvent selects C ($0.05)
        current = graph.query(
            "MATCH (ce:CanonEvent {claim_key_id:$ck, current:true}) "
            "RETURN ce.id, ce.selected_value",
            {"ck": ckid},
        ).result_set
        assert len(current) == 1
        current_id, current_val = current[0]
        assert current_val == "0.05"

        # Walk the SUPERSEDES lineage from the current head of the chain:
        # (CanonEvent)-[:SUPERSEDES*1..10]->(old)-[:SELECTS]->(p)
        lineage = graph.query(
            "MATCH (ev:CanonEvent {id:$evid})-[:SUPERSEDES*1..10]->"
            "(old:CanonEvent)-[:SELECTS]->(p:Proposition) "
            "RETURN old.selected_value, p.value_norm ORDER BY old.as_of DESC",
            {"evid": current_id},
        ).result_set
        # Should walk to B (0.10) then A (0.15)
        assert len(lineage) == 2
        assert lineage[0] == ["0.10", "0.10"]
        assert lineage[1] == ["0.15", "0.15"]

        # Verify step-by-step pair supersession chain: C -> B -> A
        chain = graph.query(
            "MATCH (a:CanonEvent)-[:SUPERSEDES]->(b:CanonEvent) "
            "WHERE a.claim_key_id=$ck RETURN a.selected_value, b.selected_value "
            "ORDER BY a.as_of DESC",
            {"ck": ckid},
        ).result_set
        assert len(chain) == 2
        assert chain[0] == ["0.05", "0.10"]
        assert chain[1] == ["0.10", "0.15"]
    finally:
        try:
            db.select_graph(tenant).delete()
        except Exception:
            pass


def test_walked_path_has_five_hops(graph) -> None:
    """The walked-path arrows, verified end to end on this test's own tenant.

    Reversed arrows would return zero rows silently, so non-empty plus the
    exact node sequence and hop count is the actual assertion.
    """
    writer = GraphWriter(graph)
    writer.ensure_schema()
    writer.ingest(
        [
            make_doc(
                "walk-old",
                "Acme",
                "starter_price",
                "starter plan price",
                "money",
                "$0.08",
                "0.08",
                date="2025-01-01",
            )
        ]
    )
    writer.canonize_all()
    writer.ingest(
        [
            make_doc(
                "walk-new",
                "Acme",
                "starter_price",
                "starter plan price",
                "money",
                "$0.06",
                "0.06",
                stance="supersede",
                explicit=True,
                prior="0.08",
                date="2025-06-01",
            )
        ]
    )
    writer.canonize_all()

    provider = GraphClaimProvider(graph)
    path = provider.walked_path("walk-old")

    assert path, "reversed arrows would return zero rows; the path must be non-empty"
    assert len(path) - 1 == 5, f"expected exactly 5 hops, got {len(path)} nodes"
    assert [node[0] for node in path] == [
        "Artifact",
        "Assertion",
        "Proposition",
        "ClaimKey",
        "Proposition",
        "CanonEvent",
    ]
    assert path[2][1] != path[4][1], "retired and selected propositions must differ"
    assert all(node[1] for node in path), "every node needs its stable id"

    # The document asserting the currently selected value has no walked path.
    assert provider.walked_path("walk-new") == []

