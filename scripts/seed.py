"""Extract, write and canonize the corpus into a tenant graph."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from canister_evaluation import build_ingest_documents, load_gold
from canister_graph import (
    GraphWriter,
    build_client,
    drop_graph,
    require_local_or_allow_remote,
    select_graph,
)

DEFAULT_CORPUS = os.environ.get("CANISTER_CORPUS_DIR", "corpus/out")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a tenant graph.")
    parser.add_argument("--corpus", type=Path, default=Path(DEFAULT_CORPUS))
    parser.add_argument(
        "--tenant",
        default=os.environ.get("CANISTER_DEFAULT_TENANT", "demo"),
    )
    parser.add_argument("--keep", action="store_true", help="do not drop existing graph")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow dropping and writing the tenant graph on a non-local FALKORDB_HOST (dangerous)",
    )
    args = parser.parse_args()

    require_local_or_allow_remote(args.allow_remote, action=f"seed tenant {args.tenant!r}")

    gold = load_gold(args.corpus)
    documents = build_ingest_documents(args.corpus, gold)

    db = build_client()
    if not args.keep:
        drop_graph(db, args.tenant)
    graph = select_graph(args.tenant, db=db)
    writer = GraphWriter(graph)
    writer.ensure_schema()

    before = writer.count_nodes()
    stats = writer.ingest(documents)
    after_ingest = writer.count_nodes()
    decisions = writer.canonize_all()
    final = writer.count_nodes()

    summary = {
        "tenant": args.tenant,
        "documents": stats.documents,
        "assertions": stats.assertions,
        "nodes_before": before,
        "nodes_after_ingest": after_ingest,
        "nodes_final": final,
        "canon_events": len(decisions),
        "decisions": {
            "CANON": sum(1 for d in decisions if d.decision == "CANON"),
            "CONTESTED": sum(1 for d in decisions if d.decision == "CONTESTED"),
            "UNKNOWN": sum(1 for d in decisions if d.decision == "UNKNOWN"),
        },
        "relationships": writer.count_relationships(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
