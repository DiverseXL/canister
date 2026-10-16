"""Plain tool handlers, importable without any MCP transport.

These are the exact functions the MCP server exposes. They fail closed: an
unreachable FalkorDB raises :class:`GraphUnavailable`; nothing falls back to
plain retrieval.
"""

from __future__ import annotations

import os

from canister_evaluation import ground_from_graph
from canister_graph import GraphClaimProvider, select_graph

MODE_ALIASES = {"current": "temporal", "temporal": "temporal", "historical": "history"}


def _tenant(tenant_id: str | None) -> str:
    return tenant_id or os.environ.get("CANISTER_DEFAULT_TENANT", "demo")


def _index_path() -> str:
    return os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")


def canister_ground(
    question: str,
    mode: str = "current",
    tenant_id: str | None = None,
    k: int = 10,
) -> dict:
    """Ground a question against a tenant's temporal claim graph."""
    if mode not in MODE_ALIASES:
        raise ValueError(f"unknown mode: {mode!r}; expected one of {sorted(MODE_ALIASES)}")
    return ground_from_graph(
        question,
        MODE_ALIASES[mode],
        tenant_id=_tenant(tenant_id),
        index_path=_index_path(),
        k=k,
    )


def canister_claim(claim_key: str | None = None, tenant_id: str | None = None) -> dict:
    """Look up a claim key's state, or list every claim key for a tenant."""
    tenant = _tenant(tenant_id)
    provider = GraphClaimProvider(select_graph(tenant))
    if claim_key:
        state = provider.claim_state(claim_key)
        return {
            "tenant_id": tenant,
            "claim_key": claim_key,
            "decision": state.decision,
            "selected_value": state.selected_value,
            "priority": state.priority,
            "reason": state.reason,
        }
    return {
        "tenant_id": tenant,
        "count": len(provider.all_claim_keys()),
        "claims": provider.all_claim_keys(),
    }
