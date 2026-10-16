"""Controlled vocabulary shared by the corpus generator and the extractor.

This is an ontology (which entities and attributes exist), not gold data. The
extractor still has to recover the value, stance and evidence span from the raw
document text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ENTITIES: tuple[str, ...] = (
    "Acme Corp",
    "Globex",
    "Initech",
    "Umbrella Corp",
    "Soylent",
    "Hooli",
    "Vehement Capital",
    "Stark Industries",
    "Wayne Enterprises",
    "Wonka Industries",
    "Cyberdyne Systems",
    "Tyrell Corp",
)

PEOPLE: tuple[str, ...] = (
    "Dana Cole",
    "Ravi Menon",
    "Lena Ortiz",
    "Marcus Webb",
    "Priya Nair",
    "Tom Falk",
    "Grace Kim",
    "Omar Haddad",
    "Nina Petrov",
    "Sam Ortiz",
)


@dataclass(frozen=True)
class Attribute:
    key: str
    label: str
    aliases: tuple[str, ...]
    value_type: str


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("starter_price", "starter plan price", ("starter price", "starter plan"), "money"),
    Attribute("pro_price", "pro plan price", ("pro price", "pro plan"), "money"),
    Attribute("refund_window", "refund window", ("refund period",), "duration_days"),
    Attribute("launch_date", "launch date", ("general availability date", "ga date"), "date"),
    Attribute("integration_owner", "integration owner", ("integration lead",), "person"),
    Attribute(
        "support_sla",
        "support response SLA",
        ("support SLA", "response SLA"),
        "duration_hours",
    ),
)

ATTRIBUTE_BY_KEY: dict[str, Attribute] = {a.key: a for a in ATTRIBUTES}


def _attribute_index() -> list[tuple[str, Attribute]]:
    pairs: list[tuple[str, Attribute]] = []
    for attr in ATTRIBUTES:
        for label in (attr.label, *attr.aliases):
            pairs.append((label, attr))
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return pairs


_ATTRIBUTE_INDEX = _attribute_index()


def find_entities(text: str) -> list[str]:
    """Return known entity names mentioned in ``text``, in order of appearance."""
    matches: list[tuple[int, str]] = []
    for name in ENTITIES:
        m = re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text, re.IGNORECASE)
        if m:
            matches.append((m.start(), name))
    matches.sort(key=lambda item: item[0])
    return [name for _, name in matches]


def find_attributes(text: str) -> list[Attribute]:
    """Return known attributes referenced in ``text`` (longest alias wins)."""
    found: dict[str, Attribute] = {}
    for label, attr in _ATTRIBUTE_INDEX:
        if attr.key in found:
            continue
        if re.search(rf"(?<![\w]){re.escape(label)}(?![\w])", text, re.IGNORECASE):
            found[attr.key] = attr
    return list(found.values())


def attribute_for_label(label: str) -> Attribute | None:
    """Resolve an attribute label/alias (e.g. from a structured field) to an Attribute."""
    needle = label.strip().lower()
    for candidate, attr in _ATTRIBUTE_INDEX:
        if candidate.lower() == needle:
            return attr
    return None
