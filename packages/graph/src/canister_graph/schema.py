"""Graph schema: labels, relationship types and index creation."""

from __future__ import annotations

from typing import Any

LABELS = (
    "Entity",
    "ClaimKey",
    "Proposition",
    "Assertion",
    "Artifact",
    "CanonEvent",
)

RELATIONSHIPS = (
    ("Entity", "HAS_CLAIM", "ClaimKey"),
    ("ClaimKey", "HAS_VALUE", "Proposition"),
    ("Assertion", "ASSERTS", "Proposition"),
    ("Assertion", "IN_ARTIFACT", "Artifact"),
    ("CanonEvent", "SELECTS", "Proposition"),
    ("CanonEvent", "SUPERSEDES", "CanonEvent"),
)

# (label, property) pairs. Keep these literals; they are never user input.
INDEXES: tuple[tuple[str, str], ...] = (
    ("Entity", "id"),
    ("ClaimKey", "id"),
    ("Proposition", "id"),
    ("Assertion", "id"),
    ("Artifact", "id"),
    ("Artifact", "doc_id"),
    ("CanonEvent", "id"),
    ("CanonEvent", "claim_key_id"),
)


def ensure_schema(graph: Any) -> None:
    """Create indexes for the schema. Safe to call repeatedly."""
    for label, prop in INDEXES:
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception as exc:  # already indexed
            if "already indexed" not in str(exc):
                raise
