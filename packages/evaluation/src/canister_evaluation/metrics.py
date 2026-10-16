"""Metrics over a single ground() receipt, relative to the gold labels."""

from __future__ import annotations

from typing import Any


def score_question(
    receipt: dict[str, Any],
    question: dict[str, Any],
    index: dict[str, Any],
) -> dict[str, Any]:
    key = (question["entity"], question["attribute"])
    label_map = index["docs"].get(key, {})
    final_ids = [entry["doc_id"] for entry in receipt["final_context"]]

    current_docs = [doc for doc, label in label_map.items() if label == "current"]
    superseded_docs = [doc for doc, label in label_map.items() if label == "superseded"]
    contested_docs = [doc for doc, label in label_map.items() if label == "contested"]

    leak = sum(1 for doc in final_ids if doc in superseded_docs)
    current_hits = [doc for doc in current_docs if doc in final_ids]
    contested_hits = [doc for doc in contested_docs if doc in final_ids]

    decisions = receipt["decisions"]
    if len(receipt["claim_keys"]) == 1:
        decision = decisions[receipt["claim_keys"][0]]
        graph_answer = decision["selected_value"] or decision["decision"]
    else:
        graph_answer = "UNKNOWN"

    expected = question["expected"]
    if expected == "UNKNOWN":
        answer_correct = graph_answer == "UNKNOWN"
    else:
        answer_correct = graph_answer == expected

    return {
        "qid": question["qid"],
        "kind": question["kind"],
        "context_size": len(final_ids),
        "superseded_leak": leak,
        "current_recall": (len(current_hits) / len(current_docs) if current_docs else None),
        "contested_recall": (len(contested_hits) / len(contested_docs) if contested_docs else None),
        "has_current": bool(current_hits),
        "has_contested": bool(contested_hits),
        "graph_answer": graph_answer,
        "expected": expected,
        "answer_correct": answer_correct,
        "claim_keys": receipt["claim_keys"],
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    answerable = [r for r in rows if r["kind"] == "answerable"]
    contested = [r for r in rows if r["kind"] == "contested"]
    unanswerable = [r for r in rows if r["kind"] == "unanswerable"]

    return {
        "questions": len(rows),
        "context_size_mean": mean([r["context_size"] for r in rows]),
        "context_size_all_ten": all(r["context_size"] == 10 for r in rows),
        "superseded_leak_total": sum(r["superseded_leak"] for r in rows),
        "superseded_leak_questions": sum(1 for r in rows if r["superseded_leak"] > 0),
        "current_recall_mean": mean([r["current_recall"] for r in rows]),
        "answer_correct_rate": mean([1 if r["answer_correct"] else 0 for r in rows]),
        "answerable_correct_rate": mean([1 if r["answer_correct"] else 0 for r in answerable]),
        "contested_correct_rate": mean([1 if r["answer_correct"] else 0 for r in contested]),
        "unanswerable_correct_rate": mean([1 if r["answer_correct"] else 0 for r in unanswerable]),
    }
