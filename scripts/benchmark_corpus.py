"""Build an FTS5 index over the EnterpriseRAG-Bench corpus by streaming the release zip.

Documents are read one entry at a time from ``var/benchmark/all_documents.zip``
and inserted straight into a SQLite FTS5 index; the archive is never extracted.
The build fails closed on disk pressure: it refuses to start below 6 GiB free,
re-checks every 25,000 documents, and stops cleanly if free space drops below
3 GiB. It commits every 5,000 documents, runs with WAL enabled, and never runs
VACUUM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

BATCH = 5_000
FREE_BEFORE_BYTES = 6 * 1024**3
FREE_STOP_BYTES = 3 * 1024**3
SPACE_CHECK_EVERY = 25_000

ZIP = Path("var/benchmark/all_documents.zip")
QUESTIONS = Path("var/benchmark/questions.jsonl")
INDEX = Path("var/benchmark/corpus_index.sqlite3")
OUT = Path("evidence/benchmark/corpus_index.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(str(path)).free


def doc_id_from_name(name: str) -> str:
    stem = Path(name).name[: -len(".txt")]
    return stem.split("__", 1)[0]


def title_from_text(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=ZIP)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    start_free = free_bytes(args.index.parent)
    if start_free < FREE_BEFORE_BYTES:
        raise SystemExit(
            f"refusing to start: {start_free / 1024**3:.2f} GiB free, need >= 6 GiB"
        )

    args.index.parent.mkdir(parents=True, exist_ok=True)
    for side in (
        args.index,
        Path(str(args.index) + "-wal"),
        Path(str(args.index) + "-shm"),
    ):
        if side.exists():
            side.unlink()

    conn = sqlite3.connect(str(args.index))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE VIRTUAL TABLE docs USING fts5("
        "doc_id UNINDEXED, title, body, tokenize='porter unicode61')"
    )
    conn.commit()

    seen: Counter[str] = Counter()
    duplicates = 0
    duplicate_examples: list[str] = []
    min_free = start_free
    space_checks: list[dict] = []
    stopped_early = False
    inserted = 0
    since_commit = 0
    txt_entries = 0

    started = time.perf_counter()
    with zipfile.ZipFile(args.zip) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".txt"):
                continue
            txt_entries += 1
            doc_id = doc_id_from_name(name)
            seen[doc_id] += 1
            if seen[doc_id] > 1:
                duplicates += 1
                if len(duplicate_examples) < 10:
                    duplicate_examples.append(doc_id)
                continue
            text = archive.read(name).decode("utf-8", "replace")
            conn.execute(
                "INSERT INTO docs (doc_id, title, body) VALUES (?, ?, ?)",
                (doc_id, title_from_text(text), text),
            )
            inserted += 1
            since_commit += 1
            if since_commit >= BATCH:
                conn.commit()
                since_commit = 0
            if inserted % SPACE_CHECK_EVERY == 0:
                free = free_bytes(args.index.parent)
                min_free = min(min_free, free)
                space_checks.append(
                    {"documents": inserted, "free_gb": round(free / 1024**3, 3)}
                )
                if free < FREE_STOP_BYTES:
                    stopped_early = True
                    break
    conn.commit()
    build_seconds = time.perf_counter() - started

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    index_bytes = args.index.stat().st_size
    wal_path = Path(str(args.index) + "-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0

    result = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": {
            "repo": "onyx-dot-app/EnterpriseRAG-Bench",
            "release": "v1.0.0",
            "zip": args.zip.as_posix(),
            "zip_bytes": args.zip.stat().st_size,
            "zip_sha256": sha256_file(args.zip),
            "questions": args.questions.as_posix(),
            "questions_sha256": (
                sha256_file(args.questions) if args.questions.exists() else ""
            ),
            "zip_txt_entries": txt_entries,
            "extracted": False,
        },
        "index": {
            "path": args.index.as_posix(),
            "documents": inserted,
            "duplicate_doc_ids": duplicates,
            "duplicate_id_examples": duplicate_examples,
            "build_seconds": round(build_seconds, 3),
            "index_bytes": index_bytes,
            "wal_bytes": wal_bytes,
            "batch_commit": BATCH,
            "space_check_every": SPACE_CHECK_EVERY,
            "stopped_early": stopped_early,
            "start_free_gb": round(start_free / 1024**3, 3),
            "min_free_gb": round(min_free / 1024**3, 3),
            "free_space_checks": space_checks,
            "vacuum": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["index"], indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
