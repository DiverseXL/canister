"""Canonization priority rules, enforced without a database.

These are the exact rules from the README:
1. explicit supersession beats everything
2. temporal ordering only when metadata and semantics agree
3. corroboration is a tie-break only; majority never overrides supersession
4. no signal -> CONTESTED
"""

from __future__ import annotations

from canister_graph import resolve
from canister_graph.models import AssertionView


def a(
    assertion_id: str,
    value: str,
    *,
    date: str | None = "2025-01-01",
    stance: str = "assert",
    explicit: bool = False,
    prior: str | None = None,
) -> AssertionView:
    return AssertionView(
        assertion_id=assertion_id,
        proposition_id="prop-" + assertion_id,
        value_norm=value,
        stance=stance,
        explicit_supersession=explicit,
        prior_value=prior,
        published_at=date,
        source="test",
    )


def test_explicit_supersession_beats_majority() -> None:
    # The 9-vs-1 adversarial case from the brief.
    assertions = [a(f"old-{i}", "0.15", date=f"2025-01-{i + 1:02d}") for i in range(9)]
    assertions.append(
        a("new", "0.07", date="2025-06-01", stance="supersede", explicit=True, prior="0.15")
    )
    decision = resolve("acme::starter_price", assertions)
    assert decision.decision == "CANON"
    assert decision.selected_value == "0.07"
    assert decision.priority == 1
    assert decision.reason == "explicit_supersession"
    assert len(decision.superseded_assertion_ids) == 9


def test_temporal_change_beats_majority() -> None:
    # Same 9-vs-1 but the later artifact relies on semantics + metadata, not the
    # word "supersedes".
    assertions = [a(f"old-{i}", "0.15", date=f"2025-01-{i + 1:02d}") for i in range(9)]
    assertions.append(a("new", "0.07", date="2025-06-01", stance="supersede", prior="0.15"))
    decision = resolve("acme::starter_price", assertions)
    assert decision.selected_value == "0.07"
    assert decision.priority == 2
    assert decision.reason == "temporal_order_and_semantics"


def test_explicit_language_beats_a_later_plain_assertion() -> None:
    assertions = [
        a("explicit", "0.05", date="2024-01-01", stance="supersede", explicit=True),
        a("later", "0.09", date="2025-12-01"),
    ]
    decision = resolve("ck", assertions)
    assert decision.selected_value == "0.05"
    assert decision.priority == 1


def test_corroboration_unanimous_is_canon() -> None:
    assertions = [a("x", "0.08"), a("y", "0.08"), a("z", "0.08")]
    decision = resolve("ck", assertions)
    assert decision.decision == "CANON"
    assert decision.selected_value == "0.08"
    assert decision.priority == 3


def test_no_signal_is_contested_never_majority() -> None:
    # 9 artifacts say 0.15, one later artifact contradicts without any change
    # language. Corroboration is a tie-break only: this is CONTESTED.
    assertions = [a(f"old-{i}", "0.15", date=f"2025-01-{i + 1:02d}") for i in range(9)]
    assertions.append(a("new", "0.07", date="2025-06-01"))
    decision = resolve("ck", assertions)
    assert decision.decision == "CONTESTED"
    assert decision.selected_value is None
    assert decision.priority == 4


def test_metadata_without_semantics_is_contested() -> None:
    assertions = [a("old", "0.08", date="2025-01-01"), a("new", "0.06", date="2025-06-01")]
    decision = resolve("ck", assertions)
    assert decision.decision == "CONTESTED"


def test_missing_dates_disagreement_is_contested() -> None:
    assertions = [a("old", "0.08", date=None), a("new", "0.06", date=None)]
    decision = resolve("ck", assertions)
    assert decision.decision == "CONTESTED"


def test_no_assertions_is_unknown() -> None:
    decision = resolve("ck", [])
    assert decision.decision == "UNKNOWN"
    assert decision.selected_value is None
    assert decision.reason == "no_assertions"


def test_single_assertion_is_canon_by_corroboration() -> None:
    decision = resolve("ck", [a("only", "30d")])
    assert decision.decision == "CANON"
    assert decision.selected_value == "30d"


def test_three_step_revision_chain_resolves_to_latest() -> None:
    # A revision chain: A is asserted, then superseded by B, then superseded by C.
    assertions = [
        a("doc-a", "0.15", date="2025-01-01", stance="assert"),
        a("doc-b", "0.10", date="2025-03-01", stance="supersede", explicit=True, prior="0.15"),
        a("doc-c", "0.05", date="2025-06-01", stance="supersede", explicit=True, prior="0.10"),
    ]
    decision = resolve("acme::starter_price", assertions)
    assert decision.decision == "CANON"
    assert decision.selected_value == "0.05"
    assert decision.priority == 1
    assert decision.reason == "explicit_supersession"
    assert set(decision.superseded_assertion_ids) == {"doc-a", "doc-b"}
    assert decision.evidence_assertion_ids == ("doc-c",)

