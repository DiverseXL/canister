"""Seed the "bench" tenant from the conflict inventory (not the extractor).

Every node is written through the existing :class:`GraphWriter` (``ingest`` /
``write_artifact`` / ``write_assertion``) and canonized with ``canonize_all``;
no state is ever set by hand.

For each inventory entry we write:

* the old document asserting ``old_value`` (span ``old_span``), and
* the new document asserting ``new_value`` (span ``new_span``) with the
  ``supersession_sentence`` as its stance marker (``stance="supersede"``,
  ``explicit_supersession=True``).

The new document never asserts ``old_value`` even when
``new_doc_mentions_old_value`` is true. The ClaimKey identity is the
inventory's ``claim_key`` (``entity::attribute``), split into the two halves the
writer hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from canister_graph import (
    ArtifactInput,
    AssertionInput,
    GraphWriter,
    IngestDocument,
    build_client,
    drop_graph,
    ids,
    require_local_or_allow_remote,
    select_graph,
)

INVENTORY = Path("research/conflicts_revised.json")
ZIP = Path("var/benchmark/all_documents.zip")
TENANT = "bench"


def norm_value(value: str) -> str:
    return " ".join(value.strip().split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_doc_texts(zf: zipfile.ZipFile, doc_ids: set[str]) -> dict[str, list[tuple[str, str]]]:
    by_doc: dict[str, list[str]] = {}
    for name in zf.namelist():
        if not name.lower().endswith(".txt"):
            continue
        stem = name.rsplit("/", 1)[-1]
        doc_id = stem.split("__", 1)[0]
        if doc_id in doc_ids:
            by_doc.setdefault(doc_id, []).append(name)
    texts: dict[str, list[tuple[str, str]]] = {}
    for doc_id, members in by_doc.items():
        texts[doc_id] = [
            (name, zf.read(name).decode("utf-8", "replace")) for name in sorted(members)
        ]
    return texts


def find_span(
    doc_id: str, span: str, texts: dict[str, list[tuple[str, str]]]
) -> tuple[str, str, int, int]:
    for name, text in texts.get(doc_id, []):
        start = text.find(span)
        if start >= 0:
            return name, text, start, start + len(span)
    raise SystemExit(f"span not found for {doc_id!r}: {span[:60]!r}")


def title_of(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def build_documents(
    inventory: dict, texts: dict[str, list[tuple[str, str]]]
) -> list[IngestDocument]:
    documents: list[IngestDocument] = []
    for entry in inventory["questions"]:
        entity_key, attribute_key = entry["claim_key"].split("::", 1)
        attribute_label = entry["attribute"]
        supersession = entry.get("supersession_sentence", "")
        explicit = bool(supersession and supersession != "UNSURE")

        for role in ("old", "new"):
            doc_id = entry[f"{role}_doc_id"]
            span = entry[f"{role}_span"]
            name, text, start, end = find_span(doc_id, span, texts)
            artifact = ArtifactInput(
                doc_id=doc_id,
                title=title_of(text),
                source=name.split("/", 1)[0],
                published_at=None,
                content_sha256=sha256_text(text),
                path=name,
            )
            if role == "old":
                assertion = AssertionInput(
                    doc_id=doc_id,
                    entity=entity_key,
                    attribute=attribute_key,
                    attribute_label=attribute_label,
                    value_type="text",
                    value_raw=entry["old_value"],
                    value_norm=norm_value(entry["old_value"]),
                    stance="assert",
                    explicit_supersession=False,
                    prior_value=None,
                    span_start=start,
                    span_end=end,
                    quote=span,
                    structured=False,
                    source=artifact.source,
                    published_at=None,
                )
            else:
                assertion = AssertionInput(
                    doc_id=doc_id,
                    entity=entity_key,
                    attribute=attribute_key,
                    attribute_label=attribute_label,
                    value_type="text",
                    value_raw=entry["new_value"],
                    value_norm=norm_value(entry["new_value"]),
                    stance="supersede",
                    explicit_supersession=explicit,
                    prior_value=norm_value(entry["old_value"]),
                    span_start=start,
                    span_end=end,
                    quote=supersession or span,
                    structured=False,
                    source=artifact.source,
                    published_at=None,
                )
            documents.append(IngestDocument(artifact=artifact, assertions=(assertion,)))
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the bench tenant from the inventory.")
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--zip", type=Path, default=ZIP)
    parser.add_argument("--tenant", default=TENANT)
    parser.add_argument(
        "--reset", action="store_true", help="drop the bench graph first (bench tenant only)"
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow dropping and writing the bench graph on a non-local FALKORDB_HOST (dangerous)",
    )
    args = parser.parse_args()

    require_local_or_allow_remote(args.allow_remote, action="seed the bench tenant")

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    needed = set()
    for entry in inventory["questions"]:
        needed.add(entry["old_doc_id"])
        needed.add(entry["new_doc_id"])

    with zipfile.ZipFile(args.zip) as zf:
        texts = load_doc_texts(zf, needed)
    documents = build_documents(inventory, texts)

    db = build_client()
    if args.reset:
        drop_graph(db, args.tenant)
    graph = select_graph(args.tenant, db=db)
    writer = GraphWriter(graph)
    writer.ensure_schema()

    # Run 1
    before1 = writer.count_nodes()
    writer.ingest(documents)
    after_ingest1 = writer.count_nodes()
    writer.canonize_all()
    nodes1 = writer.count_nodes()
    rels1 = writer.count_relationships()
    print(f"run 1: nodes_before={before1} nodes_after_ingest={after_ingest1} "
          f"nodes_after_canon={nodes1} relationships={rels1}")

    # Run 2 (idempotency): must create 0 new nodes
    before2 = writer.count_nodes()
    writer.ingest(documents)
    after_ingest2 = writer.count_nodes()
    decisions2 = writer.canonize_all()
    nodes2 = writer.count_nodes()
    rels2 = writer.count_relationships()
    print(f"run 2: nodes_before={before2} nodes_after_ingest={after_ingest2} "
          f"nodes_after_canon={nodes2} relationships={rels2} new_nodes={nodes2 - nodes1}")

    by_id = {
        ids.claim_key_id(*entry["claim_key"].split("::", 1)): entry
        for entry in inventory["questions"]
    }
    rows = []
    for decision in decisions2:
        entry = by_id.get(decision.claim_key)
        if entry is None:
            continue
        expected = entry["expected_state"]
        expected_value = norm_value(entry["new_value"])
        matched = decision.decision == expected and decision.selected_value == expected_value
        rows.append(
            {
                "question_id": entry["question_id"],
                "expected_state": expected,
                "state": decision.decision,
                "selected_value": decision.selected_value,
                "priority": decision.priority,
                "reason": decision.reason,
                "match": matched,
            }
        )
    rows.sort(key=lambda r: r["question_id"])

    print()
    header = ("question_id", "expected_state", "canon_state", "selected_value",
              "priority", "reason", "match")
    print("{:<12}{:<15}{:<12}{:<52}{:<9}{:<22}{}".format(*header))
    for row in rows:
        value = (row["selected_value"] or "")[:50]
        print("{:<12}{:<15}{:<12}{:<52}{:<9}{:<22}{}".format(
            row["question_id"],
            row["expected_state"],
            row["state"],
            value,
            str(row["priority"]),
            row["reason"],
            "yes" if row["match"] else "no",
        ))

    disagreements = [r for r in rows if not r["match"]]
    print()
    if disagreements:
        print(f"DISAGREEMENTS ({len(disagreements)}):")
        for row in disagreements:
            print(json.dumps(row, ensure_ascii=False))
        print("STOP: canonizer disagrees with expected_state; not changing the canonizer.")
    else:
        print(f"no disagreements ({len(rows)} entries, all match expected_state)")

    modules = db.connection.module_list()
    graph_module = next((m for m in modules if m.get("name") == "graph"), {})
    server = db.connection.info("server")
    print()
    print(f"falkordb server: module graph ver={graph_module.get('ver')} "
          f"redis_version={server.get('redis_version')}")
    mem = "unavailable"
    try:
        mem = db.connection.execute_command("GRAPH.MEMORY", "USAGE", args.tenant)
    except Exception as exc:  # pragma: no cover - depends on server
        mem = f"unavailable ({exc})"
    print(f"graph size: nodes={writer.count_nodes()} relationships="
          f"{writer.count_relationships()} memory_usage={mem}")

    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
