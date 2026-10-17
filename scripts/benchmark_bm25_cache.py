"""Build (resumably) the frozen BM25 candidate cache for the benchmark questions.

For each selected question exactly one BM25 query is issued against the
read-only FTS5 index in ``var/benchmark`` and the ranked doc ids and scores
(``LIMIT 40``) are appended to ``var/benchmark/bm25_cache.jsonl``. Every line is
keyed by question id plus the sha256 of the query text and of the index file, so
the cache is invalidated automatically if either changes.

The SQL uses ``ORDER BY bm25(docs)`` (FTS5's native ascending BM25 order) which
SQLite serves with its top-N plan; the fetched rows are then re-sorted in Python
by ``(bm25, doc_id)`` to mirror the documented tie-break of the system's
``FtsStore.bm25``. The retrieval rule, tokenizer and matching rule are unchanged
(the query text is produced by ``FtsStore._match_query``); the index is opened
read-only (``mode=ro``).

The build is resumable: completed questions are skipped, a torn final line is
dropped, and progress is printed every 25 questions.

Run all:        ``uv run python scripts/benchmark_bm25_cache.py``
Run conflicts:  ``uv run python scripts/benchmark_bm25_cache.py --only-conflicts``
Run a sample:   ``uv run python scripts/benchmark_bm25_cache.py --sample 20261017:100``
Verify 5:       ``uv run python scripts/benchmark_bm25_cache.py --verify 5``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from canister_retrieval.store import FtsStore

INDEX = Path("var/benchmark/corpus_index.sqlite3")
QUESTIONS = Path("var/benchmark/questions.jsonl")
INVENTORY = Path("research/conflicts_revised.json")
OUT = Path("var/benchmark/bm25_cache.jsonl")
META = Path("var/benchmark/bm25_cache.meta.json")
LIMIT = 40
PROGRESS_EVERY = 25


def sample_ids(all_ids: list[str], seed: int, n: int) -> list[str]:
    """Deterministic envelope sample shared with scripts/benchmark_controls.py."""
    return sorted(random.Random(seed).sample(sorted(all_ids), n))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_questions(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_cache(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records[record["question_id"]] = record
    return records


def write_cache(path: Path, questions: list[dict], records: dict[str, dict]) -> None:
    """Rewrite the cache in question order, dropping any torn/duplicate lines."""
    lines = []
    for question in questions:
        record = records.get(question["question_id"])
        if record is not None:
            lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def run_query(conn: sqlite3.Connection, match: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT doc_id, bm25(docs) FROM docs WHERE docs MATCH ? "
        "ORDER BY bm25(docs) LIMIT ?",
        (match, limit),
    ).fetchall()
    ordered = sorted(rows, key=lambda row: (float(row[1]), row[0]))
    return [{"doc_id": row[0], "score": round(-float(row[1]), 6)} for row in ordered]


def selected_questions(questions, args) -> list[dict]:
    if args.only_conflicts:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))["questions"]
        want = {entry["question_id"] for entry in inventory}
        return [q for q in questions if q["question_id"] in want]
    if args.sample:
        seed, n = args.sample.split(":")
        want = set(sample_ids([q["question_id"] for q in questions], int(seed), int(n)))
        return [q for q in questions if q["question_id"] in want]
    return questions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--meta", type=Path, default=META)
    parser.add_argument("--limit", type=int, default=LIMIT)
    parser.add_argument("--only-conflicts", action="store_true")
    parser.add_argument("--sample", default="", help="SEED:N deterministic envelope sample")
    parser.add_argument("--verify", type=int, default=0, help="re-query N questions and compare")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    index_sha = sha256_file(args.index)

    if args.verify:
        return verify(args, questions, index_sha)

    records = load_cache(args.out)
    valid: dict[str, dict] = {}
    for question in questions:
        record = records.get(question["question_id"])
        if record is None:
            continue
        if record.get("index_sha256") != index_sha:
            continue
        if record.get("query_sha256") != sha256_text(question["question"]):
            continue
        valid[question["question_id"]] = record
    records = valid
    write_cache(args.out, questions, records)  # clean any torn line, keep order

    subset = selected_questions(questions, args)
    todo = [q for q in subset if q["question_id"] not in records]
    print(
        f"cache: {len(records)}/{len(questions)} present, building {len(todo)} of "
        f"{len(subset)} selected, index_sha256={index_sha[:16]}",
        flush=True,
    )
    if not todo:
        write_meta(args, questions, records, index_sha)
        return 0

    store = FtsStore(args.index)
    conn = sqlite3.connect(f"file:{args.index.as_posix()}?mode=ro", uri=True)
    started = time.perf_counter()
    done = 0
    with args.out.open("a", encoding="utf-8") as handle:
        for question in todo:
            qid = question["question_id"]
            text = question["question"]
            match = store._match_query(text)
            t = time.perf_counter()
            candidates = run_query(conn, match, args.limit)
            seconds = time.perf_counter() - t
            record = {
                "question_id": qid,
                "query_sha256": sha256_text(text),
                "index_sha256": index_sha,
                "limit": args.limit,
                "search_seconds": round(seconds, 4),
                "candidates": candidates,
            }
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            records[qid] = record
            done += 1
            if done % PROGRESS_EVERY == 0 or done == len(todo):
                mean_seconds = sum(r["search_seconds"] for r in records.values()) / len(records)
                print(
                    f"[{len(records)}/{len(questions)}] +{done} elapsed="
                    f"{time.perf_counter() - started:.1f}s mean={mean_seconds:.2f}s",
                    flush=True,
                )
    conn.close()
    write_meta(args, questions, records, index_sha)
    return 0


def write_meta(args, questions, records, index_sha) -> None:
    present = [records[q["question_id"]] for q in questions if q["question_id"] in records]
    meta = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "index_file": args.index.as_posix(),
        "index_sha256": index_sha,
        "limit": args.limit,
        "questions_total": len(questions),
        "cache_entries": len(present),
        "queries_issued": len(present),
        "total_search_seconds": round(sum(r["search_seconds"] for r in present), 3),
        "complete": len(present) == len(questions),
    }
    args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("meta:", json.dumps(meta), flush=True)


def verify(args, questions, index_sha) -> int:
    records = load_cache(args.out)
    store = FtsStore(args.index)
    conn = sqlite3.connect(f"file:{args.index.as_posix()}?mode=ro", uri=True)
    checked = 0
    mismatches = []
    for question in questions:
        if checked >= args.verify:
            break
        record = records.get(question["question_id"])
        if record is None:
            continue
        match = store._match_query(question["question"])
        fresh = run_query(conn, match, args.limit)
        checked += 1
        if fresh != record["candidates"]:
            mismatches.append(question["question_id"])
        print(
            f"verify {question['question_id']}: "
            f"{'identical' if fresh == record['candidates'] else 'MISMATCH'}",
            flush=True,
        )
    conn.close()
    print(f"verified {checked} questions, mismatches={mismatches}", flush=True)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
