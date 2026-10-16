"""Canister deterministic claim extraction."""

from canister_extraction.extract import ExtractedClaim, extract
from canister_extraction.normalize import normalize_value
from canister_extraction.vocab import (
    ATTRIBUTE_BY_KEY,
    ATTRIBUTES,
    ENTITIES,
    PEOPLE,
    Attribute,
    find_attributes,
    find_entities,
)

__all__ = [
    "ExtractedClaim",
    "extract",
    "normalize_value",
    "ENTITIES",
    "ATTRIBUTES",
    "ATTRIBUTE_BY_KEY",
    "PEOPLE",
    "Attribute",
    "find_entities",
    "find_attributes",
]
