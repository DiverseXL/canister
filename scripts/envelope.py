"""Assemble the measured submission envelope.

Every number here is read back from a script's output or queried from the graph.
Anything missing is recorded as ``not_run``.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from canister_evaluation import gold_index, load_gold
from canister_graph import build_client, select_graph

DEFAULT_CORPUS = Path("corpus/out")


def _falkordb_versions(db) -> dict:
    versions: dict[str, str | None] = {"redis_version": None, "graph_module": None}
    try:
        info = db.connection.info("server")
        versions["redis_version"] = info.get("redis_version")
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        modules = db.connection.execute_command("MODULE", "LIST")
        for module in modules:
            fields = {str(k).lower(): v for k, v in zip(module[0::2], module[1::2], strict=False)}
            if fields.get("name") == "graph":
                versions["graph_module"] = str(fields.get("ver"))
    except Exception:  # pragma: no cover - defensive
        pass
    return versions


def _graph_metrics(tenant: str) -> dict:
    db = build_client()
    graph = select_graph(tenant, db=db)
    queries = {
        "nodes": "MATCH (n) RETURN count(n)",
        "relationships": "MATCH ()-[r]->() RETURN count(r)",
        "artifacts": "MATCH (a:Artifact) RETURN count(a)",
        "assertions": "MATCH (a:Assertion) RETURN count(a)",
        "canon_events": "MATCH (ce:CanonEvent) RETURN count(ce)",
        "supersedes_edges": "MATCH (:CanonEvent)-[r:SUPERSEDES]->(:CanonEvent) RETURN count(r)",
        "canon": "MATCH (ce:CanonEvent {current:true}) WHERE ce.decision='CANON' RETURN count(ce)",
        "contested": (
            "MATCH (ce:CanonEvent {current:true}) WHERE ce.decision='CONTESTED' RETURN count(ce)"
        ),
        "unknown": (
            "MATCH (ce:CanonEvent {current:true}) WHERE ce.decision='UNKNOWN' RETURN count(ce)"
        ),
    }
    metrics = {}
    for name, query in queries.items():
        metrics[name] = int(graph.query(query).result_set[0][0])
    metrics["versions"] = _falkordb_versions(db)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the submission envelope.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--tenant", default="demo")
    parser.add_argument("--out", type=Path, default=Path("evidence/envelope.json"))
    args = parser.parse_args()

    gold = load_gold(args.corpus)
    index = gold_index(gold)

    envelope: dict = {
        "project": "Canister",
        "track": "Company Brain (Track 3)",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "corpus": {
            **gold["counts"],
            "seed": gold["seed"],
            "answerable_claim_keys": len(index["claims"]),
        },
        "graph": _graph_metrics(args.tenant),
        "measured_by": {
            "corpus": "corpus/generator.py",
            "benchmark": "scripts/benchmark.py",
            "verify": "scripts/verify.py",
            "envelope": "scripts/envelope.py",
        },
    }

    benchmark_path = Path("evidence/benchmark.json")
    if benchmark_path.exists():
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        envelope["benchmark"] = {
            "arms": {mode: arm["metrics"] for mode, arm in benchmark["arms"].items()}
        }
    else:
        envelope["benchmark"] = "not_run"

    verify_path = Path("evidence/verify.json")
    if verify_path.exists():
        verify = json.loads(verify_path.read_text(encoding="utf-8"))
        envelope["verify"] = {
            "passed": verify["passed"],
            "failed": verify["failed"],
            "not_run": verify["not_run"],
            "checks": [
                {"name": check["name"], "status": check["status"]} for check in verify["checks"]
            ],
        }
    else:
        envelope["verify"] = "not_run"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(envelope, indent=2, sort_keys=True))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
