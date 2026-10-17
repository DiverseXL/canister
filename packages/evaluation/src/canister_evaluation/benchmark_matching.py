"""Frozen question-to-claim matching rule for the conflict benchmark.

The rule is deliberately small, lexical and frozen: a question matches a claim
iff it contains every entity term and at least half of the attribute terms.
Matching is case-insensitive and token based. Terms are read from each
inventory entry's ``match_terms`` field, which is hand-written from that
entry's entity name and claim key only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def question_matches_claim(question: str, match_terms: Mapping[str, Any]) -> bool:
    """Return True iff ``question`` matches the claim described by ``match_terms``.

    Token based and case-insensitive. A match requires every ``entity_terms``
    entry to be present and at least half of the ``attribute_terms`` entries to
    be present. ``match_terms`` is ``{"entity_terms": [...], "attribute_terms":
    [...]}``.
    """
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))

    def present(term: str) -> bool:
        term_tokens = re.findall(r"[a-z0-9]+", term.lower())
        return bool(term_tokens) and all(token in tokens for token in term_tokens)

    entity_terms = match_terms.get("entity_terms") or []
    attribute_terms = match_terms.get("attribute_terms") or []
    if not entity_terms or not attribute_terms:
        return False
    if not all(present(term) for term in entity_terms):
        return False
    matched = sum(1 for term in attribute_terms if present(term))
    return matched * 2 >= len(attribute_terms)
