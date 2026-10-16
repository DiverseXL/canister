"""Deterministic ids are stable, normalized and collision-resistant."""

from canister_graph import ids


def test_entity_id_is_deterministic_and_normalized() -> None:
    assert ids.entity_id("Acme Corp") == ids.entity_id("  acme   corp ")
    assert ids.entity_id("Acme Corp") != ids.entity_id("Globex")


def test_artifact_and_claim_key_ids() -> None:
    assert ids.artifact_id("doc-0001") == ids.artifact_id("doc-0001")
    a = ids.claim_key_id("Acme", "starter_price")
    b = ids.claim_key_id("Acme", "pro_price")
    assert a != b


def test_assertion_id_depends_on_span() -> None:
    base = ids.assertion_id("art", "ck", "0.08", 0, 10)
    assert base != ids.assertion_id("art", "ck", "0.08", 0, 11)
    assert base != ids.assertion_id("art", "ck", "0.06", 0, 10)
    assert base == ids.assertion_id("art", "ck", "0.08", 0, 10)


def test_canon_event_id_is_order_insensitive_but_content_sensitive() -> None:
    a = ids.canon_event_id("ck", "CANON", "p", ["x", "y"])
    b = ids.canon_event_id("ck", "CANON", "p", ["y", "x"])
    c = ids.canon_event_id("ck", "CANON", "p", ["y", "z"])
    assert a == b
    assert a != c
    assert a != ids.canon_event_id("ck", "CONTESTED", None, ["x", "y"])


def test_id_prefixes_are_distinct() -> None:
    prefixes = {
        ids.entity_id("x").split("_")[0],
        ids.claim_key_id("x", "y").split("_")[0],
        ids.proposition_id("ck", "v").split("_")[0],
        ids.artifact_id("d").split("_")[0],
        ids.assertion_id("a", "c", "v", 0, 1).split("_")[0],
    }
    assert len(prefixes) == 5
