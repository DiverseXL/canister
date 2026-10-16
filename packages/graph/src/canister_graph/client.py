"""FalkorDB client helpers. One graph per tenant.

Every entry point here fails closed: if FalkorDB cannot be reached the caller
gets a :class:`GraphUnavailable` and must not fall back to plain retrieval.
"""

from __future__ import annotations

import os

from falkordb import FalkorDB


class GraphUnavailable(RuntimeError):
    """Raised when FalkorDB cannot be reached or a graph query fails."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


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
        raise GraphUnavailable(f"could not build FalkorDB client: {exc}") from exc


def ping(db: FalkorDB) -> None:
    """Raise :class:`GraphUnavailable` unless the server answers PING."""
    try:
        db.connection.ping()
    except Exception as exc:
        raise GraphUnavailable(f"FalkorDB unreachable: {exc}") from exc


def select_graph(tenant_id: str, *, db: FalkorDB | None = None):
    """Return the tenant graph, failing closed when the server is unreachable."""
    db = db or build_client()
    ping(db)
    try:
        return db.select_graph(tenant_id)
    except Exception as exc:  # pragma: no cover - defensive
        raise GraphUnavailable(f"could not select graph {tenant_id!r}: {exc}") from exc


def list_graphs(db: FalkorDB) -> list[str]:
    try:
        return list(db.list_graphs())
    except Exception as exc:
        raise GraphUnavailable(f"could not list graphs: {exc}") from exc


def drop_graph(db: FalkorDB, name: str) -> bool:
    """Drop a graph if it exists. Returns True when a graph was dropped."""
    try:
        if name in db.list_graphs():
            db.select_graph(name).delete()
            return True
    except Exception as exc:
        raise GraphUnavailable(f"could not drop graph {name!r}: {exc}") from exc
    return False
