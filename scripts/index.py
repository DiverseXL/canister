"""Build the SQLite FTS5 / BM25 index from the generated corpus."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from canister_evaluation import build_fts_documents, load_gold
from canister_retrieval import FtsStore

DEFAULT_CORPUS = os.environ.get("CANISTER_CORPUS_DIR", "corpus/out")
DEFAULT_INDEX = os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the FTS5 index.")
    parser.add_argument("--corpus", type=Path, default=Path(DEFAULT_CORPUS))
    parser.add_argument("--index", type=Path, default=Path(DEFAULT_INDEX))
    args = parser.parse_args()

    gold = load_gold(args.corpus)
    documents = build_fts_documents(args.corpus, gold)
    args.index.parent.mkdir(parents=True, exist_ok=True)
    store = FtsStore(args.index)
    store.reset()
    count = store.add_documents(documents)
    print(f"Indexed {count} documents into {args.index}")

    probe = store.bm25("starter plan price", 5)
    print(f"BM25 self-check: top {len(probe)} candidates for a sample query")


if __name__ == "__main__":
    main()
