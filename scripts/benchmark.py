"""Benchmark the flat vs temporal arms over the gold questions.

Same corpus, same BM25 weights, same 10-document budget. Only the context
topology changes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from canister_evaluation import (
    build_fts_documents,
    gold_index,
    load_gold,
    run_arm,
)
from canister_graph import GraphClaimProvider, GraphUnavailable, select_graph
from canister_retrieval import FtsStore

DEFAULT_CORPUS = os.environ.get("CANISTER_CORPUS_DIR", "corpus/out")
DEFAULT_INDEX = os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation arms.")
    parser.add_argument("--corpus", type=Path, default=Path(DEFAULT_CORPUS))
    parser.add_argument("--index", type=Path, default=Path(DEFAULT_INDEX))
    parser.add_argument("--tenant", default=os.environ.get("CANISTER_DEFAULT_TENANT", "demo"))
    parser.add_argument("--out", type=Path, default=Path("var/benchmark.json"))
    args = parser.parse_args()

    gold = load_gold(args.corpus)
    index = gold_index(gold)
    questions = gold["questions"]

    # Make sure the index reflects the corpus on disk.
    store = FtsStore(args.index)
    store.create()
    if store.count() == 0:
        store.add_documents(build_fts_documents(args.corpus, gold))

    try:
        graph = select_graph(args.tenant)
    except GraphUnavailable:
        raise
    provider = GraphClaimProvider(graph)

    arms = {}
    for mode in ("flat", "temporal"):
        result = run_arm(mode, questions, provider=provider, retrieve=store.bm25, index=index)
        arms[mode] = {"metrics": result["metrics"], "rows": result["rows"]}

    report = {"tenant": args.tenant, "arms": arms}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"{'metric':<32}{'flat':>12}{'temporal':>12}")
    for key in arms["flat"]["metrics"]:
        flat = arms["flat"]["metrics"][key]
        temporal = arms["temporal"]["metrics"][key]
        print(f"{key:<32}{str(flat):>12}{str(temporal):>12}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
