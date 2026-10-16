"""FastAPI service. FalkorDB is required: if it is down we fail closed."""

from __future__ import annotations

import os

from canister_evaluation import build_context, ground_from_graph
from canister_graph import GraphUnavailable, build_client
from canister_graph.grounding import MODES
from canister_retrieval import FtsStore
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Canister",
    version="0.1.0",
    description=(
        "Temporal claim graph grounding. Superseded claims stay answerable as "
        "history but never reach the model as present-tense context."
    ),
)


def _index_path() -> str:
    return os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")


def _default_tenant() -> str:
    return os.environ.get("CANISTER_DEFAULT_TENANT", "demo")


class GroundRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = "temporal"
    tenant_id: str | None = None
    k: int = Field(10, ge=1, le=50)
    include_text: bool = False


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
    if request.mode not in MODES:
        raise HTTPException(
            status_code=400,
            detail={"error": "BAD_REQUEST", "message": f"unknown mode: {request.mode!r}"},
        )
    tenant = request.tenant_id or _default_tenant()
    try:
        receipt = ground_from_graph(
            request.question,
            request.mode,
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

    if request.include_text:
        store = FtsStore(_index_path())
        receipt["context"] = build_context(receipt, store)
    return receipt
