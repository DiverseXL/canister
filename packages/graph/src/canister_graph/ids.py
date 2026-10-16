"""Deterministic, content-addressed ids for every node type.

Ids are derived only from stable inputs, so re-ingesting the same corpus maps
onto the same nodes and `MERGE` becomes a no-op.
"""

from __future__ import annotations

import hashlib

_SEP = "\x1f"


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    h.update(_SEP.join(parts).encode("utf-8"))
    return h.hexdigest()


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def entity_id(name: str) -> str:
    return "ent_" + _digest("entity", _norm(name))[:32]


def claim_key_id(entity: str, attribute: str) -> str:
    return "ck_" + _digest("claim_key", _norm(entity), _norm(attribute))[:32]


def proposition_id(claim_key: str, value_norm: str) -> str:
    return "prop_" + _digest("proposition", claim_key, value_norm)[:32]


def artifact_id(doc_id: str) -> str:
    return "art_" + _digest("artifact", doc_id)[:32]


def assertion_id(
    artifact: str,
    claim_key: str,
    value_norm: str,
    span_start: int,
    span_end: int,
) -> str:
    return (
        "asrt_"
        + _digest("assertion", artifact, claim_key, value_norm, str(span_start), str(span_end))[:32]
    )


def canon_event_id(
    claim_key: str,
    decision: str,
    selected_proposition: str | None,
    evidence_assertion_ids: list[str] | tuple[str, ...],
) -> str:
    parts = ["canon_event", claim_key, decision, selected_proposition or ""]
    parts.extend(sorted(evidence_assertion_ids))
    return "cev_" + _digest(*parts)[:32]
