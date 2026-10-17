"""Performance probe for a single local FalkorDB node.

Builds a throwaway synthetic graph using the project's own schema labels
(Entity, ClaimKey, Proposition, Assertion, Artifact, CanonEvent) and
relationships, writes it with ``UNWIND`` batches of 500, measures read latency,
then deletes exactly that graph in a ``finally`` block.

Only a graph named ``perf_<8 hex>`` is created and only it is dropped. The
``demo`` and ``bench`` graphs, and any graph whose name starts with
``canister_``, are never read or written. All numbers describe this one local
Docker node, which is shared with other processes, and are indicative only;
nothing here is a claim about any other system.

Run: ``uv run python scripts/perf.py``
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import random
import secrets
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from canister_graph import build_client, drop_graph, list_graphs, select_graph
from canister_graph.schema import ensure_schema

ENTITIES = 200
CLAIM_KEYS = 1800
PROPOSITIONS = 3000
ASSERTIONS = 3000
ARTIFACTS = 1000
CANON_EVENTS = 1000
BATCH = 500
TARGET_EDGES = 30000
FAN_IN = (10, 100, 1000)
CHAIN_LENGTH = 10
CHAINS = 100
WARMUP_RUNS = 20
TIMED_RUNS = 200
SEED = 20261017

FILL = {"HAS_CLAIM": 2000, "HAS_VALUE": 3500, "ASSERTS": 4500, "IN_ARTIFACT": 4500, "SELECTS": 2800}

EDGE_SPECS = {
    "HAS_CLAIM": ("Entity", "ClaimKey"),
    "HAS_VALUE": ("ClaimKey", "Proposition"),
    "ASSERTS": ("Assertion", "Proposition"),
    "IN_ARTIFACT": ("Assertion", "Artifact"),
    "SELECTS": ("CanonEvent", "Proposition"),
    "SUPERSEDES": ("CanonEvent", "CanonEvent"),
}

NODE_QUERIES = {
    "Entity": "UNWIND $rows AS row MERGE (n:Entity {id:row.id}) SET n.name=row.name",
    "ClaimKey": "UNWIND $rows AS row MERGE (n:ClaimKey {id:row.id}) SET n.key=row.key",
    "Proposition": (
        "UNWIND $rows AS row MERGE (n:Proposition {id:row.id}) SET n.value_norm=row.value_norm"
    ),
    "Assertion": (
        "UNWIND $rows AS row MERGE (n:Assertion {id:row.id}) SET n.claim_key_id=row.claim_key_id"
    ),
    "Artifact": "UNWIND $rows AS row MERGE (n:Artifact {id:row.id}) SET n.doc_id=row.doc_id",
    "CanonEvent": (
        "UNWIND $rows AS row MERGE (n:CanonEvent {id:row.id}) SET n.claim_key_id=row.claim_key_id"
    ),
}


def ent(i: int) -> str:
    return f"ent_{i}"


def ck_id(i: int) -> str:
    return f"ck_{i}"


def prop(i: int) -> str:
    return f"prop_{i}"


def asrt(i: int) -> str:
    return f"asrt_{i}"


def art(i: int) -> str:
    return f"art_{i}"


def cev(i: int) -> str:
    return f"cev_{i}"


def unique_name(db) -> str:
    existing = set(list_graphs(db))
    while True:
        name = "perf_" + secrets.token_hex(4)
        if name not in existing:
            return name


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "not_run"


def falkordb_info(db) -> dict:
    modules = db.connection.module_list()
    graph_module = next((m for m in modules if m.get("name") == "graph"), {})
    server = db.connection.info("server")
    return {
        "module_graph_version": graph_module.get("ver"),
        "redis_version": server.get("redis_version"),
        "python_client_version": importlib.metadata.version("falkordb"),
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def node_rows() -> dict[str, list[dict]]:
    return {
        "Entity": [{"id": ent(i), "name": f"Entity {i}"} for i in range(ENTITIES)],
        "ClaimKey": [
            {"id": ck_id(i), "key": f"e{i % ENTITIES}::attr{i % 7}"} for i in range(CLAIM_KEYS)
        ],
        "Proposition": [
            {"id": prop(i), "value_norm": f"value {i}"} for i in range(PROPOSITIONS)
        ],
        "Assertion": [
            {"id": asrt(i), "claim_key_id": ck_id(i % CLAIM_KEYS)} for i in range(ASSERTIONS)
        ],
        "Artifact": [{"id": art(i), "doc_id": f"doc-{i}"} for i in range(ARTIFACTS)],
        "CanonEvent": [
            {"id": cev(i), "claim_key_id": ck_id(i % CLAIM_KEYS)} for i in range(CANON_EVENTS)
        ],
    }


def edge_rows() -> dict[str, list[tuple[str, str]]]:
    edges: dict[str, list[tuple[str, str]]] = {}
    edges["HAS_CLAIM"] = [(ent(i % ENTITIES), ck_id(i)) for i in range(CLAIM_KEYS)]
    edges["HAS_VALUE"] = [(ck_id(j % CLAIM_KEYS), prop(j)) for j in range(PROPOSITIONS)]
    edges["IN_ARTIFACT"] = [(asrt(a), art(a % ARTIFACTS)) for a in range(ASSERTIONS)]
    edges["SELECTS"] = [(cev(c), prop(c % PROPOSITIONS)) for c in range(CANON_EVENTS)]

    asserts: list[tuple[str, str]] = []
    cursor = 0
    for index, target in enumerate(FAN_IN):
        for _ in range(target):
            asserts.append((asrt(cursor), prop(index)))
            cursor += 1
    ordinary = PROPOSITIONS - len(FAN_IN)
    for a in range(cursor, ASSERTIONS):
        asserts.append((asrt(a), prop(len(FAN_IN) + (a - cursor) % ordinary)))
    edges["ASSERTS"] = asserts

    supersedes: list[tuple[str, str]] = []
    for chain in range(CHAINS):
        base = chain * CHAIN_LENGTH
        for step in range(CHAIN_LENGTH - 1):
            supersedes.append((cev(base + step), cev(base + step + 1)))
    edges["SUPERSEDES"] = supersedes

    for i in range(FILL["HAS_CLAIM"]):
        edges["HAS_CLAIM"].append((ent((i * 13 + 5) % ENTITIES), ck_id((i * 7 + 1) % CLAIM_KEYS)))
    for i in range(FILL["HAS_VALUE"]):
        edges["HAS_VALUE"].append(
            (ck_id((i * 5 + 2) % CLAIM_KEYS), prop((i * 3 + 1) % PROPOSITIONS))
        )
    for i in range(FILL["ASSERTS"]):
        edges["ASSERTS"].append(
            (asrt((i * 11 + 3) % ASSERTIONS), prop(len(FAN_IN) + (i * 7) % ordinary))
        )
    for i in range(FILL["IN_ARTIFACT"]):
        edges["IN_ARTIFACT"].append(
            (asrt((i * 5 + 1) % ASSERTIONS), art((i * 17 + 4) % ARTIFACTS))
        )
    for i in range(FILL["SELECTS"]):
        edges["SELECTS"].append(
            (cev((i * 13 + 7) % CANON_EVENTS), prop((i * 19 + 9) % PROPOSITIONS))
        )
    return edges


def write_nodes(graph, rows_by_label: dict[str, list[dict]]) -> None:
    for label, rows in rows_by_label.items():
        query = NODE_QUERIES[label]
        for i in range(0, len(rows), BATCH):
            graph.query(query, {"rows": rows[i : i + BATCH]})


def write_edges(graph, rel: str, head: str, tail: str, pairs: list[tuple[str, str]]) -> None:
    query = (
        f"UNWIND $rows AS row "
        f"MATCH (h:{head} {{id:row.h}}) "
        f"MATCH (t:{tail} {{id:row.t}}) "
        f"CREATE (h)-[:{rel}]->(t)"
    )
    for i in range(0, len(pairs), BATCH):
        chunk = [{"h": h, "t": t} for h, t in pairs[i : i + BATCH]]
        graph.query(query, {"rows": chunk})


def measure(fn: Callable[[], int], warmup: int, runs: int) -> dict:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    rows: list[int] = []
    for _ in range(runs):
        start = time.perf_counter()
        returned = fn()
        samples.append((time.perf_counter() - start) * 1000.0)
        rows.append(returned)
    return {
        "warmup_runs": warmup,
        "timed_runs": runs,
        "p50_ms": round(percentile(samples, 0.50), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
        "rows_returned": {
            "min": min(rows),
            "max": max(rows),
            "mean": round(sum(rows) / len(rows), 3),
        },
    }


def teardown(db, name: str) -> dict:
    start = time.perf_counter()
    dropped = drop_graph(db, name)
    seconds = time.perf_counter() - start
    remaining = sorted(list_graphs(db))
    return {
        "seconds": round(seconds, 6),
        "dropped": dropped,
        "still_listed": name in remaining,
        "confirmed_gone": dropped and name not in remaining,
        "graphs_after": remaining,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="FalkorDB perf probe on a throwaway graph.")
    parser.add_argument("--out", type=Path, default=Path("evidence/perf.json"))
    parser.add_argument("--warmup", type=int, default=WARMUP_RUNS)
    parser.add_argument("--runs", type=int, default=TIMED_RUNS)
    args = parser.parse_args()

    db = build_client()
    graph_name = unique_name(db)

    report: dict = {
        "generated_by": "scripts/perf.py",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "date": datetime.now(UTC).date().isoformat(),
        "graph": {"name": graph_name, "prefix": "perf_"},
        "note": (
            "Single local Docker FalkorDB node shared with other processes (the demo/bench "
            "graphs and other workloads are live). Figures are indicative measurements of "
            "this one local node only; they are not a claim about any other system."
        ),
    }

    graph = None
    result: dict = {}
    try:
        graph = select_graph(graph_name, db=db)
        ensure_schema(graph)

        rows_by_label = node_rows()
        node_count = sum(len(rows) for rows in rows_by_label.values())
        edges = edge_rows()
        edge_count = sum(len(pairs) for pairs in edges.values())

        start = time.perf_counter()
        write_nodes(graph, rows_by_label)
        node_seconds = time.perf_counter() - start

        start = time.perf_counter()
        for rel, (head, tail) in EDGE_SPECS.items():
            write_edges(graph, rel, head, tail, edges[rel])
        edge_seconds = time.perf_counter() - start

        actual_nodes = int(graph.query("MATCH (n) RETURN count(n)").result_set[0][0])
        actual_edges = int(graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0])

        report["environment"] = {
            "falkordb": falkordb_info(db),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "git_commit": git_commit(),
        }
        report["dataset"] = {
            "batch_size": BATCH,
            "chain_length": CHAIN_LENGTH,
            "chains": CHAINS,
            "fan_in": list(FAN_IN),
            "nodes": {"total": node_count, **{k: len(v) for k, v in rows_by_label.items()}},
            "relationships": {"total": edge_count, **{k: len(v) for k, v in edges.items()}},
        }
        report["write_throughput"] = {
            "nodes": {
                "count": node_count,
                "seconds": round(node_seconds, 6),
                "nodes_per_second": round(node_count / node_seconds, 1),
            },
            "relationships": {
                "count": edge_count,
                "seconds": round(edge_seconds, 6),
                "edges_per_second": round(edge_count / edge_seconds, 1),
            },
            "total_seconds": round(node_seconds + edge_seconds, 6),
            "verified": {"nodes": actual_nodes, "relationships": actual_edges},
        }

        rng = random.Random(SEED)
        ordinary = PROPOSITIONS - len(FAN_IN)

        def q_claim() -> int:
            target = ck_id(rng.randrange(CLAIM_KEYS))
            res = graph.query(
                "MATCH (ck:ClaimKey {id:$id})-[:HAS_VALUE]->(p:Proposition) RETURN p.id",
                {"id": target},
            )
            return len(res.result_set)

        def q_lineage() -> int:
            head = cev(rng.randrange(CHAINS) * CHAIN_LENGTH)
            res = graph.query(
                "MATCH (c:CanonEvent {id:$id})-[:SUPERSEDES*1..10]->(x:CanonEvent) RETURN x.id",
                {"id": head},
            )
            return len(res.result_set)

        def q_residue(target: str) -> Callable[[], int]:
            def run() -> int:
                res = graph.query(
                    "MATCH (p:Proposition {id:$id})<-[:ASSERTS]-(a:Assertion)"
                    "-[:IN_ARTIFACT]->(art:Artifact) RETURN a.id, art.id",
                    {"id": target},
                )
                return len(res.result_set)

            return run

        def q_two_hop() -> int:
            target = ent(rng.randrange(ENTITIES))
            res = graph.query(
                "MATCH (e:Entity {id:$id})-[:HAS_CLAIM]->(ck:ClaimKey)"
                "-[:HAS_VALUE]->(p:Proposition) RETURN p.id",
                {"id": target},
            )
            return len(res.result_set)

        report["latency"] = {
            "warmup_runs": args.warmup,
            "timed_runs": args.runs,
            "seed": SEED,
            "claim_neighbourhood": measure(q_claim, args.warmup, args.runs),
            "supersession_lineage": measure(q_lineage, args.warmup, args.runs),
            "reverse_residue": {
                f"fan_in_{n}": measure(q_residue(prop(i)), args.warmup, args.runs)
                for i, n in enumerate(FAN_IN)
            },
            "two_hop_neighbourhood": measure(q_two_hop, args.warmup, args.runs),
            "two_hop_note": "rows returned = Entity -> ClaimKey -> Proposition matches",
            "ordinary_propositions": ordinary,
        }
        result = report
    finally:
        report["teardown"] = teardown(db, graph_name)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    if not result:
        print("perf run failed before completing; graph cleaned up.", flush=True)
        return 1

    write_data = report["write_throughput"]
    latency = report["latency"]
    print(
        f"graph {graph_name}: nodes={write_data['nodes']['count']} "
        f"({write_data['nodes']['nodes_per_second']}/s), "
        f"edges={write_data['relationships']['count']} "
        f"({write_data['relationships']['edges_per_second']}/s)"
    )
    print(
        "latency p50/p95/max ms: "
        f"claim={latency['claim_neighbourhood']['p50_ms']}/"
        f"{latency['claim_neighbourhood']['p95_ms']}/"
        f"{latency['claim_neighbourhood']['max_ms']}, "
        f"lineage={latency['supersession_lineage']['p50_ms']}/"
        f"{latency['supersession_lineage']['p95_ms']}/"
        f"{latency['supersession_lineage']['max_ms']}"
    )
    for name, stats in latency["reverse_residue"].items():
        print(
            f"  residue {name}: {stats['p50_ms']}/{stats['p95_ms']}/{stats['max_ms']} ms "
            f"(rows {stats['rows_returned']['mean']})"
        )
    print(
        f"  two-hop: {latency['two_hop_neighbourhood']['p50_ms']}/"
        f"{latency['two_hop_neighbourhood']['p95_ms']}/"
        f"{latency['two_hop_neighbourhood']['max_ms']} ms "
        f"(rows {latency['two_hop_neighbourhood']['rows_returned']['mean']})"
    )
    print(
        f"teardown: {report['teardown']['seconds']} s, "
        f"gone={report['teardown']['confirmed_gone']}"
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
