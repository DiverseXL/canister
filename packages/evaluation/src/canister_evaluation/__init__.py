"""Canister evaluation package (arms, context builder, metrics)."""

from canister_evaluation.arms import ground_from_graph, run_arm
from canister_evaluation.context import build_context, render_context
from canister_evaluation.corpus import (
    build_fts_documents,
    build_ingest_documents,
    gold_index,
    load_gold,
    sha256_text,
)
from canister_evaluation.metrics import aggregate, score_question

__all__ = [
    "ground_from_graph",
    "run_arm",
    "build_context",
    "render_context",
    "build_fts_documents",
    "build_ingest_documents",
    "gold_index",
    "load_gold",
    "sha256_text",
    "aggregate",
    "score_question",
]
