"""Deterministic value normalization.

Planted values (corpus) and recovered values (extractor) are normalized with the
same functions so they can be compared exactly.
"""

from __future__ import annotations

import re

_MONEY_RE = re.compile(r"\$\s?(?P<num>\d[\d,]*(?:\.\d+)?)")
_INT_RE = re.compile(r"(?P<num>\d[\d,]*)")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PERSON_RE = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+")


def _strip_commas(raw: str) -> str:
    return raw.replace(",", "")


def normalize_value(raw: str, value_type: str) -> str:
    """Normalize a raw value string for a given attribute value type."""
    raw = raw.strip()
    if value_type == "money":
        m = _MONEY_RE.search(raw)
        if not m:
            raise ValueError(f"not a money value: {raw!r}")
        return f"{float(_strip_commas(m.group('num'))):.2f}"
    if value_type == "duration_days":
        m = _INT_RE.search(raw)
        if not m:
            raise ValueError(f"not a duration value: {raw!r}")
        return f"{int(_strip_commas(m.group('num')))}d"
    if value_type == "duration_hours":
        m = _INT_RE.search(raw)
        if not m:
            raise ValueError(f"not a duration value: {raw!r}")
        return f"{int(_strip_commas(m.group('num')))}h"
    if value_type == "date":
        m = _DATE_RE.search(raw)
        if not m:
            raise ValueError(f"not a date value: {raw!r}")
        return m.group(0)
    if value_type == "person":
        m = _PERSON_RE.search(raw)
        if not m:
            raise ValueError(f"not a person value: {raw!r}")
        return m.group(0).strip().lower()
    raise ValueError(f"unknown value type: {value_type!r}")
