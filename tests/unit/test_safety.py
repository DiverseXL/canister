"""Remote-host safety guard tests. No network, no database."""

from __future__ import annotations

import pytest
from canister_graph.safety import (
    is_local_host,
    require_local_or_allow_remote,
    resolve_host,
)


def test_resolve_host_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("FALKORDB_HOST", raising=False)
    assert resolve_host() == "127.0.0.1"


def test_resolve_host_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "graph.example")
    assert resolve_host() == "graph.example"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "LOCALHOST", " 127.0.0.1 "])
def test_is_local_host_accepts_loopback(host: str) -> None:
    assert is_local_host(host)


@pytest.mark.parametrize("host", ["graph.example", "10.0.0.5", "0.0.0.0", "redis-host"])
def test_is_local_host_rejects_remote(host: str) -> None:
    assert not is_local_host(host)


def test_guard_allows_local_host(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    require_local_or_allow_remote(False, action="do a thing")


def test_guard_allows_default_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("FALKORDB_HOST", raising=False)
    require_local_or_allow_remote(False, action="do a thing")


def test_guard_refuses_remote_without_flag(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "graph.example")
    with pytest.raises(SystemExit) as excinfo:
        require_local_or_allow_remote(False, action="drop graphs")
    assert "graph.example" in str(excinfo.value)
    assert "--allow-remote" in str(excinfo.value)


def test_guard_allows_remote_with_flag(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "graph.example")
    require_local_or_allow_remote(True, action="drop graphs")
