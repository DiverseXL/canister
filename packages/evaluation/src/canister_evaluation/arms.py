"""Evaluation arms and the fail-closed graph service."""

from __future__ import annotations

import redis.exceptions
from canister_graph.client import GraphUnavailable, select_graph
from canister_graph.grounding import GraphClaimProvider, ground
from canister_retrieval import FtsStore

from canister_evaluation.metrics import aggregate, score_question

CONNECTION_ERRORS = (
    GraphUnavailable,
    redis.exceptions.RedisError,
    OSError,
    TimeoutError,
)


def ground_from_graph(
    question: str,
    mode: str,
    *,
    tenant_id: str,
    index_path: str,
    k: int = 10,
) -> dict:
    """Ground a question against a tenant graph, failing closed.

    If FalkorDB is unreachable this raises :class:`GraphUnavailable`; callers must
    not fall back to plain retrieval.
    """
    try:
        graph = select_graph(tenant_id)
        store = FtsStore(index_path)
        provider = GraphClaimProvider(graph)
        return ground(question, mode, provider=provider, retrieve=store.bm25, k=k)
    except CONNECTION_ERRORS as exc:
        if isinstance(exc, GraphUnavailable):
            raise
        raise GraphUnavailable(f"temporal graph unavailable: {exc}") from exc


def run_arm(
    mode: str,
    questions: list[dict],
    *,
    provider,
    retrieve,
    index: dict,
    k: int = 10,
) -> dict:
    """Run one evaluation arm (``flat`` / ``temporal`` / ``history``) over questions."""
    rows = []
    receipts = []
    for question in questions:
        receipt = ground(question["question"], mode, provider=provider, retrieve=retrieve, k=k)
        receipts.append(receipt)
        rows.append(score_question(receipt, question, index))
    return {"mode": mode, "metrics": aggregate(rows), "rows": rows, "receipts": receipts}
