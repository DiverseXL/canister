"""Grounded context selection.

BM25 proposes candidates; the graph decides which of them may still ground a
present-tense answer. Superseded candidates are filtered, the ranking backfills
to the same budget, and any missed current evidence is pinned by evicting the
lowest-ranked candidate. The result is a receipt, not just a list.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any, Protocol

from canister_graph.models import ClaimState

MODES = ("flat", "temporal", "history")

LABELS = (
    "current",
    "contested",
    "historical",
    "superseded",
    "not_in_claim_graph",
)

_PRECEDENCE = {
    "current": 0,
    "contested": 1,
    "historical": 2,
    "superseded": 3,
    "not_in_claim_graph": 4,
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

READ_KEY_INFO = "MATCH (ck:ClaimKey) RETURN ck.id, ck.entity, ck.attribute, ck.attribute_label"
READ_STATE = (
    "MATCH (ce:CanonEvent {claim_key_id:$ck}) WHERE ce.current=true "
    "RETURN ce.decision, ce.selected_value, ce.priority, ce.reason "
    "ORDER BY ce.as_of DESC, ce.id DESC LIMIT 1"
)
READ_DOC_VALUES = (
    "MATCH (ck:ClaimKey)-[:HAS_VALUE]->(p:Proposition)"
    "<-[:ASSERTS]-(a:Assertion)-[:IN_ARTIFACT]->(art:Artifact) "
    "WHERE art.doc_id=$doc AND ck.id IN $cks "
    "RETURN DISTINCT ck.id AS ck, p.value_norm AS value"
)

_CYPHER: dict[str, str] = {
    "READ_KEY_INFO": READ_KEY_INFO,
    "READ_STATE": READ_STATE,
    "READ_DOC_VALUES": READ_DOC_VALUES,
}


def cypher_queries() -> dict[str, str]:
    """Identifiers of the Cypher queries used by :func:`ground`, with a hash of each."""
    return {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        for name, text in _CYPHER.items()
    }


class ClaimProvider(Protocol):
    def relevant_claim_keys(self, question: str) -> list[str]: ...

    def claim_state(self, claim_key: str) -> ClaimState: ...

    def doc_claim_values(self, doc_id: str, claim_keys: Sequence[str]) -> list[tuple[str, str]]: ...


def classify(
    values: Sequence[tuple[str, str]],
    states: dict[str, ClaimState],
) -> str:
    """Label a document relative to the query's claim keys.

    Precedence: current > contested > historical > superseded > not_in_claim_graph.
    """
    if not values:
        return "not_in_claim_graph"
    labels: set[str] = set()
    for claim_key, value in values:
        state = states.get(claim_key)
        if state is None:
            labels.add("historical")
            continue
        if state.decision == "CANON":
            labels.add("current" if value == state.selected_value else "superseded")
        elif state.decision == "CONTESTED":
            labels.add("contested")
        else:
            labels.add("historical")
    if not labels:
        return "not_in_claim_graph"
    return min(labels, key=lambda label: _PRECEDENCE[label])


def _sha256_context(final: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        [
            {"rank": entry["rank"], "doc_id": entry["doc_id"], "label": entry["label"]}
            for entry in final
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entry(candidate, label: str) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "doc_id": candidate.doc_id,
        "label": label,
        "bm25_score": round(float(candidate.score), 6),
    }


def ground(
    question: str,
    mode: str,
    *,
    provider: ClaimProvider,
    retrieve,
    k: int = 10,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}")

    query_id = hashlib.sha256(f"{mode}\x1f{question}".encode()).hexdigest()[:16]
    claim_keys = provider.relevant_claim_keys(question)
    states = {claim_key: provider.claim_state(claim_key) for claim_key in claim_keys}

    pool = k if mode == "flat" else max(k * 4, 40)
    ranking = sorted(retrieve(question, pool), key=lambda candidate: candidate.rank)

    labels: dict[str, str] = {}
    for candidate in ranking:
        values = provider.doc_claim_values(candidate.doc_id, claim_keys)
        labels[candidate.doc_id] = classify(values, states)

    if mode == "flat":
        final = ranking[:k]
        selected_ids = {candidate.doc_id for candidate in final}
        pinned: list[str] = []
    elif mode == "history":
        superseded = [c for c in ranking if labels[c.doc_id] == "superseded"]
        final = superseded[:k]
        selected_ids = {candidate.doc_id for candidate in final}
        pinned = []
    else:  # temporal
        final, pinned, selected_ids = _select_temporal(ranking, labels, k)

    cut_set = []
    for candidate in ranking:
        if candidate.doc_id in selected_ids:
            continue
        if mode == "history":
            reason = "not_superseded"
        elif labels[candidate.doc_id] == "superseded":
            reason = "superseded"
        else:
            reason = "outside_budget"
        cut_set.append({**_entry(candidate, labels[candidate.doc_id]), "reason": reason})

    final.sort(key=lambda candidate: candidate.rank)
    final_context = [_entry(candidate, labels[candidate.doc_id]) for candidate in final]

    return {
        "mode": mode,
        "query": question,
        "query_id": query_id,
        "grounding": "TEMPORAL_GRAPH",
        "claim_keys": claim_keys,
        "decisions": {
            claim_key: {
                "decision": state.decision,
                "selected_value": state.selected_value,
                "priority": state.priority,
                "reason": state.reason,
            }
            for claim_key, state in states.items()
        },
        "pool_size": len(ranking),
        "input_ranking": [_entry(candidate, labels[candidate.doc_id]) for candidate in ranking],
        "cut_set": cut_set,
        "final_context": final_context,
        "pinned": pinned,
        "final_size": len(final_context),
        "sha256": _sha256_context(final_context),
        "cypher_queries": cypher_queries(),
    }


def _select_temporal(
    ranking: list[Any], labels: dict[str, str], k: int
) -> tuple[list[Any], list[str], set[str]]:
    kept = [c for c in ranking if labels[c.doc_id] != "superseded"]
    final = kept[:k]
    present = {candidate.doc_id for candidate in final}
    pinned: list[str] = []

    for candidate in kept:
        if labels[candidate.doc_id] != "current" or candidate.doc_id in present:
            continue
        if len(final) >= k:
            evicted = final.pop()
            present.discard(evicted.doc_id)
        final.append(candidate)
        present.add(candidate.doc_id)
        pinned.append(candidate.doc_id)

    if len(final) < k:
        for candidate in kept:
            if len(final) >= k:
                break
            if candidate.doc_id in present:
                continue
            final.append(candidate)
            present.add(candidate.doc_id)

    return final, pinned, present


class GraphClaimProvider:
    """Reads claim state from a FalkorDB graph."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self._keys: list[tuple[str, str, str, str]] | None = None

    def _all_keys(self) -> list[tuple[str, str, str, str]]:
        if self._keys is None:
            result = self.graph.query(READ_KEY_INFO)
            self._keys = [(row[0], row[1], row[2], row[3] or "") for row in result.result_set]
        return self._keys

    def all_claim_keys(self) -> list[dict[str, str]]:
        return [
            {
                "claim_key": key_id,
                "entity": entity,
                "attribute": attribute,
                "attribute_label": label,
            }
            for key_id, entity, attribute, label in self._all_keys()
        ]

    def relevant_claim_keys(self, question: str) -> list[str]:
        question_lower = question.lower()
        question_tokens = set(_TOKEN_RE.findall(question_lower))
        scored: list[tuple[int, str]] = []
        for key_id, entity, _attribute, label in self._all_keys():
            if entity.lower() not in question_lower:
                continue
            label_tokens = set(_TOKEN_RE.findall(label.lower()))
            if not label_tokens or not label_tokens.issubset(question_tokens):
                continue
            scored.append((len(label_tokens), key_id))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        return sorted(key_id for score, key_id in scored if score == best)

    def claim_state(self, claim_key: str) -> ClaimState:
        result = self.graph.query(READ_STATE, {"ck": claim_key})
        if not result.result_set:
            return ClaimState(
                claim_key=claim_key,
                decision="UNKNOWN",
                selected_value=None,
                reason="no_canon_event",
                priority=None,
            )
        decision, selected_value, priority, reason = result.result_set[0]
        return ClaimState(
            claim_key=claim_key,
            decision=decision,
            selected_value=selected_value or None,
            reason=reason,
            priority=int(priority) if priority not in (None, "") else None,
        )

    def doc_claim_values(self, doc_id: str, claim_keys: Sequence[str]) -> list[tuple[str, str]]:
        if not claim_keys:
            return []
        result = self.graph.query(READ_DOC_VALUES, {"doc": doc_id, "cks": list(claim_keys)})
        return [(row[0], row[1]) for row in result.result_set]
