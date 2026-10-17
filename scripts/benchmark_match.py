"""Freeze the question-to-claim matching rule, then run it over all 500 questions.

``--freeze`` writes the rule and inventory sha256 hashes into
``evidence/benchmark/matching.json`` under ``frozen`` and never overwrites an
existing frozen block (a changed rule is appended to ``rule_changes`` with
before/after numbers instead). ``--run`` verifies the frozen hashes still hold,
then scores every question in ``var/benchmark/questions.jsonl`` against the 19
inventory claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from canister_evaluation.benchmark_matching import question_matches_claim

RULE_FILE = Path("packages/evaluation/src/canister_evaluation/benchmark_matching.py")
INVENTORY = Path("research/conflicts_revised.json")
QUESTIONS = Path("var/benchmark/questions.jsonl")
OUT = Path("evidence/benchmark/matching.json")

RULE_DESCRIPTION = (
    "a question matches a claim iff it contains every entity term and at least "
    "half of the attribute terms (case-insensitive, token based)"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_out() -> dict[str, Any]:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {}


def save_out(data: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
                   encoding="utf-8")


def freeze() -> dict[str, Any]:
    data = load_out()
    rule_sha = sha256_file(RULE_FILE)
    inventory_sha = sha256_file(INVENTORY)
    if "frozen" in data:
        existing = data["frozen"]
        if existing.get("rule_sha256") != rule_sha:
            data.setdefault("rule_changes", []).append(
                {
                    "changed_at_utc": now(),
                    "rule_sha256_before": existing.get("rule_sha256"),
                    "rule_sha256_after": rule_sha,
                    "note": "rule file changed after the original freeze",
                }
            )
        if existing.get("inventory_sha256") != inventory_sha:
            data["inventory_changes"] = data.get("inventory_changes", [])
            data["inventory_changes"].append(
                {
                    "changed_at_utc": now(),
                    "inventory_sha256_before": existing.get("inventory_sha256"),
                    "inventory_sha256_after": inventory_sha,
                }
            )
        print("frozen already present; original hashes preserved")
    else:
        data["frozen"] = {
            "rule_file": RULE_FILE.as_posix(),
            "rule_function": "question_matches_claim",
            "rule_sha256": rule_sha,
            "inventory_file": INVENTORY.as_posix(),
            "inventory_sha256": inventory_sha,
            "description": RULE_DESCRIPTION,
            "frozen_at_utc": now(),
        }
        print(f"frozen written: rule_sha256={rule_sha[:16]} inventory_sha256={inventory_sha[:16]}")
    save_out(data)
    return data


def run() -> int:
    data = load_out()
    if "frozen" not in data:
        raise SystemExit("no frozen block: run --freeze first")
    frozen = data["frozen"]
    rule_sha = sha256_file(RULE_FILE)
    if rule_sha != frozen["rule_sha256"]:
        raise SystemExit(
            "rule file changed since freeze; record the change with --freeze before --run"
        )

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    claims = inventory["questions"]
    questions = [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    conflict_ids = {claim["question_id"] for claim in claims}
    not_found_ids = {
        q["question_id"] for q in questions if q["question_type"] == "info_not_found"
    }

    matched: dict[str, list[str]] = {}
    for question in questions:
        matched[question["question_id"]] = [
            claim["question_id"]
            for claim in claims
            if question_matches_claim(question["question"], claim["match_terms"])
        ]

    conflict_matched_own = sorted(qid for qid in conflict_ids if qid in matched[qid])
    conflict_not_matched_own = sorted(qid for qid in conflict_ids if qid not in matched[qid])
    conflict_matched_other = {
        qid: [c for c in matched[qid] if c != qid]
        for qid in sorted(conflict_ids)
        if len(matched[qid]) > 1
    }

    info_not_found_matched = sorted(
        qid for qid in not_found_ids if matched.get(qid)
    )

    other_questions = [
        q
        for q in questions
        if q["question_id"] not in conflict_ids and q["question_type"] != "info_not_found"
    ]
    other_matched = [
        {
            "question_id": q["question_id"],
            "question_type": q["question_type"],
            "matched_claims": matched[q["question_id"]],
        }
        for q in other_questions
        if matched[q["question_id"]]
    ]

    results = {
        "generated_at_utc": now(),
        "questions_file": QUESTIONS.as_posix(),
        "claims_count": len(claims),
        "conflict_questions": {
            "definition": "the 19 inventory entries (qst_0413 excluded)",
            "expected_by_construction": True,
            "matched_own_claim": conflict_matched_own,
            "not_matched_own_claim": conflict_not_matched_own,
            "matched_other_claims": conflict_matched_other,
        },
        "info_not_found": {
            "total": len(not_found_ids),
            "matched_any_count": len(info_not_found_matched),
            "matched_any_by_id": info_not_found_matched,
        },
        "other_questions_matched": other_matched,
        "totals": {
            "questions_total": len(questions),
            "conflict_inventory": len(conflict_ids),
            "info_not_found": len(not_found_ids),
            "remaining_other": len(other_questions),
            "remaining_other_matched": len(other_matched),
            "conflict_matched_own": len(conflict_matched_own),
            "conflict_not_matched_own": len(conflict_not_matched_own),
            "info_not_found_matched": len(info_not_found_matched),
        },
    }
    data["results"] = results
    data.setdefault("rule_changes", [])
    save_out(data)

    print(json.dumps(results["totals"], indent=2))
    print(f"conflict matched own claim: {len(conflict_matched_own)}/19")
    print(f"conflict NOT matched own claim: {conflict_not_matched_own}")
    print(f"conflict also matching other claims: {json.dumps(conflict_matched_other)}")
    print(
        f"info_not_found matched any claim: "
        f"{len(info_not_found_matched)}/{len(not_found_ids)} {info_not_found_matched}"
    )
    print(f"other questions matched ({len(other_matched)}):")
    for row in other_matched:
        print(f"  {row['question_id']} [{row['question_type']}] -> {row['matched_claims']}")
    print(f"Wrote {OUT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    if args.run:
        return run()
    if not args.freeze:
        parser.error("choose --freeze and/or --run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
