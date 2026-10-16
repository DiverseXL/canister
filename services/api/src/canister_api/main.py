"""FastAPI service. FalkorDB is required: if it is down we fail closed."""

from __future__ import annotations

import hashlib
import json
import os

from canister_evaluation import build_context, ground_from_graph
from canister_graph import GraphClaimProvider, GraphUnavailable, build_client, select_graph
from canister_graph.grounding import cypher_queries
from canister_retrieval import FtsStore
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from canister_api import receipts

app = FastAPI(
    title="Canister",
    version="0.2.0",
    description=(
        "Temporal claim graph grounding. Superseded claims stay answerable as "
        "history but never reach the model as present-tense context."
    ),
)

_origins = os.environ.get(
    "CANISTER_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in _origins.split(",") if origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public modes map onto the graph's internal selection modes.
MODE_ALIASES = {"current": "temporal", "temporal": "temporal", "historical": "history"}


def _index_path() -> str:
    return os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")


def _default_tenant() -> str:
    return os.environ.get("CANISTER_DEFAULT_TENANT", "demo")


class GroundRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = "current"
    tenant_id: str | None = None
    k: int = Field(10, ge=1, le=50)
    include_text: bool = False


def _receipt_id(tenant: str, query_id: str) -> str:
    return hashlib.sha256(f"{tenant}\x1f{query_id}".encode()).hexdigest()[:16]


@app.get("/health")
def health() -> dict:
    reachable = True
    detail = "ok"
    try:
        build_client().connection.ping()
    except Exception as exc:  # pragma: no cover - depends on environment
        reachable = False
        detail = str(exc)
    return {
        "status": "ok" if reachable else "degraded",
        "graph_reachable": reachable,
        "detail": detail,
    }


@app.post("/ground")
def ground_endpoint(request: GroundRequest) -> dict:
    if request.mode not in MODE_ALIASES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BAD_REQUEST",
                "message": (
                    f"unknown mode: {request.mode!r}; expected one of {sorted(MODE_ALIASES)}"
                ),
            },
        )
    internal = MODE_ALIASES[request.mode]
    tenant = request.tenant_id or _default_tenant()
    try:
        receipt = ground_from_graph(
            request.question,
            internal,
            tenant_id=tenant,
            index_path=_index_path(),
            k=request.k,
        )
    except GraphUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "TEMPORAL_GRAPH_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"error": "BAD_REQUEST", "message": str(exc)}
        ) from exc

    receipt["tenant_id"] = tenant
    receipt["mode_requested"] = request.mode
    receipt["mode_internal"] = internal
    rid = _receipt_id(tenant, receipt["query_id"])
    receipt["receipt_id"] = rid

    if request.include_text:
        store = FtsStore(_index_path())
        receipt["context"] = build_context(receipt, store)

    receipts.save(rid, receipt)
    return receipt


@app.get("/grounding/{receipt_id}")
def grounding_record_endpoint(receipt_id: str) -> dict:
    if not receipts.valid_id(receipt_id):
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": "invalid grounding record id"},
        )
    stored = receipts.load(receipt_id)
    if stored is None:
        raise HTTPException(
            status_code=404, detail={"error": "NOT_FOUND", "message": "no such grounding record"}
        )
    return stored


@app.get("/receipt/{receipt_id}", include_in_schema=False)
def grounding_record_alias(receipt_id: str) -> dict:
    """Deprecated alias for ``/grounding/{id}``, kept for existing clients."""
    return grounding_record_endpoint(receipt_id)


@app.get("/claims")
def claims_endpoint(tenant_id: str | None = None) -> dict:
    tenant = tenant_id or _default_tenant()
    try:
        graph = select_graph(tenant)
        provider = GraphClaimProvider(graph)
        claims = provider.all_claim_keys()
        for claim in claims:
            state = provider.claim_state(claim["claim_key"])
            claim["decision"] = state.decision
            claim["selected_value"] = state.selected_value
            claim["priority"] = state.priority
            claim["reason"] = state.reason
    except GraphUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "TEMPORAL_GRAPH_UNAVAILABLE", "message": str(exc)},
        ) from exc

    payload = {"tenant_id": tenant, "claims": claims, "count": len(claims)}
    payload["sha256"] = hashlib.sha256(
        json.dumps(claims, sort_keys=True).encode("utf-8")
    ).hexdigest()
    payload["cypher_queries"] = {
        name: cypher_queries()[name] for name in ("READ_KEY_INFO", "READ_STATE")
    }
    return payload
