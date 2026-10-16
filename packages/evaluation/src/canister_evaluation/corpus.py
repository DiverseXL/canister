"""Load the generated corpus into ingest-ready structures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from canister_extraction import ATTRIBUTE_BY_KEY, extract
from canister_graph.models import ArtifactInput, AssertionInput, IngestDocument
from canister_retrieval import Document


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_gold(corpus_dir: str | Path) -> dict:
    return json.loads((Path(corpus_dir) / "gold.json").read_text(encoding="utf-8"))


def _read_text(corpus_dir: Path, doc: dict) -> str:
    return (corpus_dir / doc["path"]).read_text(encoding="utf-8")


def build_ingest_documents(corpus_dir: str | Path, gold: dict) -> list[IngestDocument]:
    corpus_dir = Path(corpus_dir)
    documents: list[IngestDocument] = []
    for doc in gold["documents"]:
        text = _read_text(corpus_dir, doc)
        artifact = ArtifactInput(
            doc_id=doc["doc_id"],
            title=doc["title"],
            source=doc["source"],
            published_at=doc["published_at"],
            content_sha256=sha256_text(text),
            path=doc["path"],
        )
        assertions = []
        for claim in extract(text, doc_id=doc["doc_id"]):
            attribute = ATTRIBUTE_BY_KEY[claim.attribute]
            assertions.append(
                AssertionInput(
                    doc_id=doc["doc_id"],
                    entity=claim.entity,
                    attribute=claim.attribute,
                    attribute_label=claim.attribute_label,
                    value_type=attribute.value_type,
                    value_raw=claim.value_raw,
                    value_norm=claim.value_norm,
                    stance=claim.stance,
                    explicit_supersession=claim.explicit_supersession,
                    prior_value=claim.prior_value,
                    span_start=claim.span_start,
                    span_end=claim.span_end,
                    quote=claim.quote,
                    structured=claim.structured,
                    source=doc["source"],
                    published_at=doc["published_at"],
                )
            )
        documents.append(IngestDocument(artifact=artifact, assertions=tuple(assertions)))
    return documents


def build_fts_documents(corpus_dir: str | Path, gold: dict) -> list[Document]:
    corpus_dir = Path(corpus_dir)
    documents = []
    for doc in gold["documents"]:
        text = _read_text(corpus_dir, doc)
        documents.append(
            Document(
                doc_id=doc["doc_id"],
                title=doc["title"],
                body=text,
                sha256=sha256_text(text),
            )
        )
    return documents


def gold_index(gold: dict) -> dict:
    """Index gold labels for metrics.

    Returns ``{"claims": {(entity, attribute): claim}, "docs": {(entity, attribute):
    {doc_id: label}}}``.
    """
    claims = {(claim["entity"], claim["attribute"]): claim for claim in gold["claim_keys"]}
    docs: dict[tuple[str, str], dict[str, str]] = {}
    for doc in gold["documents"]:
        for planted in doc["claims"]:
            key = (planted["entity"], planted["attribute"])
            docs.setdefault(key, {})[doc["doc_id"]] = doc["gold_label"]
    return {"claims": claims, "docs": docs}
