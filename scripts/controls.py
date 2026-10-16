"""Task 8 controls.

Six deterministic controls around the temporal arm:

a) random-removal control      (is it *these* docs, or any docs?)
b) mechanism split             (which half of the mechanism does the work?)
c) top_k sweep                 (does leak survive a bigger budget?)
d) historical mode             (is retired evidence still answerable?)
e) safety envelope             (what does temporal touch outside conflicts?)
f) tenant isolation            (does one tenant's canon leak into another?)

All numbers are deterministic: no model is called. The corpus is synthetic and
seeded; nothing here is compared to any other project's numbers.

Run: ``uv run python scripts/controls.py``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path

from canister_evaluation import (
    build_fts_documents,
    build_ingest_documents,
    gold_index,
    load_gold,
    sha256_text,
)
from canister_extraction import ATTRIBUTE_BY_KEY, normalize_value
from canister_graph import (
    GraphClaimProvider,
    GraphWriter,
    build_client,
    classify,
    drop_graph,
    ground,
    select_graph,
)
from canister_graph.models import ArtifactInput, AssertionInput
from canister_retrieval import FtsStore

DEFAULT_CORPUS = os.environ.get("CANISTER_CORPUS_DIR", "corpus/out")
DEFAULT_INDEX = os.environ.get("CANISTER_INDEX_PATH", "var/index.sqlite3")
SWEEP = (5, 10, 20)
CONFLICT_KINDS = ("majority", "conflict")


# --- gold helpers ----------------------------------------------------------
def _conflict_keys(gold: dict) -> set[tuple[str, str]]:
    return {
        (claim["entity"], claim["attribute"])
        for claim in gold["claim_keys"]
        if claim["kind"] in CONFLICT_KINDS
    }


def _claim_kind(gold: dict) -> dict[tuple[str, str], str]:
    return {(c["entity"], c["attribute"]): c["kind"] for c in gold["claim_keys"]}


def _ids(index: dict, key: tuple[str, str], label: str) -> set[str]:
    return {doc for doc, lab in index["docs"].get(key, {}).items() if lab == label}


def _final_ids(receipt: dict) -> list[str]:
    return [entry["doc_id"] for entry in receipt["final_context"]]


def _leak(ids, superseded: set[str]) -> int:
    return sum(1 for doc in ids if doc in superseded)


def _random_seed(qid: str) -> int:
    return int(hashlib.sha256(qid.encode("utf-8")).hexdigest()[:8], 16)


# --- selection mechanisms (pure, used by the mechanism split) --------------
def _rank_and_labels(provider, claim_keys, retrieve, question: str, pool: int):
    ranking = sorted(retrieve(question, pool), key=lambda candidate: candidate.rank)
    states = {key: provider.claim_state(key) for key in claim_keys}
    labels = {
        candidate.doc_id: classify(provider.doc_claim_values(candidate.doc_id, claim_keys), states)
        for candidate in ranking
    }
    return ranking, labels


def _cut_only(ranking, labels, k):
    kept = [candidate for candidate in ranking if labels[candidate.doc_id] != "superseded"]
    return kept[:k]


def _pin_only(ranking, labels, k):
    final = list(ranking[:k])
    present = {candidate.doc_id for candidate in final}
    for candidate in ranking:
        if labels[candidate.doc_id] != "current" or candidate.doc_id in present:
            continue
        if len(final) >= k:
            evicted = final.pop()
            present.discard(evicted.doc_id)
        assert len(final) < k, "pinning must evict, never extend the budget"
        final.append(candidate)
        present.add(candidate.doc_id)
    assert len(final) <= k, "pin-only must never exceed the budget"
    final.sort(key=lambda candidate: candidate.rank)
    return final


def _full(ranking, labels, k):
    kept = [candidate for candidate in ranking if labels[candidate.doc_id] != "superseded"]
    final = kept[:k]
    present = {candidate.doc_id for candidate in final}
    for candidate in kept:
        if labels[candidate.doc_id] != "current" or candidate.doc_id in present:
            continue
        if len(final) >= k:
            evicted = final.pop()
            present.discard(evicted.doc_id)
        assert len(final) < k, "a pinned current doc must evict the lowest-ranked candidate"
        final.append(candidate)
        present.add(candidate.doc_id)
    assert len(final) <= k, "the context budget is fixed at k; pinning never adds an 11th slot"
    if len(final) < k:
        for candidate in kept:
            if len(final) >= k:
                break
            if candidate.doc_id in present:
                continue
            final.append(candidate)
            present.add(candidate.doc_id)
    final.sort(key=lambda candidate: candidate.rank)
    return final


def _random_removal(ranking, baseline, n_remove, k, qid):
    rng = random.Random(_random_seed(qid))
    baseline_ids = [candidate.doc_id for candidate in baseline]
    removed = set(rng.sample(baseline_ids, min(n_remove, len(baseline_ids))))
    final = [candidate for candidate in baseline if candidate.doc_id not in removed]
    present = {candidate.doc_id for candidate in final}
    for candidate in ranking:
        if len(final) >= k:
            break
        if candidate.doc_id in removed or candidate.doc_id in present:
            continue
        final.append(candidate)
        present.add(candidate.doc_id)
    return final


# --- controls --------------------------------------------------------------
def random_removal_control(gold, index, provider, retrieve, k) -> dict:
    rows = []
    for question in gold["questions"]:
        key = (question["entity"], question["attribute"])
        if key not in _conflict_keys(gold):
            continue
        superseded = _ids(index, key, "superseded")
        claim_keys = provider.relevant_claim_keys(question["question"])
        ranking, labels = _rank_and_labels(
            provider, claim_keys, retrieve, question["question"], max(k * 4, 40)
        )

        baseline = ranking[:k]
        temporal_receipt = ground(
            question["question"], "temporal", provider=provider, retrieve=retrieve, k=k
        )
        temporal_ids = set(_final_ids(temporal_receipt))
        n_removed = sum(1 for candidate in baseline if candidate.doc_id not in temporal_ids)

        random_final = _random_removal(ranking, baseline, n_removed, k, question["qid"])
        rows.append(
            {
                "qid": question["qid"],
                "n_removed": n_removed,
                "baseline_leak": _leak([c.doc_id for c in baseline], superseded),
                "random_leak": _leak([c.doc_id for c in random_final], superseded),
                "temporal_leak": _leak(_final_ids(temporal_receipt), superseded),
            }
        )
    summary = {
        "questions": len(rows),
        "baseline_leak_total": sum(r["baseline_leak"] for r in rows),
        "random_leak_total": sum(r["random_leak"] for r in rows),
        "temporal_leak_total": sum(r["temporal_leak"] for r in rows),
        "docs_removed_total": sum(r["n_removed"] for r in rows),
        "random_beats_baseline": sum(1 for r in rows if r["random_leak"] < r["baseline_leak"]),
        "temporal_beats_baseline": sum(1 for r in rows if r["temporal_leak"] < r["baseline_leak"]),
    }
    return {"rows": rows, "summary": summary}


def mechanism_split(gold, index, provider, retrieve, k) -> dict:
    arms = {
        name: {"superseded_in_context": 0, "current_gold_in_context": 0, "sizes": []}
        for name in ("baseline", "cut_only", "pin_only", "full")
    }
    for question in gold["questions"]:
        key = (question["entity"], question["attribute"])
        if key not in _conflict_keys(gold):
            continue
        superseded = _ids(index, key, "superseded")
        current = _ids(index, key, "current")
        claim_keys = provider.relevant_claim_keys(question["question"])
        ranking, labels = _rank_and_labels(
            provider, claim_keys, retrieve, question["question"], max(k * 4, 40)
        )

        picks = {
            "baseline": ranking[:k],
            "cut_only": _cut_only(ranking, labels, k),
            "pin_only": _pin_only(ranking, labels, k),
            "full": _full(ranking, labels, k),
        }
        for name, chosen in picks.items():
            ids = [candidate.doc_id for candidate in chosen]
            arms[name]["superseded_in_context"] += _leak(ids, superseded)
            arms[name]["current_gold_in_context"] += sum(1 for doc in ids if doc in current)
            arms[name]["sizes"].append(len(ids))
    for arm in arms.values():
        sizes = arm.pop("sizes")
        arm["context_size_mean"] = round(sum(sizes) / len(sizes), 4) if sizes else None
        arm["context_size_all_ten"] = all(size == k for size in sizes)
    return {"budget": k, "over_conflict_questions": len(_conflict_keys(gold)), "arms": arms}


def top_k_sweep(gold, provider, retrieve, index) -> dict:
    result = {}
    for k in SWEEP:
        baseline_leak = 0
        temporal_leak = 0
        baseline_all = True
        temporal_all = True
        for question in gold["questions"]:
            key = (question["entity"], question["attribute"])
            if key not in _conflict_keys(gold):
                continue
            superseded = _ids(index, key, "superseded")
            flat = ground(question["question"], "flat", provider=provider, retrieve=retrieve, k=k)
            temporal = ground(
                question["question"], "temporal", provider=provider, retrieve=retrieve, k=k
            )
            baseline_leak += _leak(_final_ids(flat), superseded)
            temporal_leak += _leak(_final_ids(temporal), superseded)
            baseline_all = baseline_all and flat["final_size"] == k
            temporal_all = temporal_all and temporal["final_size"] == k
        result[str(k)] = {
            "baseline": {"leak_total": baseline_leak, "size_all_k": baseline_all},
            "temporal": {"leak_total": temporal_leak, "size_all_k": temporal_all},
        }
    return result


def historical_mode(gold, index, provider, retrieve, k) -> dict:
    rows = []
    for question in gold["questions"]:
        key = (question["entity"], question["attribute"])
        if key not in _conflict_keys(gold):
            continue
        superseded = _ids(index, key, "superseded")
        receipt = ground(question["question"], "history", provider=provider, retrieve=retrieve, k=k)
        final_ids = set(_final_ids(receipt))
        recovered = sorted(superseded & final_ids)
        cut_reasons = {entry["reason"] for entry in receipt["cut_set"]}
        rows.append(
            {
                "qid": question["qid"],
                "retired_total": len(superseded),
                "retired_recovered": len(recovered),
                "all_recovered": set(recovered) == set(superseded) and bool(superseded),
                "retired_doc_cut": "superseded" in cut_reasons,
            }
        )
    return {
        "rows": rows,
        "summary": {
            "conflicts": len(rows),
            "all_conflicts_recover_retired_evidence": all(r["all_recovered"] for r in rows),
            "any_retired_doc_cut": any(r["retired_doc_cut"] for r in rows),
        },
    }


def safety_envelope(gold, index, provider, retrieve, k) -> dict:
    conflict = _conflict_keys(gold)
    kind_map = _claim_kind(gold)
    non_conflict_total = 0
    identical = 0
    removed_outside = 0
    pins_outside = 0
    interventions = []
    for question in gold["questions"]:
        key = (question["entity"], question["attribute"])
        flat = ground(question["question"], "flat", provider=provider, retrieve=retrieve, k=k)
        temporal = ground(
            question["question"], "temporal", provider=provider, retrieve=retrieve, k=k
        )
        flat_ids = _final_ids(flat)
        temporal_ids = _final_ids(temporal)
        removed = [doc for doc in flat_ids if doc not in set(temporal_ids)]
        added = [doc for doc in temporal_ids if doc not in set(flat_ids)]
        is_conflict = key in conflict
        if not is_conflict:
            non_conflict_total += 1
            removed_outside += len(removed)
            pins_outside += len(temporal["pinned"])
            if flat["sha256"] == temporal["sha256"]:
                identical += 1
        if removed or added or temporal["pinned"]:
            interventions.append(
                {
                    "qid": question["qid"],
                    "kind": question["kind"],
                    "claim_kind": kind_map.get(key, "none"),
                    "conflict": is_conflict,
                    "claim_keys": temporal["claim_keys"],
                    "removed_from_base_ranking": removed,
                    "pinned_current": temporal["pinned"],
                    "decisions": {
                        ck: {"decision": d["decision"], "reason": d["reason"]}
                        for ck, d in temporal["decisions"].items()
                    },
                }
            )
    return {
        "non_conflict_questions": non_conflict_total,
        "non_conflict_byte_identical": identical,
        "expected_docs_removed_outside_conflicts": 0,
        "docs_removed_outside_conflicts": removed_outside,
        "pins_outside_conflicts": pins_outside,
        "interventions": interventions,
    }


def _sentinel(value_type: str) -> str:
    return {
        "money": "$9.99",
        "duration_days": "99 days",
        "duration_hours": "99 hours",
        "date": "2026-02-01",
        "person": "Zara Sentinel",
    }[value_type]


def tenant_isolation(corpus_dir, gold, index_path, tenant_a, tenant_b, k) -> dict:
    db = build_client()
    docs = build_ingest_documents(corpus_dir, gold)

    for tenant in (tenant_a, tenant_b):
        drop_graph(db, tenant)
        writer = GraphWriter(select_graph(tenant, db=db))
        writer.ensure_schema()
        writer.ingest(docs)
        writer.canonize_all()

    claim = next(c for c in gold["claim_keys"] if c["kind"] in CONFLICT_KINDS)
    key = (claim["entity"], claim["attribute"])
    attribute = ATTRIBUTE_BY_KEY[claim["attribute"]]
    sentinel_raw = _sentinel(attribute.value_type)
    sentinel_norm = normalize_value(sentinel_raw, attribute.value_type)

    writer_b = GraphWriter(select_graph(tenant_b, db=db))
    artifact = ArtifactInput(
        doc_id="isolation-control",
        title="Isolation control",
        source="isolation-control",
        published_at="2026-02-01",
        content_sha256=sha256_text(sentinel_raw),
        path="",
    )
    writer_b.write_artifact(artifact)
    writer_b.write_assertion(
        AssertionInput(
            doc_id=artifact.doc_id,
            entity=claim["entity"],
            attribute=claim["attribute"],
            attribute_label=claim["attribute_label"],
            value_type=attribute.value_type,
            value_raw=sentinel_raw,
            value_norm=sentinel_norm,
            stance="supersede",
            explicit_supersession=True,
            prior_value=claim["current_value"],
            span_start=0,
            span_end=len(sentinel_raw),
            quote=sentinel_raw,
            structured=False,
            source=artifact.source,
            published_at=artifact.published_at,
        )
    )
    writer_b.canonize_all()

    question = next(
        q
        for q in gold["questions"]
        if (q["entity"], q["attribute"]) == key and q["kind"] == "answerable"
    )
    store = FtsStore(index_path)
    provider_a = GraphClaimProvider(select_graph(tenant_a, db=db))
    provider_b = GraphClaimProvider(select_graph(tenant_b, db=db))
    receipt_a = ground(
        question["question"], "temporal", provider=provider_a, retrieve=store.bm25, k=k
    )
    receipt_b = ground(
        question["question"], "temporal", provider=provider_b, retrieve=store.bm25, k=k
    )

    value_a = receipt_a["decisions"][receipt_a["claim_keys"][0]]["selected_value"]
    value_b = receipt_b["decisions"][receipt_b["claim_keys"][0]]["selected_value"]

    result = {
        "claim_key_entity": claim["entity"],
        "claim_key_attribute": claim["attribute"],
        "question": question["question"],
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "tenant_a_value": value_a,
        "tenant_b_value": value_b,
        "expected_tenant_a": claim["current_value"],
        "expected_tenant_b": sentinel_norm,
        "isolated": value_a == claim["current_value"]
        and value_b == sentinel_norm
        and value_a != value_b,
        "tenant_a_nodes": GraphWriter(select_graph(tenant_a, db=db)).count_nodes(),
        "tenant_b_nodes": GraphWriter(select_graph(tenant_b, db=db)).count_nodes(),
    }
    drop_graph(db, tenant_a)
    drop_graph(db, tenant_b)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Task 8 controls.")
    parser.add_argument("--corpus", type=Path, default=Path(DEFAULT_CORPUS))
    parser.add_argument("--index", type=Path, default=Path(DEFAULT_INDEX))
    parser.add_argument("--tenant-a", default="canister_controls_a")
    parser.add_argument("--tenant-b", default="canister_controls_b")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("evidence/controls.json"))
    args = parser.parse_args()

    gold = load_gold(args.corpus)
    index = gold_index(gold)

    store = FtsStore(args.index)
    store.create()
    if store.count() == 0:
        store.add_documents(build_fts_documents(args.corpus, gold))

    db = build_client()
    drop_graph(db, args.tenant_a)
    writer_a = GraphWriter(select_graph(args.tenant_a, db=db))
    writer_a.ensure_schema()
    writer_a.ingest(build_ingest_documents(args.corpus, gold))
    writer_a.canonize_all()
    provider = GraphClaimProvider(select_graph(args.tenant_a, db=db))

    report = {
        "generated_by": "scripts/controls.py",
        "metrics_class": "deterministic",
        "note": (
            "Synthetic, seeded corpus (generator.py). No model is called and no "
            "number is compared to any other project."
        ),
        "budget": args.k,
        "corpus": {**gold["counts"], "seed": gold["seed"]},
        "random_removal_control": random_removal_control(gold, index, provider, store.bm25, args.k),
        "mechanism_split": mechanism_split(gold, index, provider, store.bm25, args.k),
        "top_k_sweep": top_k_sweep(gold, provider, store.bm25, index),
        "historical_mode": historical_mode(gold, index, provider, store.bm25, args.k),
        "safety_envelope": safety_envelope(gold, index, provider, store.bm25, args.k),
        "tenant_isolation": tenant_isolation(
            args.corpus, gold, args.index, args.tenant_a, args.tenant_b, args.k
        ),
    }
    drop_graph(db, args.tenant_a)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"random-removal: {report['random_removal_control']['summary']}")
    print(f"mechanism split: {json.dumps(report['mechanism_split']['arms'], sort_keys=True)}")
    print(f"top-k sweep: {json.dumps(report['top_k_sweep'], sort_keys=True)}")
    print(f"historical mode: {report['historical_mode']['summary']}")
    print(
        f"safety envelope: non_conflict={report['safety_envelope']['non_conflict_questions']} "
        f"identical={report['safety_envelope']['non_conflict_byte_identical']} "
        f"removed_outside={report['safety_envelope']['docs_removed_outside_conflicts']} "
        f"pins_outside={report['safety_envelope']['pins_outside_conflicts']}"
    )
    print(f"tenant isolation: isolated={report['tenant_isolation']['isolated']}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
