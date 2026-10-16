"""Canonization: a fixed-priority resolver.

The rules are enforced here as pure functions so they can be tested without a
database:

1. Explicit supersession language beats everything.
2. Reliable temporal ordering, only when metadata and semantics agree.
3. Corroboration is a tie-break only. Majority never overrides supersession.
4. No signal -> CONTESTED. Never invent an ordering.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from canister_graph.models import AssertionView, ClaimDecision


def _sort_key(assertion: AssertionView) -> tuple[str, str]:
    return (assertion.published_at or "", assertion.assertion_id)


def _canon(
    claim_key: str,
    assertions: Sequence[AssertionView],
    by_value: dict[str, list[AssertionView]],
    selected: AssertionView,
    priority: int,
    reason: str,
) -> ClaimDecision:
    superseded = tuple(
        sorted(a.assertion_id for a in assertions if a.value_norm != selected.value_norm)
    )
    evidence = tuple(sorted(a.assertion_id for a in by_value[selected.value_norm]))
    as_of = max((a.published_at or "" for a in assertions), default="")
    return ClaimDecision(
        claim_key=claim_key,
        decision="CANON",
        selected_value=selected.value_norm,
        selected_proposition_id=selected.proposition_id,
        selected_assertion_id=selected.assertion_id,
        priority=priority,
        reason=reason,
        superseded_assertion_ids=superseded,
        evidence_assertion_ids=evidence,
        as_of=as_of,
    )


def resolve(claim_key: str, assertions: Iterable[AssertionView]) -> ClaimDecision:
    assertions = list(assertions)
    if not assertions:
        return ClaimDecision(
            claim_key=claim_key,
            decision="UNKNOWN",
            selected_value=None,
            selected_proposition_id=None,
            selected_assertion_id=None,
            priority=None,
            reason="no_assertions",
            superseded_assertion_ids=(),
            evidence_assertion_ids=(),
            as_of="",
        )

    by_value: dict[str, list[AssertionView]] = {}
    for assertion in assertions:
        by_value.setdefault(assertion.value_norm, []).append(assertion)
    values = sorted(by_value)
    as_of = max((a.published_at or "" for a in assertions), default="")

    # Rule 1: explicit supersession beats everything.
    explicit = [a for a in assertions if a.explicit_supersession]
    if explicit:
        winner = max(explicit, key=_sort_key)
        return _canon(claim_key, assertions, by_value, winner, 1, "explicit_supersession")

    # Rule 2: reliable temporal ordering, only when metadata and semantics agree.
    if len(values) > 1 and all(a.published_at for a in assertions):
        latest = max(assertions, key=_sort_key)
        latest_date = latest.published_at or ""
        older_dates = [
            a.published_at or "" for a in assertions if a.value_norm != latest.value_norm
        ]
        metadata_agrees = all(latest_date > d for d in older_dates)
        semantic_change = latest.stance == "supersede" or (
            latest.prior_value is not None
            and latest.prior_value in values
            and latest.prior_value != latest.value_norm
        )
        if semantic_change and metadata_agrees:
            return _canon(
                claim_key, assertions, by_value, latest, 2, "temporal_order_and_semantics"
            )

    # Rule 3: corroboration is a tie-break only.
    if len(values) == 1:
        value = values[0]
        winner = min(by_value[value], key=lambda a: a.assertion_id)
        return _canon(claim_key, assertions, by_value, winner, 3, "corroborated")

    # Rule 4: no signal -> CONTESTED. Never invent an ordering.
    return ClaimDecision(
        claim_key=claim_key,
        decision="CONTESTED",
        selected_value=None,
        selected_proposition_id=None,
        selected_assertion_id=None,
        priority=4,
        reason="no_signal",
        superseded_assertion_ids=(),
        evidence_assertion_ids=tuple(sorted(a.assertion_id for a in assertions)),
        as_of=as_of,
    )
