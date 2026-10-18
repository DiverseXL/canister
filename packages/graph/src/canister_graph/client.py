"""FalkorDB client helpers. One graph per tenant.

Every entry point here fails closed: if FalkorDB cannot be reached the caller
gets a :class:`GraphUnavailable` and must not fall back to plain retrieval.

Connection settings come from optional environment variables: ``FALKORDB_HOST``
(default ``127.0.0.1``), ``FALKORDB_PORT`` (default ``6379``),
``FALKORDB_USERNAME`` and ``FALKORDB_PASSWORD`` (default: no auth). The
connection is plaintext -- TLS is never enabled. A configured password is
scrubbed from every error message before it is raised, so it can never reach a
log or an HTTP response.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from falkordb import FalkorDB

REDACTED = "***"


class GraphUnavailable(RuntimeError):
    """Raised when FalkorDB cannot be reached or a graph query fails."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def _url_password(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlsplit(url).password
    except ValueError:  # pragma: no cover - malformed URLs are rare
        return None


def redact(message: object, *secrets: str | None) -> str:
    """Return *message* with every occurrence of a secret replaced by ``***``."""
    text = str(message)
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


def _env_secrets() -> list[str]:
    """Passwords currently configured via the environment (never logged)."""
    secrets: list[str] = []
    password = os.environ.get("FALKORDB_PASSWORD")
    if password:
        secrets.append(password)
    url_password = _url_password(os.environ.get("FALKORDB_URL"))
    if url_password:
        secrets.append(url_password)
    return secrets


def build_client(
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    url: str | None = None,
) -> FalkorDB:
    """Construct (but do not prove reachable) a FalkorDB client."""
    host = host or _env("FALKORDB_HOST", "127.0.0.1")
    port = port or int(_env("FALKORDB_PORT", "6379") or "6379")
    username = username or _env("FALKORDB_USERNAME")
    password = password or _env("FALKORDB_PASSWORD")
    url = url or _env("FALKORDB_URL")
    try:
        if url:
            return FalkorDB.from_url(url)
        return FalkorDB(host=host, port=port, username=username, password=password)
    except Exception as exc:  # pragma: no cover - construction rarely fails
        raise GraphUnavailable(
            redact(
                f"could not build FalkorDB client: {exc}",
                password,
                _url_password(url),
            )
        ) from exc


def ping(db: FalkorDB) -> None:
    """Raise :class:`GraphUnavailable` unless the server answers PING."""
    try:
        db.connection.ping()
    except Exception as exc:
        raise GraphUnavailable(
            redact(f"FalkorDB unreachable: {exc}", *_env_secrets())
        ) from exc


def select_graph(tenant_id: str, *, db: FalkorDB | None = None):
    """Return the tenant graph, failing closed when the server is unreachable."""
    db = db or build_client()
    ping(db)
    try:
        return db.select_graph(tenant_id)
    except Exception as exc:  # pragma: no cover - defensive
        raise GraphUnavailable(
            redact(f"could not select graph {tenant_id!r}: {exc}", *_env_secrets())
        ) from exc


def list_graphs(db: FalkorDB) -> list[str]:
    try:
        return list(db.list_graphs())
    except Exception as exc:
        raise GraphUnavailable(
            redact(f"could not list graphs: {exc}", *_env_secrets())
        ) from exc


def drop_graph(db: FalkorDB, name: str) -> bool:
    """Drop a graph if it exists. Returns True when a graph was dropped."""
    try:
        if name in db.list_graphs():
            db.select_graph(name).delete()
            return True
    except Exception as exc:
        raise GraphUnavailable(
            redact(f"could not drop graph {name!r}: {exc}", *_env_secrets())
        ) from exc
    return False
