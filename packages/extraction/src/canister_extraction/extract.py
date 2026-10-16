"""Deterministic claim extraction.

Produces assertions with an exact evidence span (character offsets into the raw
document text), a stance marker and a structured-vs-prose flag. No model, no
network: the same text always yields the same assertions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from canister_extraction.normalize import normalize_value
from canister_extraction.vocab import (
    PEOPLE,
    attribute_for_label,
    find_attributes,
    find_entities,
)

EXPLICIT_RE = re.compile(
    r"\bsupersed(?:e|es|ed|ing)\b"
    r"|\breplac(?:e|es|ed|ing)\b"
    r"|\boverrid(?:e|es|den|ing)\b"
    r"|\bno longer valid\b"
    r"|\bcorrect(?:s|ed|ion)\b",
    re.IGNORECASE,
)

CORROBORATE_RE = re.compile(
    r"\b(?:remains?|unchanged|confirms?|confirmed|no change)\b", re.IGNORECASE
)

_PERSON_ALT = "|".join(re.escape(name) for name in sorted(PEOPLE, key=len, reverse=True))

VALUE_PATTERNS: dict[str, str] = {
    "money": r"\$\s?\d[\d,]*(?:\.\d+)?",
    "duration_days": r"\d+\s*(?:business\s+)?days?",
    "duration_hours": r"\d+\s*hours?",
    "date": r"\d{4}-\d{2}-\d{2}",
    "person": rf"(?:{_PERSON_ALT})",
}

_LINE_RE = re.compile(r"[^\n]+")
_SENTENCE_RE = re.compile(r".+?(?:[.!?](?=\s|$)|$)")
_STRUCT_RE = re.compile(
    r"-\s*entity:\s*(?P<entity>[^\n]+)\n"
    r"-\s*attribute:\s*(?P<attribute>[^\n]+)\n"
    r"-\s*value:\s*(?P<value>[^\n]+)"
)


@dataclass(frozen=True)
class ExtractedClaim:
    doc_id: str
    entity: str
    attribute: str
    attribute_label: str
    value_raw: str
    value_norm: str
    stance: str
    explicit_supersession: bool
    prior_value: str | None
    span_start: int
    span_end: int
    quote: str
    structured: bool


def _parse_structured(text: str, doc_id: str) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    for m in _STRUCT_RE.finditer(text):
        entity_raw = m.group("entity").strip()
        attr = attribute_for_label(m.group("attribute").strip().rstrip("."))
        if attr is None:
            continue
        entities = find_entities(entity_raw)
        if not entities:
            continue
        value_raw = m.group("value").strip().rstrip(".")
        try:
            value_norm = normalize_value(value_raw, attr.value_type)
        except ValueError:
            continue
        claims.append(
            ExtractedClaim(
                doc_id=doc_id,
                entity=entities[0],
                attribute=attr.key,
                attribute_label=attr.label,
                value_raw=value_raw,
                value_norm=value_norm,
                stance="assert",
                explicit_supersession=False,
                prior_value=None,
                span_start=m.start(),
                span_end=m.end(),
                quote=text[m.start() : m.end()],
                structured=True,
            )
        )
    return claims


def _parse_sentence(sent: str, start: int, end: int, doc_id: str) -> list[ExtractedClaim]:
    entities = find_entities(sent)
    if not entities:
        return []
    attrs = find_attributes(sent)
    if not attrs:
        return []

    explicit = bool(EXPLICIT_RE.search(sent))
    claims: list[ExtractedClaim] = []
    for attr in attrs:
        pat = VALUE_PATTERNS[attr.value_type]
        prior_raw: str | None = None
        value_raw: str | None = None

        change = re.search(
            rf"from\s+(?P<old>{pat})\s+(?:to|→)\s+(?P<new>{pat})", sent, re.IGNORECASE
        )
        if change:
            prior_raw = change.group("old")
            value_raw = change.group("new")
            stance = "supersede"
        else:
            prev = re.search(rf"previously\s+(?P<old>{pat})", sent, re.IGNORECASE)
            match = re.search(pat, sent)
            if not match:
                continue
            value_raw = match.group(0)
            prior_raw = prev.group("old") if prev else None
            if CORROBORATE_RE.search(sent):
                stance = "corroborate"
            else:
                stance = "assert"
            if explicit:
                stance = "supersede"

        try:
            value_norm = normalize_value(value_raw, attr.value_type)
            prior_norm = normalize_value(prior_raw, attr.value_type) if prior_raw else None
        except ValueError:
            continue

        for entity in entities:
            claims.append(
                ExtractedClaim(
                    doc_id=doc_id,
                    entity=entity,
                    attribute=attr.key,
                    attribute_label=attr.label,
                    value_raw=value_raw,
                    value_norm=value_norm,
                    stance=stance,
                    explicit_supersession=explicit,
                    prior_value=prior_norm,
                    span_start=start,
                    span_end=end,
                    quote=sent.strip(),
                    structured=False,
                )
            )
    return claims


def extract(text: str, *, doc_id: str) -> list[ExtractedClaim]:
    """Extract deterministic claims from raw document ``text``.

    Structured fields win over prose duplicates for the same (claim key, value).
    """
    structured = _parse_structured(text, doc_id)
    seen = {(c.attribute, c.entity, c.value_norm) for c in structured}
    claims = list(structured)

    for line_m in _LINE_RE.finditer(text):
        line = line_m.group(0)
        for m in _SENTENCE_RE.finditer(line):
            sent = m.group(0).strip()
            if len(sent) < 8:
                continue
            start = line_m.start() + m.start()
            end = line_m.start() + m.end()
            for claim in _parse_sentence(sent, start, end, doc_id):
                key = (claim.attribute, claim.entity, claim.value_norm)
                if key in seen:
                    continue
                seen.add(key)
                claims.append(claim)

    claims.sort(key=lambda c: (c.span_start, c.attribute, c.entity))
    return claims
