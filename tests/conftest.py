"""Shared test fixtures. Corpus and index are built into a temp directory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def corpus_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from corpus.generator import build

    out = tmp_path_factory.mktemp("corpus")
    build(out)
    return out


@pytest.fixture(scope="session")
def gold(corpus_dir: Path) -> dict:
    return json.loads((corpus_dir / "gold.json").read_text(encoding="utf-8"))
