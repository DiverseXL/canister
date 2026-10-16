"""Extraction must recover every planted claim exactly, offline and deterministically."""

from __future__ import annotations

import json
from pathlib import Path

from canister_extraction import extract


def _planted_tuple(claim: dict) -> tuple:
    return (
        claim["attribute"],
        claim["entity"],
        claim["value_norm"],
        claim["stance"],
        claim["explicit_supersession"],
        claim["prior_value"],
        claim["structured"],
    )


def _extracted_tuple(claim) -> tuple:
    return (
        claim.attribute,
        claim.entity,
        claim.value_norm,
        claim.stance,
        claim.explicit_supersession,
        claim.prior_value,
        claim.structured,
    )


def test_corpus_shape(corpus_dir: Path, gold: dict) -> None:
    assert gold["counts"] == {
        "documents": 200,
        "claim_keys": 40,
        "conflicts": 18,
        "contested": 2,
        "unanswerable_questions": 10,
        "questions": 50,
    }
    assert len(list((corpus_dir / "documents").glob("*.md"))) == 200
    assert sum(1 for q in gold["questions"] if q["kind"] == "unanswerable") == 10
    assert sum(1 for k in gold["claim_keys"] if k["kind"] == "contested") == 2


def test_extraction_matches_planted_claims(corpus_dir: Path, gold: dict) -> None:
    mismatches = []
    for doc in gold["documents"]:
        text = (corpus_dir / doc["path"]).read_text(encoding="utf-8")
        got = sorted(_extracted_tuple(c) for c in extract(text, doc_id=doc["doc_id"]))
        want = sorted(_planted_tuple(c) for c in doc["claims"])
        if got != want:
            mismatches.append((doc["doc_id"], want, got))
    assert not mismatches, f"{len(mismatches)} docs mismatched: {mismatches[:3]}"


def test_reproducible_second_build(corpus_dir: Path, gold: dict, tmp_path: Path) -> None:
    from corpus.generator import build

    out = tmp_path / "again"
    again = build(out)
    assert json.dumps(again, sort_keys=True) == json.dumps(gold, sort_keys=True)


def test_spans_are_exact(corpus_dir: Path, gold: dict) -> None:
    doc = gold["documents"][0]
    text = (corpus_dir / doc["path"]).read_text(encoding="utf-8")
    for claim in extract(text, doc_id=doc["doc_id"]):
        assert text[claim.span_start : claim.span_end].strip()
        assert claim.quote in text
