"""Seeded, reproducible synthetic company corpus generator.

Produces 200 documents with 18 planted conflicts (including one 9-vs-1
majority-adversarial case), 2 CONTESTED cases and 10 unanswerable questions.
Gold labels are written to ``corpus/out/gold.json``.

Run: ``uv run python corpus/generator.py``
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from canister_extraction import (
    ATTRIBUTE_BY_KEY,
    ATTRIBUTES,
    ENTITIES,
    PEOPLE,
    Attribute,
    normalize_value,
)

SEED = 1337
N_DOCS = 200
N_CONFLICT = 18
N_CONTESTED = 2
N_ANSWERABLE_KEYS = 40
N_UNANSWERABLE = 10

# The majority-adversarial case: many documents assert one value, a single later
# document supersedes it. Kept explicit so the example is fixed and legible.
MAJORITY_ENTITY = "Acme Corp"
MAJORITY_ATTRIBUTE = "starter_price"
MAJORITY_OLD = "$0.15"
MAJORITY_NEW = "$0.07"
MAJORITY_DOCS = 9

MONEY = [0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.40, 0.50, 0.75, 1.00, 1.20, 2.50]
DAYS = [7, 14, 21, 30, 45, 60, 90]
HOURS = [4, 8, 12, 24, 48, 72]
DATES = [
    "2025-03-01",
    "2025-04-01",
    "2025-05-15",
    "2025-06-01",
    "2025-07-01",
    "2025-08-15",
    "2025-09-01",
    "2025-10-01",
    "2025-11-01",
    "2025-12-01",
]
SOURCES = ["internal-wiki", "release-notes", "sales-ops", "support-portal", "finance-shared"]
MADE_UP_ENTITIES = ["Northwind Traders", "Contoso", "Fabrikam", "Litware"]
CONFLICT_TEMPLATES = ["explicit", "change_temporal", "change_semantic"]

EPOCH = date(2025, 1, 6)


def iso(index: int) -> str:
    return (EPOCH + timedelta(days=index * 7)).isoformat()


def raw_value(attr: Attribute, rng: random.Random) -> str:
    if attr.value_type == "money":
        return f"${rng.choice(MONEY):.2f}"
    if attr.value_type == "duration_days":
        return f"{rng.choice(DAYS)} days"
    if attr.value_type == "duration_hours":
        return f"{rng.choice(HOURS)} hours"
    if attr.value_type == "date":
        return rng.choice(DATES)
    if attr.value_type == "person":
        return rng.choice(PEOPLE)
    raise ValueError(attr.value_type)


def different_value(attr: Attribute, old_raw: str, rng: random.Random) -> str:
    for _ in range(100):
        candidate = raw_value(attr, rng)
        if normalize_value(candidate, attr.value_type) != normalize_value(old_raw, attr.value_type):
            return candidate
    raise RuntimeError("could not perturb value")


@dataclass
class PlantedClaim:
    entity: str
    attribute: str
    attribute_label: str
    value_raw: str
    value_norm: str
    stance: str
    explicit_supersession: bool
    prior_value: str | None
    structured: bool


@dataclass
class Document:
    doc_id: str
    title: str
    source: str
    published_at: str
    path: str
    gold_label: str
    claims: list[PlantedClaim] = field(default_factory=list)
    body: str = field(default="", repr=False, compare=False)


FILLER = (
    "This record was filed by the platform team and is retained for internal "
    "reference only. It contains no other changes."
)


def structured_block(entity: str, label: str, value_raw: str) -> str:
    return f"Recorded fields\n- entity: {entity}\n- attribute: {label}\n- value: {value_raw}"


def prose(entity: str, label: str, value_raw: str, kind: str, prior_raw: str | None) -> str:
    if kind == "assert_plain":
        return f"The {label} for {entity} is {value_raw}."
    if kind == "assert_poss":
        return f"{entity}'s {label} is {value_raw}."
    if kind == "corroborate":
        return f"Our records confirm that {entity}'s {label} remains {value_raw}."
    if kind == "change_temporal":
        return f"{entity} changed its {label} from {prior_raw} to {value_raw}."
    if kind == "change_semantic":
        return f"{entity} moved its {label} from {prior_raw} to {value_raw}."
    if kind == "explicit":
        return (
            "This notice supersedes all previous guidance: "
            f"{entity}'s {label} is now {value_raw}, previously {prior_raw}."
        )
    if kind == "contested_plain":
        return f"{entity} lists its {label} as {value_raw}."
    raise ValueError(kind)


def render_document(doc: Document) -> str:
    front = (
        "---\n"
        f"doc_id: {doc.doc_id}\n"
        f"title: {doc.title}\n"
        f"source: {doc.source}\n"
        f"published_at: {doc.published_at}\n"
        "---\n\n"
        f"# {doc.title}\n\n"
    )
    return front + doc.body + "\n"


def build(out_dir: Path) -> dict:
    rng = random.Random(SEED)

    majority_attr = ATTRIBUTE_BY_KEY[MAJORITY_ATTRIBUTE]
    combos = [
        (e, a)
        for e in ENTITIES
        for a in ATTRIBUTES
        if not (e == MAJORITY_ENTITY and a.key == MAJORITY_ATTRIBUTE)
    ]
    rng.shuffle(combos)
    key_combos = [(MAJORITY_ENTITY, majority_attr)] + combos[: N_ANSWERABLE_KEYS - 1]
    unused = combos[N_ANSWERABLE_KEYS - 1 :]

    kinds = ["majority"] + ["conflict"] * (N_CONFLICT - 1) + ["contested"] * N_CONTESTED
    kinds += ["stable"] * (N_ANSWERABLE_KEYS - len(kinds))
    assert len(kinds) == N_ANSWERABLE_KEYS

    docs: list[Document] = []
    claim_keys: list[dict] = []
    state = {"doc": 0, "date": 0, "stable": 0}

    def add_doc(
        entity: str,
        attr: Attribute,
        value_raw: str,
        *,
        date_idx: int,
        label: str,
        kind: str,
        prior_raw: str | None = None,
        explicit: bool = False,
        structured: bool = False,
        stance: str = "assert",
    ) -> None:
        state["doc"] += 1
        doc_id = f"doc-{state['doc']:04d}"
        parts: list[str] = []
        if structured:
            parts.append(structured_block(entity, attr.label, value_raw))
        parts.append(prose(entity, attr.label, value_raw, kind, prior_raw))
        parts.append(FILLER)
        body = "\n\n".join(parts)
        value_norm = normalize_value(value_raw, attr.value_type)
        prior_norm = normalize_value(prior_raw, attr.value_type) if prior_raw else None
        effective_stance = "assert" if structured else stance
        docs.append(
            Document(
                doc_id=doc_id,
                title=f"{entity} {attr.label} update",
                source=SOURCES[state["doc"] % len(SOURCES)],
                published_at=iso(date_idx),
                path=f"documents/{doc_id}.md",
                gold_label=label,
                claims=[
                    PlantedClaim(
                        entity=entity,
                        attribute=attr.key,
                        attribute_label=attr.label,
                        value_raw=value_raw,
                        value_norm=value_norm,
                        stance=effective_stance,
                        explicit_supersession=False if structured else explicit,
                        prior_value=None if structured else prior_norm,
                        structured=structured,
                    )
                ],
                body=body,
            )
        )

    for (entity, attr), kind in zip(key_combos, kinds, strict=True):
        base = raw_value(attr, rng)
        if kind == "majority":
            base = MAJORITY_OLD
            for _ in range(MAJORITY_DOCS):
                style = rng.random()
                add_doc(
                    entity,
                    attr,
                    base,
                    date_idx=state["date"],
                    label="superseded",
                    kind="assert_poss" if style < 0.5 else "assert_plain",
                    structured=style > 0.7,
                )
                state["date"] += 1
            new = MAJORITY_NEW
            add_doc(
                entity,
                attr,
                new,
                date_idx=state["date"] + 30,
                label="current",
                kind="explicit",
                prior_raw=base,
                explicit=True,
                stance="supersede",
            )
            state["date"] += 2
            claim_keys.append(_claim(entity, attr, kind, base, new))
        elif kind == "conflict":
            template = CONFLICT_TEMPLATES[len(claim_keys) % len(CONFLICT_TEMPLATES)]
            for _ in range(2):
                add_doc(
                    entity,
                    attr,
                    base,
                    date_idx=state["date"],
                    label="superseded",
                    kind="assert_plain",
                    structured=rng.random() > 0.5,
                )
                state["date"] += 1
            new = different_value(attr, base, rng)
            add_doc(
                entity,
                attr,
                new,
                date_idx=state["date"] + 10,
                label="current",
                kind=template,
                prior_raw=base,
                explicit=(template == "explicit"),
                stance="supersede",
            )
            state["date"] += 2
            claim_keys.append(_claim(entity, attr, kind, base, new))
        elif kind == "contested":
            other = different_value(attr, base, rng)
            same_date = state["date"] + 5
            add_doc(
                entity,
                attr,
                base,
                date_idx=same_date,
                label="contested",
                kind="contested_plain",
            )
            add_doc(
                entity,
                attr,
                other,
                date_idx=same_date,
                label="contested",
                kind="contested_plain",
            )
            state["date"] += 7
            claim_keys.append(_claim(entity, attr, kind, None, None))
        else:  # stable
            count = 7 if state["stable"] < 15 else 6
            state["stable"] += 1
            for _ in range(count):
                style = rng.random()
                if style < 0.34:
                    add_doc(
                        entity,
                        attr,
                        base,
                        date_idx=state["date"],
                        label="current",
                        kind="assert_plain",
                        structured=True,
                    )
                elif style < 0.67:
                    add_doc(
                        entity,
                        attr,
                        base,
                        date_idx=state["date"],
                        label="current",
                        kind="assert_poss",
                    )
                else:
                    add_doc(
                        entity,
                        attr,
                        base,
                        date_idx=state["date"],
                        label="current",
                        kind="corroborate",
                        structured=True,
                    )
                state["date"] += 1
            claim_keys.append(_claim(entity, attr, kind, base, base))

    assert len(docs) == N_DOCS, f"generated {len(docs)} docs, expected {N_DOCS}"

    questions = _build_questions(claim_keys, unused, rng)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "documents").mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (out_dir / doc.path).write_text(render_document(doc), encoding="utf-8")

    gold = {
        "seed": SEED,
        "counts": {
            "documents": N_DOCS,
            "claim_keys": N_ANSWERABLE_KEYS,
            "conflicts": N_CONFLICT,
            "contested": N_CONTESTED,
            "unanswerable_questions": N_UNANSWERABLE,
            "questions": len(questions),
        },
        "claim_keys": claim_keys,
        "questions": questions,
        "documents": [{k: v for k, v in asdict(doc).items() if k != "body"} for doc in docs],
    }
    (out_dir / "gold.json").write_text(json.dumps(gold, indent=2, sort_keys=True), encoding="utf-8")
    return gold


def _claim(
    entity: str, attr: Attribute, kind: str, old_raw: str | None, new_raw: str | None
) -> dict:
    return {
        "entity": entity,
        "attribute": attr.key,
        "attribute_label": attr.label,
        "kind": kind,
        "old_value": normalize_value(old_raw, attr.value_type) if old_raw else None,
        "current_value": normalize_value(new_raw, attr.value_type) if new_raw else None,
    }


def _build_questions(claim_keys: list[dict], unused: list[tuple], rng: random.Random) -> list[dict]:
    questions: list[dict] = []
    for claim in claim_keys:
        expected = "CONTESTED" if claim["kind"] == "contested" else claim["current_value"]
        questions.append(
            {
                "qid": f"q-{len(questions) + 1:03d}",
                "question": (
                    f"What is the current {claim['attribute_label']} for {claim['entity']}?"
                ),
                "entity": claim["entity"],
                "attribute": claim["attribute"],
                "expected": expected,
                "kind": "contested" if claim["kind"] == "contested" else "answerable",
            }
        )
    rng.shuffle(unused)
    sampled = unused[: N_UNANSWERABLE - len(MADE_UP_ENTITIES)]
    sampled += [(name, rng.choice(list(ATTRIBUTES))) for name in MADE_UP_ENTITIES]
    for entity, attr in sampled:
        questions.append(
            {
                "qid": f"q-{len(questions) + 1:03d}",
                "question": f"What is the current {attr.label} for {entity}?",
                "entity": entity,
                "attribute": attr.key,
                "expected": "UNKNOWN",
                "kind": "unanswerable",
            }
        )
    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Canister corpus.")
    parser.add_argument("--out", type=Path, default=Path("corpus/out"))
    args = parser.parse_args()
    gold = build(args.out)
    print(
        "Generated {documents} documents, {conflicts} conflicts, "
        "{contested} contested, {questions} questions -> {out}".format(
            out=args.out, **gold["counts"]
        )
    )


if __name__ == "__main__":
    main()
