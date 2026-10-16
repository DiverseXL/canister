"""Grounding logic with a fake provider: no database required."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from canister_graph import classify, ground
from canister_graph.models import ClaimState


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    rank: int
    score: float


class FakeProvider:
    def __init__(self, keys, states, values):
        self.keys = keys
        self.states = states
        self.values = values

    def relevant_claim_keys(self, question):
        return self.keys

    def claim_state(self, claim_key):
        return self.states[claim_key]

    def doc_claim_values(self, doc_id, claim_keys):
        return self.values.get(doc_id, [])


def canon(value: str) -> ClaimState:
    return ClaimState("ck", "CANON", value, "test", 1)


def ranking_with_current_late() -> list[Candidate]:
    candidates = []
    rank = 0
    for i in range(10):  # superseded, top of the BM25 ranking
        candidates.append(Candidate(f"old-{i}", rank, 10.0 - rank))
        rank += 1
    for i in range(10):  # neutral, no claim
        candidates.append(Candidate(f"neutral-{i}", rank, 5.0 - i * 0.1))
        rank += 1
    candidates.append(Candidate("current", rank, 1.0))
    return candidates


def provider_for_current_late() -> FakeProvider:
    values = {}
    for i in range(10):
        values[f"old-{i}"] = [("ck", "0.08")]
    values["current"] = [("ck", "0.06")]
    return FakeProvider(["ck"], {"ck": canon("0.06")}, values)


def test_classify_precedence() -> None:
    states = {"ck": canon("0.06")}
    assert classify([("ck", "0.06")], states) == "current"
    assert classify([("ck", "0.08")], states) == "superseded"
    assert classify([], states) == "not_in_claim_graph"
    assert classify([("ck", "0.06"), ("ck", "0.08")], states) == "current"
    contested = {"ck": ClaimState("ck", "CONTESTED", None, "no_signal", 4)}
    assert classify([("ck", "0.08")], contested) == "contested"
    unknown = {"ck": ClaimState("ck", "UNKNOWN", None, "no_assertions", None)}
    assert classify([("ck", "0.08")], unknown) == "historical"


def test_temporal_filters_superseded_and_backfills_to_ten() -> None:
    ranking = ranking_with_current_late()
    provider = provider_for_current_late()
    receipt = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert receipt["final_size"] == 10
    for entry in receipt["final_context"]:
        assert entry["label"] != "superseded"
    reasons = {entry["reason"] for entry in receipt["cut_set"]}
    assert "superseded" in reasons


def test_temporal_pins_missed_current_evidence() -> None:
    ranking = ranking_with_current_late()
    provider = provider_for_current_late()
    receipt = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert "current" in receipt["pinned"]
    assert receipt["final_context"][-1]["doc_id"] == "current"
    assert receipt["final_context"][-1]["label"] == "current"
    assert receipt["final_size"] == 10


def test_flat_mode_keeps_superseded() -> None:
    ranking = ranking_with_current_late()
    provider = provider_for_current_late()
    receipt = ground("q", "flat", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert receipt["final_size"] == 10
    assert any(entry["label"] == "superseded" for entry in receipt["final_context"])


def test_receipt_has_stable_sha256() -> None:
    ranking = ranking_with_current_late()
    provider = provider_for_current_late()
    one = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    two = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert one["sha256"] == two["sha256"]
    assert len(one["sha256"]) == 64
    flat = ground("q", "flat", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert flat["sha256"] != one["sha256"]


def test_unknown_claim_labels_history_not_current() -> None:
    values = {"d1": [("ck", "0.08")]}
    provider = FakeProvider(
        ["ck"], {"ck": ClaimState("ck", "UNKNOWN", None, "no_assertions", None)}, values
    )
    ranking = [Candidate("d1", 0, 9.0)]
    receipt = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert receipt["final_context"][0]["label"] == "historical"


def test_bad_mode_raises() -> None:
    provider = provider_for_current_late()
    with pytest.raises(ValueError):
        ground("q", "nonsense", provider=provider, retrieve=lambda q, k: [])


def test_query_ids_are_mode_sensitive() -> None:
    ranking = ranking_with_current_late()
    provider = provider_for_current_late()
    one = ground("q", "temporal", provider=provider, retrieve=lambda q, k: ranking[:k])
    two = ground("q", "flat", provider=provider, retrieve=lambda q, k: ranking[:k])
    assert one["query_id"] != two["query_id"]
