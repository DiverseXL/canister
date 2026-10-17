"""Benchmark controls (deterministic, no model in the loop).

Adapted from ``scripts/controls.py`` for the EnterpriseRAG-Bench corpus: the
SQLite FTS5 index in ``var/benchmark`` and the ``bench`` tenant graph seeded
from ``research/conflicts_revised.json``.

Question -> claim matching uses the *frozen* rule
(``canister_evaluation.benchmark_matching.question_matches_claim``); the graph
itself is read, never written, and no state is set by hand.

Retrieval is FTS5 ``bm25()`` over the same index, served from a frozen
per-question candidate cache (``var/benchmark/bm25_cache.jsonl``, built once by
``scripts/benchmark_bm25_cache.py`` with ``LIMIT 40``). No arm issues a query:
top-5/top-10/top-20 and every backfill pool are prefixes of that single ranked
list, so every arm sees the same ranking and the same budget, and every context
is asserted to hold exactly ``k`` documents. The cache is keyed by the sha256 of
the query text and validated against the sha256 of the index file.

The safety envelope runs on the 19 conflict questions plus a fixed random
sample of 100 questions (seed recorded), labelled "sample of 100, not all 500".

Run: ``uv run python scripts/benchmark_controls.py``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from canister_evaluation.benchmark_matching import question_matches_claim
from canister_graph import GraphClaimProvider, build_client, classify, ground, ids, select_graph

INDEX = Path("var/benchmark/corpus_index.sqlite3")
QUESTIONS = Path("var/benchmark/questions.jsonl")
INVENTORY = Path("research/conflicts_revised.json")
CACHE = Path("var/benchmark/bm25_cache.jsonl")
CORPUS_INDEX = Path("evidence/benchmark/corpus_index.json")
MATCHING = Path("evidence/benchmark/matching.json")
OUT = Path("evidence/benchmark/controls.json")
TENANT = "bench"
K = 10
SWEEP = (5, 10, 20)
CACHE_LIMIT = 40  # ranked candidates stored per question; arms slice prefixes of this list
ENVELOPE_SAMPLE = 100
ENVELOPE_SEED = 20261017
ENVELOPE_LABEL = "sample of 100, not all 500"
MECHANISMS = ("baseline", "cut_only", "pin_only", "full")


def sample_ids(all_ids: list[str], seed: int, n: int) -> list[str]:
    """Deterministic envelope sample shared with scripts/benchmark_bm25_cache.py."""
    return sorted(random.Random(seed).sample(sorted(all_ids), n))


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    rank: int
    score: float


class CachedRetriever:
    """Read-only BM25 retriever over the frozen candidate cache.

    No arm issues a query: ``var/benchmark/bm25_cache.jsonl`` holds the ranked
    top-``CACHE_LIMIT`` doc ids and scores per question (built once by
    ``scripts/benchmark_bm25_cache.py``); top-5/top-10/top-20 and every backfill
    pool are prefixes of that same list. Entries are keyed by the sha256 of the
    query text and validated against the sha256 of the index file.
    """

    def __init__(self, path: Path, index_sha256: str) -> None:
        self._by_query: dict[str, list[Candidate]] = {}
        self._entries: dict[str, dict] = {}
        limit = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["index_sha256"] != index_sha256:
                continue
            limit = max(limit, int(record["limit"]))
            self._entries[record["question_id"]] = record
            self._by_query[record["query_sha256"]] = [
                Candidate(doc_id=item["doc_id"], rank=rank, score=float(item["score"]))
                for rank, item in enumerate(record["candidates"])
            ]
        self.candidate_limit = limit
        self.searches_issued = len(self._entries)
        self.total_search_seconds = round(
            sum(record["search_seconds"] for record in self._entries.values()), 3
        )
        self.lookups = 0

    def has(self, query: str) -> bool:
        return hashlib.sha256(query.encode("utf-8")).hexdigest() in self._by_query

    def __call__(self, query: str, limit: int) -> list[Candidate]:
        key = hashlib.sha256(query.encode("utf-8")).hexdigest()
        assert key in self._by_query, f"query missing from bm25 cache: {query!r}"
        self.lookups += 1
        return self._by_query[key][:limit]

    def close(self) -> None:  # pragma: no cover - parity with the previous retriever
        return None


class BenchProvider:
    """Graph claim provider whose relevance is the frozen matching rule."""

    def __init__(self, inner: GraphClaimProvider, inventory: list[dict]) -> None:
        self._inner = inner
        self._entries = inventory
        self._ck = {
            entry["question_id"]: ids.claim_key_id(*entry["claim_key"].split("::", 1))
            for entry in inventory
        }

    def relevant_claim_keys(self, question: str) -> list[str]:
        return sorted(
            {
                self._ck[entry["question_id"]]
                for entry in self._entries
                if question_matches_claim(question, entry["match_terms"])
            }
        )

    def claim_state(self, claim_key: str):
        return self._inner.claim_state(claim_key)

    def doc_claim_values(self, doc_id: str, claim_keys: list[str]):
        return self._inner.doc_claim_values(doc_id, claim_keys)


# --- gold helpers ----------------------------------------------------------
def _ids(receipt: dict) -> list[str]:
    return [entry["doc_id"] for entry in receipt["final_context"]]


def _seed(qid: str) -> int:
    return int(hashlib.sha256(qid.encode("utf-8")).hexdigest()[:8], 16)


def _hits(ids_list: list[str], wanted: set[str]) -> int:
    return sum(1 for doc in ids_list if doc in wanted)


def _assert_size(name: str, ids_list: list[str], k: int) -> None:
    assert len(ids_list) == k, f"{name}: context has {len(ids_list)} docs, expected exactly {k}"


# --- selection mechanisms (pure, from scripts/controls.py) ------------------
def _rank_and_labels(provider, claim_keys, retrieve, question: str, pool: int):
    ranking = sorted(retrieve(question, pool), key=lambda candidate: candidate.rank)
    states = {key: provider.claim_state(key) for key in claim_keys}
    labels = {
        candidate.doc_id: classify(provider.doc_claim_values(candidate.doc_id, claim_keys), states)
        for candidate in ranking
    }
    return ranking, labels


def _cut_only(ranking, labels, k):
    kept = [c for c in ranking if labels[c.doc_id] != "superseded"]
    return kept[:k]


def _pin_only(ranking, labels, k):
    final = list(ranking[:k])
    present = {c.doc_id for c in final}
    for c in ranking:
        if labels[c.doc_id] != "current" or c.doc_id in present:
            continue
        if len(final) >= k:
            present.discard(final.pop().doc_id)
        final.append(c)
        present.add(c.doc_id)
    assert len(final) <= k
    final.sort(key=lambda c: c.rank)
    return final


def _full(ranking, labels, k):
    kept = [c for c in ranking if labels[c.doc_id] != "superseded"]
    final = kept[:k]
    present = {c.doc_id for c in final}
    for c in kept:
        if labels[c.doc_id] != "current" or c.doc_id in present:
            continue
        if len(final) >= k:
            present.discard(final.pop().doc_id)
        final.append(c)
        present.add(c.doc_id)
    assert len(final) <= k
    if len(final) < k:
        for c in kept:
            if len(final) >= k:
                break
            if c.doc_id in present:
                continue
            final.append(c)
            present.add(c.doc_id)
    final.sort(key=lambda c: c.rank)
    return final


def _random_removal(ranking, baseline, n_remove, k, qid):
    rng = random.Random(_seed(qid))
    baseline_ids = [c.doc_id for c in baseline]
    removed = set(rng.sample(baseline_ids, min(n_remove, len(baseline_ids))))
    final = [c for c in baseline if c.doc_id not in removed]
    present = {c.doc_id for c in final}
    for c in ranking:
        if len(final) >= k:
            break
        if c.doc_id in removed or c.doc_id in present:
            continue
        final.append(c)
        present.add(c.doc_id)
    return final


# --- per-question measurement ----------------------------------------------
def measure_question(provider, retrieve, entry, question, expected_ids) -> dict:
    qid = entry["question_id"]
    old, new = entry["old_doc_id"], entry["new_doc_id"]
    superseded, current = {old}, {new}
    text = question["question"]
    claim_keys = provider.relevant_claim_keys(text)

    baseline = ground(text, "flat", provider=provider, retrieve=retrieve, k=K)
    gate = ground(text, "temporal", provider=provider, retrieve=retrieve, k=K)
    base_ids, gate_ids = _ids(baseline), _ids(gate)
    _assert_size("baseline", base_ids, K)
    _assert_size("gate", gate_ids, K)

    ranking, labels = _rank_and_labels(provider, claim_keys, retrieve, text, max(K * 4, 40))
    n_removed = len([d for d in base_ids if d not in set(gate_ids)])
    random_final = _random_removal(ranking, ranking[:K], n_removed, K, qid)
    random_ids = [c.doc_id for c in random_final]
    _assert_size("random_removal", random_ids, K)

    picks = {
        "baseline": ranking[:K],
        "cut_only": _cut_only(ranking, labels, K),
        "pin_only": _pin_only(ranking, labels, K),
        "full": _full(ranking, labels, K),
    }
    mechanism = {}
    for name, chosen in picks.items():
        ids_list = [c.doc_id for c in chosen]
        _assert_size(f"mechanism:{name}", ids_list, K)
        mechanism[name] = {
            "superseded_in_context": _hits(ids_list, superseded),
            "current_in_context": _hits(ids_list, current),
            "context_size": len(ids_list),
        }

    sweep = {}
    for k in SWEEP:
        flat = ground(text, "flat", provider=provider, retrieve=retrieve, k=k)
        gate_k = ground(text, "temporal", provider=provider, retrieve=retrieve, k=k)
        flat_ids, gate_k_ids = _ids(flat), _ids(gate_k)
        _assert_size(f"sweep:{k}:baseline", flat_ids, k)
        _assert_size(f"sweep:{k}:gate", gate_k_ids, k)
        sweep[str(k)] = {
            "baseline_superseded": _hits(flat_ids, superseded),
            "gate_superseded": _hits(gate_k_ids, superseded),
            "baseline_current": _hits(flat_ids, current),
            "gate_current": _hits(gate_k_ids, current),
        }

    history = ground(text, "history", provider=provider, retrieve=retrieve, k=K)
    history_ids = set(_ids(history))
    history_cuts = {cut["reason"] for cut in history["cut_set"]}
    history_row = {
        "retired_in_context": old in history_ids,
        "retired_cut": "superseded" in history_cuts,
    }

    expected = set(expected_ids)
    expected_row = {
        "expected_count": len(expected),
        "baseline_found": _hits(base_ids, expected),
        "gate_found": _hits(gate_ids, expected),
    }

    return {
        "question_id": qid,
        "composite": bool(entry["composite"]),
        "claim_key": entry["claim_key"],
        "claim_key_id": ids.claim_key_id(*entry["claim_key"].split("::", 1)),
        "baseline": {
            "superseded_in_context": _hits(base_ids, superseded),
            "current_in_context": _hits(base_ids, current),
            "context_size": len(base_ids),
        },
        "gate": {
            "superseded_in_context": _hits(gate_ids, superseded),
            "current_in_context": _hits(gate_ids, current),
            "context_size": len(gate_ids),
        },
        "docs_removed_by_gate": n_removed,
        "random_removal": {
            "n_removed": n_removed,
            "superseded_in_context": _hits(random_ids, superseded),
            "current_in_context": _hits(random_ids, current),
            "context_size": len(random_ids),
        },
        "mechanism": mechanism,
        "sweep": sweep,
        "history": history_row,
        "expected_recall": expected_row,
    }


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"questions": 0}
    base_sup = sum(r["baseline"]["superseded_in_context"] for r in records)
    gate_sup = sum(r["gate"]["superseded_in_context"] for r in records)
    rand_sup = sum(r["random_removal"]["superseded_in_context"] for r in records)
    mechanism = {
        name: {
            "superseded_in_context": sum(
                r["mechanism"][name]["superseded_in_context"] for r in records
            ),
            "current_in_context": sum(
                r["mechanism"][name]["current_in_context"] for r in records
            ),
            "context_size_all_k": all(r["mechanism"][name]["context_size"] == K for r in records),
        }
        for name in MECHANISMS
    }
    sweep = {
        str(k): {
            "baseline_superseded": sum(r["sweep"][str(k)]["baseline_superseded"] for r in records),
            "gate_superseded": sum(r["sweep"][str(k)]["gate_superseded"] for r in records),
        }
        for k in SWEEP
    }
    expected_total = sum(r["expected_recall"]["expected_count"] for r in records)
    expected_base = sum(r["expected_recall"]["baseline_found"] for r in records)
    expected_gate = sum(r["expected_recall"]["gate_found"] for r in records)
    return {
        "questions": n,
        "baseline": {
            "superseded_in_context_total": base_sup,
            "current_in_context_total": sum(r["baseline"]["current_in_context"] for r in records),
        },
        "gate": {
            "superseded_in_context_total": gate_sup,
            "current_in_context_total": sum(r["gate"]["current_in_context"] for r in records),
        },
        "random_removal": {
            "superseded_in_context_total": rand_sup,
            "current_in_context_total": sum(
                r["random_removal"]["current_in_context"] for r in records
            ),
            "docs_removed_total": sum(r["random_removal"]["n_removed"] for r in records),
        },
        "gate_removed_total": sum(r["docs_removed_by_gate"] for r in records),
        "gate_cleans_questions": sum(
            1
            for r in records
            if r["gate"]["superseded_in_context"] < r["baseline"]["superseded_in_context"]
        ),
        "random_cleans_questions": sum(
            1
            for r in records
            if r["random_removal"]["superseded_in_context"] < r["baseline"]["superseded_in_context"]
        ),
        "mechanism": mechanism,
        "sweep": sweep,
        "historical_mode": {
            "retired_in_context_questions": sum(
                1 for r in records if r["history"]["retired_in_context"]
            ),
            "retired_cut_questions": sum(1 for r in records if r["history"]["retired_cut"]),
        },
        "expected_recall": {
            "expected_docs_total": expected_total,
            "baseline_found": expected_base,
            "gate_found": expected_gate,
            "baseline_recall": round(expected_base / expected_total, 4) if expected_total else None,
            "gate_recall": round(expected_gate / expected_total, 4) if expected_total else None,
        },
    }


# --- headline summary -------------------------------------------------------
def headline(agg: dict) -> dict:
    """The headline measures, extracted from an :func:`aggregate` block."""
    return {
        "questions": agg["questions"],
        "baseline_superseded_in_context": agg["baseline"]["superseded_in_context_total"],
        "gate_superseded_in_context": agg["gate"]["superseded_in_context_total"],
        "random_superseded_in_context": agg["random_removal"]["superseded_in_context_total"],
        "baseline_current_in_context": agg["baseline"]["current_in_context_total"],
        "gate_current_in_context": agg["gate"]["current_in_context_total"],
        "random_current_in_context": agg["random_removal"]["current_in_context_total"],
        "gate_cleans_questions": agg["gate_cleans_questions"],
        "random_cleans_questions": agg["random_cleans_questions"],
        "expected_recall": agg["expected_recall"],
    }


def headline_vs_19(all_agg: dict, non_agg: dict, composite_ids: list[str]) -> dict:
    """Non-composite (13) measures next to the all-19 values, plus composite ids."""

    def pair(all_value, non_value) -> dict:
        return {"all_19": all_value, "non_composite_13": non_value}

    def ratio(agg: dict, key: str) -> str:
        recall = agg["expected_recall"]
        return f"{recall[key]}/{recall['expected_docs_total']}"

    return {
        "note": (
            "Measures over the 13 non-composite inventory entries next to the all-19 "
            "values; the composite entries are excluded from the non-composite group."
        ),
        "composite_entries_excluded": len(composite_ids),
        "composite_question_ids": sorted(composite_ids),
        "measures": {
            "superseded_in_context": {
                "baseline": pair(
                    all_agg["baseline"]["superseded_in_context_total"],
                    non_agg["baseline"]["superseded_in_context_total"],
                ),
                "gate": pair(
                    all_agg["gate"]["superseded_in_context_total"],
                    non_agg["gate"]["superseded_in_context_total"],
                ),
            },
            "random_removal_superseded_in_context": pair(
                all_agg["random_removal"]["superseded_in_context_total"],
                non_agg["random_removal"]["superseded_in_context_total"],
            ),
            "current_in_context": {
                "baseline": pair(
                    all_agg["baseline"]["current_in_context_total"],
                    non_agg["baseline"]["current_in_context_total"],
                ),
                "gate": pair(
                    all_agg["gate"]["current_in_context_total"],
                    non_agg["gate"]["current_in_context_total"],
                ),
                "random": pair(
                    all_agg["random_removal"]["current_in_context_total"],
                    non_agg["random_removal"]["current_in_context_total"],
                ),
            },
            "expected_recall": {
                "baseline": pair(
                    ratio(all_agg, "baseline_found"), ratio(non_agg, "baseline_found")
                ),
                "gate": pair(ratio(all_agg, "gate_found"), ratio(non_agg, "gate_found")),
            },
        },
    }


# --- safety envelope --------------------------------------------------------
def safety_envelope(provider, retrieve, questions, conflict_ids, scope_label, sample_seed) -> dict:
    identical = 0
    removed_outside = 0
    pins_outside = 0
    expected_removed_outside = 0
    non_conflict = 0
    size_all_k = True
    interventions = []
    for question in questions:
        qid = question["question_id"]
        text = question["question"]
        flat = ground(text, "flat", provider=provider, retrieve=retrieve, k=K)
        temporal = ground(text, "temporal", provider=provider, retrieve=retrieve, k=K)
        flat_ids, temporal_ids = _ids(flat), _ids(temporal)
        size_all_k = size_all_k and len(flat_ids) == K and len(temporal_ids) == K
        removed = [doc for doc in flat_ids if doc not in set(temporal_ids)]
        added = [doc for doc in temporal_ids if doc not in set(flat_ids)]
        pins = temporal["pinned"]
        is_conflict = qid in conflict_ids
        if not is_conflict:
            non_conflict += 1
            removed_outside += len(removed)
            pins_outside += len(pins)
            if flat["sha256"] == temporal["sha256"]:
                identical += 1
            expected = set(question.get("expected_doc_ids", []))
            expected_removed_outside += _hits(removed, expected)
        if removed or added or pins:
            interventions.append(
                {
                    "question_id": qid,
                    "question_type": question["question_type"],
                    "conflict": is_conflict,
                    "claim_keys": temporal["claim_keys"],
                    "removed": removed,
                    "added": added,
                    "pinned": pins,
                }
            )
    return {
        "scope": scope_label,
        "sample_seed": sample_seed,
        "question_ids": [question["question_id"] for question in questions],
        "questions_total": len(questions),
        "non_conflict_questions": non_conflict,
        "contexts_byte_identical": identical,
        "contexts_byte_identical_all_non_conflict": identical == non_conflict,
        "size_all_k": size_all_k,
        "expected_documents_removed_outside_conflicts": expected_removed_outside,
        "documents_removed_outside_conflicts": removed_outside,
        "pins_outside_conflicts": pins_outside,
        "interventions": interventions,
    }


# --- io ---------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # pragma: no cover - no git in some environments
        return "not_run"


def print_table(title: str, records: list[dict], keys: list[str]) -> None:
    print(f"\n{title}")
    print("question_id  " + "  ".join(f"{k:>22}" for k in keys))
    for r in records:
        cells = []
        for key in keys:
            if key == "baseline_sup":
                cells.append(str(r["baseline"]["superseded_in_context"]))
            elif key == "gate_sup":
                cells.append(str(r["gate"]["superseded_in_context"]))
            elif key == "baseline_cur":
                cells.append(str(r["baseline"]["current_in_context"]))
            elif key == "gate_cur":
                cells.append(str(r["gate"]["current_in_context"]))
            elif key == "random_sup":
                cells.append(str(r["random_removal"]["superseded_in_context"]))
            elif key == "removed":
                cells.append(str(r["docs_removed_by_gate"]))
            elif key == "hist_retired":
                cells.append(str(r["history"]["retired_in_context"]))
            elif key == "exp_base":
                cells.append(f"{r['expected_recall']['baseline_found']}/{r['expected_recall']['expected_count']}")
            elif key == "exp_gate":
                cells.append(f"{r['expected_recall']['gate_found']}/{r['expected_recall']['expected_count']}")
        print(f"{r['question_id']:<12}  " + "  ".join(f"{c:>22}" for c in cells))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the benchmark controls.")
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--tenant", default=TENANT)
    parser.add_argument(
        "--envelope-sample", type=int, default=ENVELOPE_SAMPLE,
        help="0 = all questions (not the default)",
    )
    parser.add_argument("--seed", type=int, default=ENVELOPE_SEED)
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))["questions"]
    questions = [
        json.loads(line)
        for line in args.questions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {q["question_id"]: q for q in questions}
    conflict_ids = {entry["question_id"] for entry in inventory}
    composite_ids = [entry["question_id"] for entry in inventory if entry["composite"]]
    assert all(qid in by_id for qid in conflict_ids), (
        "inventory question missing from questions.jsonl"
    )

    index_sha = sha256_file(args.index)
    retrieve = CachedRetriever(args.cache, index_sha)

    if args.envelope_sample:
        wanted = sample_ids([q["question_id"] for q in questions], args.seed, args.envelope_sample)
        envelope_questions = [by_id[qid] for qid in wanted]
        scope_label = f"sample of {len(envelope_questions)}, not all {len(questions)}"
    else:
        envelope_questions = questions
        scope_label = f"all {len(questions)} questions"

    missing = [
        q["question_id"] for q in envelope_questions if not retrieve.has(q["question"])
    ] + [qid for qid in conflict_ids if not retrieve.has(by_id[qid]["question"])]
    assert not missing, f"questions missing from bm25 cache: {sorted(missing)[:10]}"

    db = build_client()
    graph = select_graph(args.tenant, db=db)
    inner = GraphClaimProvider(graph)
    provider = BenchProvider(inner, inventory)
    claims_in_graph = int(graph.query("MATCH (ck:ClaimKey) RETURN count(ck)").result_set[0][0])

    records = [
        measure_question(provider, retrieve, entry, by_id[entry["question_id"]],
                         by_id[entry["question_id"]].get("expected_doc_ids", []))
        for entry in inventory
    ]
    records.sort(key=lambda r: r["question_id"])
    non_composite = [r for r in records if not r["composite"]]
    all_agg = aggregate(records)
    non_agg = aggregate(non_composite)

    envelope = safety_envelope(
        provider, retrieve, envelope_questions, conflict_ids, scope_label, args.seed
    )

    matching = json.loads(MATCHING.read_text(encoding="utf-8"))["results"]
    corpus_index = json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))
    info_nf = matching["info_not_found"]
    assert info_nf["matched_any_count"] == 0, "expected 0 info_not_found matches"

    report = {
        "generated_by": "scripts/benchmark_controls.py",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": "none (deterministic)",
        "note": (
            "No model is in the loop. Retrieval is FTS5 bm25 top_k=10 served from a frozen "
            "per-question candidate cache (LIMIT 40); exactly 10 documents in every context "
            "(asserted); top-5/top-10/top-20 are prefixes of the same cache list. "
            "Question->claim matching uses the frozen rule in evidence/benchmark/matching.json."
        ),
        "conditions": {
            "retrieval": "sqlite FTS5 bm25 via var/benchmark/bm25_cache.jsonl (LIMIT 40)",
            "top_k": K,
            "candidate_limit": retrieve.candidate_limit,
            "exactly_k_documents": True,
            "tenant": args.tenant,
            "dedupe": "index already holds the first copy of the 4 duplicate doc ids",
        },
        "corpus_size_indexed": corpus_index["index"]["documents"],
        "index_file": args.index.as_posix(),
        "index_sha256": index_sha,
        "search": {
            "cache_file": args.cache.as_posix(),
            "candidate_limit": retrieve.candidate_limit,
            "cache_entries": retrieve.searches_issued,
            "queries_issued": retrieve.searches_issued,
            "total_search_seconds": retrieve.total_search_seconds,
            "queries_issued_by_controls": 0,
            "cache_lookups_by_controls": None,  # filled after the run
        },
        "git_commit": git_commit(),
        "claims_in_graph": claims_in_graph,
        "gate_can_only_act_on": f"{claims_in_graph} claims held by tenant '{args.tenant}'",
        "all_19": all_agg,
        "non_composite_13": non_agg,
        "headline": {
            "description": (
                "Headline measures for all 19 conflict entries and for the 13 "
                "non-composite entries next to the all-19 numbers; the 6 composite "
                "entries are excluded from the non-composite group."
            ),
            "all_19": headline(all_agg),
            "non_composite_13": headline(non_agg),
            "composite_excluded": len(records) - len(non_composite),
        },
        "non_composite_13_vs_19": headline_vs_19(all_agg, non_agg, composite_ids),
        "envelope_seed": args.seed,
        "per_question": records,
        "envelope_scope": scope_label,
        "safety_envelope": envelope,
        "info_not_found": {
            "from_matching_json": True,
            "total": info_nf["total"],
            "matched_any_count": info_nf["matched_any_count"],
            "matched_any_by_id": info_nf["matched_any_by_id"],
            "answer_quality_result": False,
            "note": (
                "lexical matching only; no model is in the loop, so this is not an "
                "answer-quality result"
            ),
        },
        "expected_recall_note": (
            "Expected-document recall drops by design under the gate: each conflict "
            "question's expected_doc_ids contains the retired document, which the gate cuts."
        ),
        "surprises": {
            "retired_doc_absent_from_baseline_top10": sorted(
                r["question_id"] for r in records if r["baseline"]["superseded_in_context"] == 0
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report["search"]["cache_lookups_by_controls"] = retrieve.lookups
    args.out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    # --- headline tables ---------------------------------------------------
    keys = ["baseline_sup", "gate_sup", "baseline_cur", "gate_cur", "random_sup", "removed"]
    print_table("(a/b) conflict questions: superseded/current in context (k=10)", records, keys)
    print("\n(mechanism split, all 19):", json.dumps(report["all_19"]["mechanism"], sort_keys=True))
    print("(mechanism split, non-composite 13):",
          json.dumps(report["non_composite_13"]["mechanism"], sort_keys=True))
    print("\n(top-k sweep, all 19):", json.dumps(report["all_19"]["sweep"], sort_keys=True))
    print(
        "(top-k sweep, non-composite 13):",
        json.dumps(report["non_composite_13"]["sweep"], sort_keys=True),
    )
    print(
        "\n(historical mode all 19):",
        json.dumps(report["all_19"]["historical_mode"], sort_keys=True),
    )
    print(
        "(expected recall all 19):",
        json.dumps(report["all_19"]["expected_recall"], sort_keys=True),
    )
    print(
        "(expected recall non-composite 13):",
        json.dumps(report["non_composite_13"]["expected_recall"], sort_keys=True),
    )
    print("\n(headline totals all 19):", json.dumps(
        {
            "baseline_superseded": report["all_19"]["baseline"]["superseded_in_context_total"],
            "gate_superseded": report["all_19"]["gate"]["superseded_in_context_total"],
            "random_superseded": report["all_19"]["random_removal"]["superseded_in_context_total"],
            "gate_cleans": report["all_19"]["gate_cleans_questions"],
            "random_cleans": report["all_19"]["random_cleans_questions"],
        }, sort_keys=True))
    print(f"\n(search): {json.dumps(report['search'], sort_keys=True)}")
    print(f"(safety envelope, {scope_label}):", json.dumps(
        {k: v for k, v in envelope.items() if k not in ("interventions", "question_ids")},
        sort_keys=True))
    print(f"(envelope scope label): {scope_label}")
    print(f"(envelope seed): {args.seed}")
    print(f"(interventions): {len(envelope['interventions'])} questions act on a claim ->")
    for row in envelope["interventions"]:
        print("   ", json.dumps(row, sort_keys=True))
    print(f"\n(claims in graph): {claims_in_graph}")
    print(f"(info_not_found matched any claim): {info_nf['matched_any_count']}/{info_nf['total']}")
    print(f"(surprise: retired doc NOT in baseline top-10): "
          f"{report['surprises']['retired_doc_absent_from_baseline_top10']}")
    print(f"\nWrote {args.out}")

    retrieve.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
