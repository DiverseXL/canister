"""SQLite FTS5 store.

FTS5's built-in ``bm25()`` ranks candidates. That is the *only* thing this
module decides: relevance. The graph decides what may still be said.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "which",
        "who",
        "for",
        "of",
        "to",
        "in",
        "on",
        "at",
        "and",
        "or",
        "current",
        "please",
        "tell",
        "me",
        "about",
        "does",
        "do",
        "with",
    }
)


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    body: str
    sha256: str = ""


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    rank: int
    score: float


class FtsStore:
    """A file-backed SQLite FTS5 index over document titles and bodies."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def create(self) -> None:
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5("
            "doc_id UNINDEXED, title, body, sha256 UNINDEXED, tokenize='porter unicode61')"
        )
        self.conn.commit()

    def reset(self) -> None:
        self.conn.execute("DROP TABLE IF EXISTS docs")
        self.conn.commit()
        self.create()

    def add_documents(self, documents) -> int:
        count = 0
        for doc in documents:
            self.conn.execute("DELETE FROM docs WHERE doc_id = ?", (doc.doc_id,))
            self.conn.execute(
                "INSERT INTO docs (doc_id, title, body, sha256) VALUES (?, ?, ?, ?)",
                (doc.doc_id, doc.title, doc.body, doc.sha256),
            )
            count += 1
        self.conn.commit()
        return count

    def count(self) -> int:
        row = self.conn.execute("SELECT count(*) FROM docs").fetchone()
        return int(row[0])

    def _match_query(self, query: str) -> str:
        tokens = [
            token
            for token in (t.lower() for t in _TOKEN_RE.findall(query))
            if token not in STOPWORDS
        ]
        if not tokens:
            tokens = [t.lower() for t in _TOKEN_RE.findall(query)]
        return " OR ".join(f'"{token}"' for token in tokens)

    def bm25(self, query: str, limit: int = 10) -> list[Candidate]:
        match = self._match_query(query)
        if not match:
            return []
        rows = self.conn.execute(
            "SELECT doc_id, bm25(docs) AS score FROM docs "
            "WHERE docs MATCH ? ORDER BY score ASC, doc_id ASC LIMIT ?",
            (match, limit),
        ).fetchall()
        return [
            Candidate(doc_id=row[0], rank=rank, score=-float(row[1]))
            for rank, row in enumerate(rows)
        ]

    def get_text(self, doc_id: str) -> str:
        row = self.conn.execute(
            "SELECT title, body FROM docs WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if row is None:
            return ""
        return f"{row[0]}\n\n{row[1]}"

    def get_sha256(self, doc_id: str) -> str:
        row = self.conn.execute("SELECT sha256 FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
        return row[0] if row else ""

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
