"""Task 9 stress set.

20 documents that express supersession with paraphrases the deterministic
extractor is *not* designed to parse ("we have since retired the old figure",
"as of last quarter this changed"). The extractor is deliberately NOT tuned to
them: the point is to measure honestly where it fails.

Each stress document:
  line 1 records the *old* value with an ordinary assertion,
  line 2 states the new value inside a paraphrase.

A human reads line 2 as "the old value is retired". The extractor sees two plain
assertions, has no supersession marker and no change grammar, so canonization
correctly refuses to invent an order -> CONTESTED. For a few documents the new
value is only expressed loosely ("a fortnight"), so the extractor recovers
nothing at all.

Run: ``uv run python corpus/stress.py``
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from canister_extraction import (
    ATTRIBUTE_BY_KEY,
    ATTRIBUTES,
    ENTITIES,
    PEOPLE,
    normalize_value,
)
from canister_extraction.extract import extract
from canister_graph import GraphWriter, build_client, drop_graph, ids, select_graph
from canister_graph.models import ArtifactInput, AssertionInput

SEED = 2025
N = 20

MONEY = ["$0.04", "$0.05", "$0.08", "$0.10", "$0.12", "$0.20", "$0.25", "$0.40"]
DAYS = ["7 days", "14 days", "21 days", "30 days", "45 days", "60 days"]
HOURS = ["4 hours", "8 hours", "12 hours", "24 hours", "48 hours"]
DATES = ["2025-06-01", "2025-07-01", "2025-09-01", "2025-11-01", "2026-01-01"]

PARAPHRASES = [
    "As of last quarter this changed; the {label} for {entity} is now {new}.",
    "We have since retired the old figure, so the {label} for {entity} sits at {new} today.",
    "{entity} moved its {label} to {new} going forward.",
    "The team is now working from {new} for the {label} at {entity}.",
    "Latest word: the {label} for {entity} now reads {new}.",
    "{entity} shifted its {label} to {new} this quarter.",
    "Take {new} as the {label} for {entity} from here on.",
    "{entity} has a new {label}: {new}.",
    "Earlier numbers are stale; the {label} for {entity} is {new}.",
    "The {label} for {entity} was reset and now reads {new}.",
    "For planning, use {new} as the {label} for {entity}.",
    "{entity} refreshed its {label}; it is {new} now.",
    "The {label} for {entity} has moved and now stands at {new}.",
    "{entity} reports {new} for its {label} as of this filing.",
    "Updated figure: the {label} for {entity} is {new}.",
    "Going forward the {label} for {entity} should be read as {new}.",
    "{entity} quietly bumped its {label} to {new}.",
    "Per the new memo, the {label} for {entity} is {new}.",
    "{entity} now frames its {label} as {new}.",
    "Count on {new} for the {label} for {entity}.",
]

LOOSE = {
    "money": ["roughly eight cents", "about half a dollar"],
    "duration_days": ["a fortnight", "about three weeks"],
    "duration_hours": ["half a day", "a couple of hours"],
    "date": ["early next spring", "sometime in Q3"],
    "person": ["Jordan Vale", "Rhea Storm"],
}

POOLS = {"money": MONEY, "duration_days": DAYS, "duration_hours": HOURS, "date": DATES}


def _pick(attr, index: int) -> str:
    if attr.value_type == "person":
        return PEOPLE[index % len(PEOPLE)]
    return POOLS[attr.value_type][index % len(POOLS[attr.value_type])]


def _distinct(attr, old_raw: str, index: int) -> str:
    for offset in range(1, 8):
        candidate = _pick(attr, index + offset)
        if normalize_value(candidate, attr.value_type) != normalize_value(old_raw, attr.value_type):
            return candidate
    raise RuntimeError("could not find a distinct value")


def build(out_dir: Path) -> dict:
    rng = random.Random(SEED)
    combos = [(entity, attr) for entity in ENTITIES for attr in ATTRIBUTES]
    rng.shuffle(combos)

    cases = []
    for index in range(N):
        entity, attr = combos[index]
        old_raw = _pick(attr, index * 2 + 1)
        new_canonical = _distinct(attr, old_raw, index * 2 + 1)
        loose = index >= N - 6
        surface = (
            LOOSE[attr.value_type][index % len(LOOSE[attr.value_type])] if loose else new_canonical
        )
        phrase = PARAPHRASES[index % len(PARAPHRASES)]
        doc_id = f"stress-{index + 1:04d}"
        body = (
            f"Previous guidance recorded the {attr.label} for {entity} at {old_raw}.\n\n"
            f"{phrase.format(entity=entity, label=attr.label, new=surface)}"
        )
        text = (
            "---\n"
            f"doc_id: {doc_id}\n"
            f"title: {entity} {attr.label} note\n"
            "source: stress-set\n"
            f"published_at: 2026-0{(index % 9) + 1}-15\n"
            "---\n\n"
            f"# {entity} {attr.label} note\n\n"
            f"{body}\n"
        )
        cases.append(
            {
                "doc_id": doc_id,
                "entity": entity,
                "attribute": attr.key,
                "attribute_label": attr.label,
                "value_type": attr.value_type,
                "old_raw": old_raw,
                "old_norm": normalize_value(old_raw, attr.value_type),
                "new_canonical": new_canonical,
                "new_norm": normalize_value(new_canonical, attr.value_type),
                "surface_new": surface,
                "loose": loose,
                "path": f"stress/{doc_id}.md",
                "text": text,
            }
        )

    (out_dir / "stress").mkdir(parents=True, exist_ok=True)
    for case in cases:
        (out_dir / case["path"]).write_text(case["text"], encoding="utf-8")

    return {"seed": SEED, "documents": cases}


def _ingest_document(case: dict):
    artifact = ArtifactInput(
        doc_id=case["doc_id"],
        title=f"{case['entity']} {case['attribute_label']} note",
        source="stress-set",
        published_at=None,
        content_sha256="",
        path=case["path"],
    )
    assertions = []
    for claim in extract(case["text"], doc_id=case["doc_id"]):
        attribute = ATTRIBUTE_BY_KEY[claim.attribute]
        assertions.append(
            AssertionInput(
                doc_id=case["doc_id"],
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
                source="stress-set",
                published_at=None,
            )
        )
    return artifact, assertions


def run(corpus_dir: Path, tenant: str) -> dict:
    built = build(corpus_dir)

    db = build_client()
    drop_graph(db, tenant)
    writer = GraphWriter(select_graph(tenant, db=db))
    writer.ensure_schema()

    extraction = {}
    for case in built["documents"]:
        artifact, assertions = _ingest_document(case)
        writer.write_artifact(artifact)
        for assertion in assertions:
            writer.write_assertion(assertion)
        extraction[case["doc_id"]] = assertions

    decisions = {decision.claim_key: decision for decision in writer.canonize_all()}
    drop_graph(db, tenant)

    results = []
    for case in built["documents"]:
        claim_key = ids.claim_key_id(case["entity"], case["attribute"])
        decision = decisions[claim_key]
        assertions = extraction[case["doc_id"]]
        value_recovered = any(assertion.value_norm == case["new_norm"] for assertion in assertions)
        explicit_flagged = any(assertion.explicit_supersession for assertion in assertions)
        selected = decision.selected_value
        if decision.decision == "CANON" and selected == case["new_norm"]:
            outcome = "CANON_current"
        elif decision.decision == "CANON":
            outcome = "CANON_stale"
        else:
            outcome = decision.decision
        results.append(
            {
                "doc_id": case["doc_id"],
                "entity": case["entity"],
                "attribute": case["attribute"],
                "old_value": case["old_norm"],
                "expected_current": case["new_norm"],
                "surface_new": case["surface_new"],
                "loose_surface": case["loose"],
                "assertions": len(assertions),
                "value_recovered": value_recovered,
                "explicit_flagged": explicit_flagged,
                "decision": decision.decision,
                "selected_value": selected,
                "outcome": outcome,
                "current_correct": outcome == "CANON_current",
            }
        )

    def rate(count: int) -> float:
        return round(count / len(results), 4)

    values_recovered = sum(1 for r in results if r["value_recovered"])
    explicit = sum(1 for r in results if r["explicit_flagged"])
    correct = sum(1 for r in results if r["current_correct"])
    outcomes: dict[str, int] = {}
    for result in results:
        outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1

    return {
        "generated_by": "corpus/stress.py",
        "metrics_class": "deterministic",
        "note": (
            "Synthetic paraphrased supersession. The extractor was NOT tuned to "
            "these documents; misses below are reported as-is."
        ),
        "corpus": {"documents": len(results), "seed": built["seed"]},
        "results": results,
        "summary": {
            "documents": len(results),
            "values_recovered": values_recovered,
            "value_recall": rate(values_recovered),
            "supersession_flagged": explicit,
            "supersession_recall": rate(explicit),
            "current_correct": correct,
            "current_recall": rate(correct),
            "outcomes": outcomes,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Task 9 stress set.")
    parser.add_argument("--corpus", type=Path, default=Path("corpus/out"))
    parser.add_argument("--tenant", default="canister_stress")
    parser.add_argument("--out", type=Path, default=Path("corpus/out/stress.json"))
    args = parser.parse_args()

    report = run(args.corpus, args.tenant)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    summary = report["summary"]
    print(
        f"documents={summary['documents']} "
        f"value_recall={summary['value_recall']} "
        f"supersession_recall={summary['supersession_recall']} "
        f"current_recall={summary['current_recall']}"
    )
    print(f"outcomes={summary['outcomes']}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
