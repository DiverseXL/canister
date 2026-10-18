"""Safety guards for scripts that restart Docker or write to FalkorDB.

Restarting the local container and dropping graphs only make sense against a
local server. Destructive scripts call :func:`require_local_or_allow_remote`
before doing any work: a non-local ``FALKORDB_HOST`` aborts unless the operator
passes ``--allow-remote`` explicitly.
"""

from __future__ import annotations

import os

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def resolve_host() -> str:
    """The host a client would use, given the current environment."""
    return os.environ.get("FALKORDB_HOST") or "127.0.0.1"


def is_local_host(host: str | None = None) -> bool:
    """True when *host* (or ``FALKORDB_HOST``) points at this machine."""
    resolved = (host if host is not None else resolve_host()).strip().lower()
    return resolved in LOCAL_HOSTS


def require_local_or_allow_remote(allow_remote: bool, *, action: str) -> None:
    """Abort *action* against a non-local FalkorDB host.

    The only override is ``allow_remote`` (the ``--allow-remote`` flag).
    """
    if allow_remote or is_local_host():
        return
    host = resolve_host()
    raise SystemExit(
        f"refusing to {action}: FALKORDB_HOST={host!r} is not local "
        f"({', '.join(sorted(LOCAL_HOSTS))}). Pass --allow-remote to override."
    )
