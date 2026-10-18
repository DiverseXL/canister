"""FalkorDB client configuration tests. No network, no database.

``build_client`` is exercised against a fake ``FalkorDB`` so nothing ever
connects, and the error paths prove a configured password can never surface in
a :class:`GraphUnavailable` message.
"""

from __future__ import annotations

import pytest
from canister_graph import GraphUnavailable, build_client
from canister_graph import client as client_module

ENV_NAMES = (
    "FALKORDB_HOST",
    "FALKORDB_PORT",
    "FALKORDB_USERNAME",
    "FALKORDB_PASSWORD",
    "FALKORDB_URL",
)


@pytest.fixture
def fake_falkordb(monkeypatch):
    """Replace the client class with a recorder that never opens a socket."""
    recorded: dict = {}

    class FakeFalkorDB:
        def __init__(self, **kwargs) -> None:
            recorded["kwargs"] = kwargs

        @classmethod
        def from_url(cls, url: str, **kwargs):
            recorded["url"] = url
            return cls()

    monkeypatch.setattr(client_module, "FalkorDB", FakeFalkorDB)
    return recorded


def test_build_client_reads_connection_env(fake_falkordb, monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "graph.example")
    monkeypatch.setenv("FALKORDB_PORT", "7000")
    monkeypatch.setenv("FALKORDB_USERNAME", "alice")
    monkeypatch.setenv("FALKORDB_PASSWORD", "s3cret-pass")
    monkeypatch.delenv("FALKORDB_URL", raising=False)

    build_client()

    assert fake_falkordb["kwargs"] == {
        "host": "graph.example",
        "port": 7000,
        "username": "alice",
        "password": "s3cret-pass",
    }


def test_build_client_defaults_without_env(fake_falkordb, monkeypatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    build_client()

    kwargs = fake_falkordb["kwargs"]
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 6379
    assert kwargs["username"] is None
    assert kwargs["password"] is None


def test_explicit_arguments_override_env(fake_falkordb, monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "env-host")
    monkeypatch.setenv("FALKORDB_PORT", "1111")
    monkeypatch.setenv("FALKORDB_USERNAME", "env-user")
    monkeypatch.setenv("FALKORDB_PASSWORD", "env-pass")
    monkeypatch.delenv("FALKORDB_URL", raising=False)

    build_client(host="arg-host", port=2222, username="arg-user", password="arg-pass")

    assert fake_falkordb["kwargs"] == {
        "host": "arg-host",
        "port": 2222,
        "username": "arg-user",
        "password": "arg-pass",
    }


def test_build_client_never_enables_tls(fake_falkordb, monkeypatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    build_client()

    assert "ssl" not in fake_falkordb["kwargs"], "the connection must stay plaintext"


def test_construction_error_never_leaks_password(monkeypatch) -> None:
    secret = "hunter2-construction-secret"
    monkeypatch.setenv("FALKORDB_PASSWORD", secret)
    monkeypatch.delenv("FALKORDB_URL", raising=False)

    class Boom:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError(f"auth failed for password {secret} on host")

    monkeypatch.setattr(client_module, "FalkorDB", Boom)

    with pytest.raises(GraphUnavailable) as excinfo:
        build_client()

    assert secret not in str(excinfo.value)
    assert client_module.REDACTED in str(excinfo.value)


def test_url_error_never_leaks_password(monkeypatch) -> None:
    secret = "url-embedded-secret"
    url = f"rediss://default:{secret}@graph.example:6380"
    monkeypatch.setenv("FALKORDB_URL", url)

    class Boom:
        @classmethod
        def from_url(cls, url: str, **kwargs):
            raise RuntimeError(f"cannot open {url}")

    monkeypatch.setattr(client_module, "FalkorDB", Boom)

    with pytest.raises(GraphUnavailable) as excinfo:
        build_client()

    assert secret not in str(excinfo.value)
    assert client_module.REDACTED in str(excinfo.value)


def test_ping_redacts_env_password(monkeypatch) -> None:
    secret = "ping-secret"
    monkeypatch.setenv("FALKORDB_PASSWORD", secret)

    class Connection:
        def ping(self) -> None:
            raise RuntimeError(f"WRONGPASS {secret}")

    class DB:
        connection = Connection()

    with pytest.raises(GraphUnavailable) as excinfo:
        client_module.ping(DB())

    assert secret not in str(excinfo.value)


def test_redact_replaces_every_secret() -> None:
    text = "user=alice password=topsecret url=redis://:topsecret@host"
    redacted = client_module.redact(text, "topsecret", "alice")
    assert "topsecret" not in redacted
    assert "alice" not in redacted
    assert client_module.REDACTED in redacted
