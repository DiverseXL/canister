"""Dataclasses shared across the graph package."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArtifactInput:
    doc_id: str
    title: str
    source: str
    published_at: str | None
    content_sha256: str
    path: str = ""


@dataclass(frozen=True)
class AssertionInput:
    doc_id: str
    entity: str
    attribute: str
    attribute_label: str
    value_type: str
    value_raw: str
    value_norm: str
    stance: str
    explicit_supersession: bool
    prior_value: str | None
    span_start: int
    span_end: int
    quote: str
    structured: bool
    source: str = ""
    published_at: str | None = None


@dataclass(frozen=True)
class IngestDocument:
    artifact: ArtifactInput
    assertions: tuple[AssertionInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IngestStats:
    documents: int
    assertions: int


@dataclass(frozen=True)
class AssertionView:
    """An assertion as read back from the graph, for canonization."""

    assertion_id: str
    proposition_id: str
    value_norm: str
    stance: str
    explicit_supersession: bool
    prior_value: str | None
    published_at: str | None
    source: str


@dataclass(frozen=True)
class ClaimDecision:
    claim_key: str
    decision: str  # CANON | CONTESTED | UNKNOWN
    selected_value: str | None
    selected_proposition_id: str | None
    selected_assertion_id: str | None
    priority: int | None
    reason: str
    superseded_assertion_ids: tuple[str, ...]
    evidence_assertion_ids: tuple[str, ...]
    as_of: str = ""


@dataclass(frozen=True)
class ClaimState:
    claim_key: str
    decision: str
    selected_value: str | None
    reason: str
    priority: int | None
