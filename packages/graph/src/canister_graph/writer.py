"""Idempotent graph writer.

Everything is written with deterministic ids and `MERGE`, so re-ingesting the
same corpus creates zero new nodes. Canonization appends a `CanonEvent` and
links it to the previous one with `SUPERSEDES`; history is never overwritten.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from canister_graph import ids
from canister_graph.canonize import resolve
from canister_graph.models import (
    AssertionInput,
    AssertionView,
    ClaimDecision,
    IngestDocument,
    IngestStats,
)
from canister_graph.schema import ensure_schema

WRITE_ARTIFACT = (
    "MERGE (a:Artifact {id:$id}) "
    "SET a.doc_id=$doc_id, a.title=$title, a.source=$source, "
    "a.published_at=$published_at, a.content_sha256=$sha, a.path=$path"
)

WRITE_ASSERTION = (
    "MERGE (e:Entity {id:$eid}) SET e.name=$ename "
    "MERGE (ck:ClaimKey {id:$ckid}) "
    "  SET ck.key=$ckkey, ck.entity=$ename, ck.attribute=$attr, "
    "      ck.attribute_label=$label "
    "MERGE (e)-[:HAS_CLAIM]->(ck) "
    "MERGE (p:Proposition {id:$pid}) "
    "  SET p.value=$value, p.value_norm=$value_norm, p.value_type=$vtype "
    "MERGE (ck)-[:HAS_VALUE]->(p) "
    "MERGE (art:Artifact {id:$aid}) "
    "MERGE (as:Assertion {id:$asid}) "
    "  SET as.claim_key_id=$ckid, as.stance=$stance, as.explicit=$explicit, "
    "      as.prior_value=$prior, as.span_start=$ss, as.span_end=$se, "
    "      as.quote=$quote, as.structured=$structured, "
    "      as.published_at=$published_at, as.source=$source "
    "MERGE (as)-[:ASSERTS]->(p) "
    "MERGE (as)-[:IN_ARTIFACT]->(art)"
)

READ_CLAIM_KEYS = "MATCH (ck:ClaimKey) RETURN ck.id"

READ_ASSERTIONS = (
    "MATCH (ck:ClaimKey {id:$ckid})-[:HAS_VALUE]->(p:Proposition)"
    "<-[:ASSERTS]-(a:Assertion)-[:IN_ARTIFACT]->(art:Artifact) "
    "RETURN a.id, a.stance, a.explicit, a.prior_value, p.id, p.value_norm, "
    "       art.published_at, art.source"
)

WRITE_CANON_EVENT = (
    "MERGE (ce:CanonEvent {id:$id}) "
    "SET ce.claim_key_id=$ck, ce.decision=$dec, ce.priority=$prio, "
    "    ce.reason=$reason, ce.selected_value=$val, ce.as_of=$asof, "
    "    ce.evidence_count=$n, ce.current=true"
)

CLEAR_OTHER_CURRENT = (
    "MATCH (ce:CanonEvent {id:$id}) "
    "MATCH (prev:CanonEvent) "
    "WHERE prev.claim_key_id=$ck AND prev.id <> $id "
    "SET prev.current=false"
)

LINK_SUPERSEDES = (
    "MATCH (ce:CanonEvent {id:$id}) "
    "MATCH (prev:CanonEvent) "
    "WHERE prev.claim_key_id=$ck AND prev.id <> $id "
    "WITH ce, prev ORDER BY prev.as_of DESC, prev.id DESC LIMIT 1 "
    "MERGE (ce)-[:SUPERSEDES]->(prev)"
)

LINK_SELECTS = (
    "MATCH (ce:CanonEvent {id:$id}) MATCH (p:Proposition {id:$pid}) MERGE (ce)-[:SELECTS]->(p)"
)

COUNT_NODES = "MATCH (n) RETURN count(n) AS c"
COUNT_RELS = "MATCH ()-[r]->() RETURN count(r) AS c"


class GraphWriter:
    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def ensure_schema(self) -> None:
        ensure_schema(self.graph)

    def write_artifact(self, artifact) -> None:
        self.graph.query(
            WRITE_ARTIFACT,
            {
                "id": ids.artifact_id(artifact.doc_id),
                "doc_id": artifact.doc_id,
                "title": artifact.title,
                "source": artifact.source,
                "published_at": artifact.published_at or "",
                "sha": artifact.content_sha256,
                "path": artifact.path,
            },
        )

    def write_assertion(self, assertion: AssertionInput) -> str:
        aid = ids.artifact_id(assertion.doc_id)
        eid = ids.entity_id(assertion.entity)
        ckid = ids.claim_key_id(assertion.entity, assertion.attribute)
        pid = ids.proposition_id(ckid, assertion.value_norm)
        asid = ids.assertion_id(
            aid, ckid, assertion.value_norm, assertion.span_start, assertion.span_end
        )
        self.graph.query(
            WRITE_ASSERTION,
            {
                "eid": eid,
                "ename": assertion.entity,
                "ckid": ckid,
                "ckkey": f"{assertion.entity}::{assertion.attribute}",
                "attr": assertion.attribute,
                "label": assertion.attribute_label,
                "pid": pid,
                "value": assertion.value_raw,
                "value_norm": assertion.value_norm,
                "vtype": assertion.value_type,
                "aid": aid,
                "asid": asid,
                "stance": assertion.stance,
                "explicit": assertion.explicit_supersession,
                "prior": assertion.prior_value or "",
                "ss": assertion.span_start,
                "se": assertion.span_end,
                "quote": assertion.quote,
                "structured": assertion.structured,
                "published_at": assertion.published_at or "",
                "source": assertion.source,
            },
        )
        return asid

    def ingest(self, documents: Iterable[IngestDocument]) -> IngestStats:
        doc_count = 0
        assertion_count = 0
        for document in documents:
            self.write_artifact(document.artifact)
            for assertion in document.assertions:
                self.write_assertion(assertion)
                assertion_count += 1
            doc_count += 1
        return IngestStats(documents=doc_count, assertions=assertion_count)

    def assertions_for(self, claim_key: str) -> list[AssertionView]:
        result = self.graph.ro_query(READ_ASSERTIONS, {"ckid": claim_key})
        views = []
        for row in result.result_set:
            (
                assertion_id,
                stance,
                explicit,
                prior_value,
                proposition_id,
                value_norm,
                published_at,
                source,
            ) = row
            views.append(
                AssertionView(
                    assertion_id=assertion_id,
                    proposition_id=proposition_id,
                    value_norm=value_norm,
                    stance=stance,
                    explicit_supersession=bool(explicit),
                    prior_value=prior_value or None,
                    published_at=published_at or None,
                    source=source,
                )
            )
        return views

    def claim_keys(self) -> list[str]:
        result = self.graph.ro_query(READ_CLAIM_KEYS)
        return sorted(row[0] for row in result.result_set)

    def write_canon_event(self, decision: ClaimDecision) -> str:
        event_id = ids.canon_event_id(
            decision.claim_key,
            decision.decision,
            decision.selected_proposition_id,
            decision.evidence_assertion_ids,
        )
        params = {
            "id": event_id,
            "ck": decision.claim_key,
            "dec": decision.decision,
            "prio": decision.priority if decision.priority is not None else 0,
            "reason": decision.reason,
            "val": decision.selected_value or "",
            "asof": decision.as_of,
            "n": len(decision.evidence_assertion_ids),
        }
        self.graph.query(WRITE_CANON_EVENT, params)
        self.graph.query(CLEAR_OTHER_CURRENT, {"id": event_id, "ck": decision.claim_key})
        self.graph.query(LINK_SUPERSEDES, {"id": event_id, "ck": decision.claim_key})
        if decision.selected_proposition_id:
            self.graph.query(
                LINK_SELECTS, {"id": event_id, "pid": decision.selected_proposition_id}
            )
        return event_id

    def canonize_all(self) -> list[ClaimDecision]:
        decisions = []
        for claim_key in self.claim_keys():
            decision = resolve(claim_key, self.assertions_for(claim_key))
            self.write_canon_event(decision)
            decisions.append(decision)
        return decisions

    def count_nodes(self) -> int:
        return int(self.graph.ro_query(COUNT_NODES).result_set[0][0])

    def count_relationships(self) -> int:
        return int(self.graph.ro_query(COUNT_RELS).result_set[0][0])
