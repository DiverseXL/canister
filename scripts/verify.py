"""End-to-end verification suite (`make verify`).

Every check runs against real FalkorDB. Anything that cannot be run (for
example a container restart with no Docker) is recorded as ``not_run`` and never
simulated.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from canister_evaluation import (
    build_fts_documents,
    build_ingest_documents,
    gold_index,
    load_gold,
    score_question,
)
from canister_graph import (
    GraphClaimProvider,
    GraphWriter,
    build_client,
    drop_graph,
    is_local_host,
    require_local_or_allow_remote,
    select_graph,
)
from canister_graph import ground as run_ground
from canister_retrieval import FtsStore

DEFAULT_CORPUS = os.environ.get("CANISTER_CORPUS_DIR", "corpus/out")
CONTAINER = "canister-falkordb"
VERIFY_TENANT = "canister_verify"
RESIDUE_TENANT = "canister_verify_residue"


class CheckFailure(AssertionError):
    pass


def _docs_for_key(gold: dict, entity: str, attribute: str) -> dict[str, list[str]]:
    waves: dict[str, list[str]] = {"superseded": [], "current": []}
    for doc in gold["documents"]:
        for claim in doc["claims"]:
            if claim["entity"] == entity and claim["attribute"] == attribute:
                waves.setdefault(doc["gold_label"], []).append(doc["doc_id"])
    return waves


def _restart_falkordb() -> None:
    try:
        subprocess.run(
            ["docker", "restart", CONTAINER],
            check=True,
            capture_output=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("docker not available") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"docker restart failed: {exc.stderr!r}") from exc

    last: Exception | None = None
    for _ in range(60):
        try:
            db = build_client()
            db.connection.ping()
            return
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise RuntimeError(f"FalkorDB did not come back after restart: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Canister verification suite.")
    parser.add_argument("--corpus", type=Path, default=Path(DEFAULT_CORPUS))
    parser.add_argument("--out", type=Path, default=Path("evidence/verify.json"))
    parser.add_argument("--skip-restart", action="store_true")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow running against a non-local FALKORDB_HOST (dangerous)",
    )
    args = parser.parse_args()

    require_local_or_allow_remote(args.allow_remote, action="run verify")

    gold = load_gold(args.corpus)
    ingest_docs = build_ingest_documents(args.corpus, gold)
    by_id = {doc.artifact.doc_id: doc for doc in ingest_docs}
    index = gold_index(gold)

    db = build_client()
    results: list[dict] = []

    def record(name: str, status: str, detail) -> None:
        results.append({"name": name, "status": status, "detail": detail})
        print(f"[{status.upper():<7}] {name}: {detail}")

    # --- seed the main verification tenant ---------------------------------
    drop_graph(db, VERIFY_TENANT)
    graph = select_graph(VERIFY_TENANT, db=db)
    writer = GraphWriter(graph)
    writer.ensure_schema()
    writer.ingest(ingest_docs)
    writer.canonize_all()
    nodes = writer.count_nodes()

    try:
        artifacts = graph.query("MATCH (a:Artifact) RETURN count(a)").result_set[0][0]
        assertions = graph.query("MATCH (a:Assertion) RETURN count(a)").result_set[0][0]
        assert artifacts == 200 and assertions == 200 and nodes > 0
        record(
            "write_read", "pass", {"artifacts": artifacts, "assertions": assertions, "nodes": nodes}
        )
    except AssertionError as exc:
        record("write_read", "fail", str(exc))

    try:
        writer.ingest(ingest_docs)
        writer.canonize_all()
        assert writer.count_nodes() == nodes
        record("idempotent_reingest", "pass", {"new_nodes": writer.count_nodes() - nodes})
    except AssertionError as exc:
        record("idempotent_reingest", "fail", str(exc))

    provider = GraphClaimProvider(graph)

    # --- canonization checks ------------------------------------------------
    majority = next(k for k in gold["claim_keys"] if k["kind"] == "majority")
    try:
        state = provider.claim_state(_key(majority))
        assert state.selected_value == majority["current_value"], state
        assert state.priority == 1, state
        record(
            "majority_adversarial",
            "pass",
            {"selected": state.selected_value, "priority": state.priority},
        )
    except AssertionError as exc:
        record("majority_adversarial", "fail", str(exc))

    conflict = next(k for k in gold["claim_keys"] if k["kind"] == "conflict")
    try:
        state = provider.claim_state(_key(conflict))
        assert state.decision == "CANON"
        assert state.selected_value == conflict["current_value"], state
        record(
            "supersession", "pass", {"selected": state.selected_value, "old": conflict["old_value"]}
        )
    except AssertionError as exc:
        record("supersession", "fail", str(exc))

    contested = next(k for k in gold["claim_keys"] if k["kind"] == "contested")
    try:
        state = provider.claim_state(_key(contested))
        assert state.decision == "CONTESTED", state
        record("contested", "pass", {"decision": state.decision})
    except AssertionError as exc:
        record("contested", "fail", str(exc))

    try:
        keys = provider.relevant_claim_keys(
            "What is the current starter plan price for Northwind Traders?"
        )
        assert keys == [], keys
        state = provider.claim_state(
            _key({"entity": "Northwind Traders", "attribute": "starter_price"})
        )
        assert state.decision == "UNKNOWN", state
        record("unknown", "pass", {"decision": state.decision})
    except AssertionError as exc:
        record("unknown", "fail", str(exc))

    # --- residue traversal (incremental ingest) ----------------------------
    try:
        drop_graph(db, RESIDUE_TENANT)
        residue_graph = select_graph(RESIDUE_TENANT, db=db)
        residue_writer = GraphWriter(residue_graph)
        residue_writer.ensure_schema()
        waves = _docs_for_key(gold, conflict["entity"], conflict["attribute"])
        residue_writer.ingest([by_id[doc_id] for doc_id in waves["superseded"]])
        residue_writer.canonize_all()
        ckid = _key(conflict)
        first = residue_graph.query(
            "MATCH (ce:CanonEvent {claim_key_id:$ck}) RETURN count(ce)", {"ck": ckid}
        ).result_set[0][0]
        residue_writer.ingest([by_id[doc_id] for doc_id in waves["current"]])
        residue_writer.canonize_all()
        events = residue_graph.query(
            "MATCH (ce:CanonEvent {claim_key_id:$ck}) RETURN count(ce)", {"ck": ckid}
        ).result_set[0][0]
        chain = residue_graph.query(
            "MATCH (a:CanonEvent)-[:SUPERSEDES]->(b:CanonEvent) "
            "WHERE a.claim_key_id=$ck RETURN a.selected_value, b.selected_value",
            {"ck": ckid},
        ).result_set
        assert first == 1 and events == 2, (first, events)
        assert len(chain) == 1 and chain[0][0] == conflict["current_value"], chain
        record(
            "residue_traversal", "pass", {"events": events, "chain": [list(row) for row in chain]}
        )
    except AssertionError as exc:
        record("residue_traversal", "fail", str(exc))

    # --- ground() receipt ---------------------------------------------------
    try:
        index_path = Path("var/verify_index.sqlite3")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        store = FtsStore(index_path)
        store.reset()
        store.add_documents(build_fts_documents(args.corpus, gold))
        question = next(
            q
            for q in gold["questions"]
            if q["kind"] == "answerable"
            and q["entity"] == majority["entity"]
            and q["attribute"] == majority["attribute"]
        )
        receipt = run_ground(
            question["question"], "temporal", provider=provider, retrieve=store.bm25
        )
        row = score_question(receipt, question, index)
        assert receipt["final_size"] == 10, receipt["final_size"]
        assert row["superseded_leak"] == 0, row
        assert len(receipt["sha256"]) == 64
        record(
            "ground_receipt",
            "pass",
            {
                "final_size": receipt["final_size"],
                "pinned": receipt["pinned"],
                "cut_set": len(receipt["cut_set"]),
                "sha256": receipt["sha256"][:16],
            },
        )
    except AssertionError as exc:
        record("ground_receipt", "fail", str(exc))

    # --- persistence across a real restart ---------------------------------
    if args.skip_restart:
        record("restart_persistence", "not_run", "skipped via --skip-restart")
    elif not is_local_host():
        record(
            "restart_persistence",
            "not_run",
            "FALKORDB_HOST is not local; the restart check only drives the local container",
        )
    else:
        try:
            _restart_falkordb()
            fresh = build_client()
            fresh_graph = select_graph(VERIFY_TENANT, db=fresh)
            after = fresh_graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
            assert after == nodes, (after, nodes)
            record("restart_persistence", "pass", {"nodes_before": nodes, "nodes_after": after})
        except RuntimeError as exc:
            record("restart_persistence", "not_run", str(exc))
        except AssertionError as exc:
            record("restart_persistence", "fail", str(exc))

    # --- cleanup ------------------------------------------------------------
    fresh_db = build_client()
    drop_graph(fresh_db, VERIFY_TENANT)
    drop_graph(fresh_db, RESIDUE_TENANT)

    failures = [r for r in results if r["status"] == "fail"]
    not_run = [r for r in results if r["status"] == "not_run"]
    report = {
        "checks": results,
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": len(failures),
        "not_run": len(not_run),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\n{report['passed']} passed, {report['failed']} failed, {report['not_run']} not_run")
    return 1 if failures else 0


def _key(spec: dict) -> str:
    from canister_graph import ids

    return ids.claim_key_id(spec["entity"], spec["attribute"])


if __name__ == "__main__":
    raise SystemExit(main())
