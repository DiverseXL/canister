"""Store and replay ground() receipts on disk.

Receipts are plain JSON so ``GET /receipt/{id}`` needs no graph: it returns the
exact bytes-verifiable receipt that ``POST /ground`` produced.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def receipts_dir() -> Path:
    return Path(os.environ.get("CANISTER_RECEIPTS_DIR", "var/receipts"))


def valid_id(receipt_id: str) -> bool:
    return bool(_ID_RE.match(receipt_id))


def save(receipt_id: str, receipt: dict) -> Path:
    if not valid_id(receipt_id):
        raise ValueError(f"invalid receipt id: {receipt_id!r}")
    directory = receipts_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{receipt_id}.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load(receipt_id: str) -> dict | None:
    if not valid_id(receipt_id):
        return None
    path = receipts_dir() / f"{receipt_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
