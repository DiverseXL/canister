"""MCP server exposing Canister as tools over stdio.

Tools:
  canister_ground  -- ground a question against a tenant's temporal claim graph
  canister_claim   -- look up a claim key's state, or list every claim key

Both fail closed: if FalkorDB is unreachable the tool call errors. The server
never falls back to plain retrieval.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from canister_mcp import tools

GROUND_DESCRIPTION = (
    "Ground a question against the tenant's temporal claim graph. mode is one of "
    "'current' (default), 'historical' or 'temporal'. Returns a receipt with the "
    "final context, a sha256 and the Cypher query identifiers used. Fails closed "
    "if FalkorDB is unreachable."
)
CLAIM_DESCRIPTION = (
    "Return one claim key's state (CANON / CONTESTED / UNKNOWN) or, when no "
    "claim_key is given, list every claim key for the tenant."
)


def build_server() -> MCPServer:
    server = MCPServer("canister", version="0.1.0")

    @server.tool(name="canister_ground", description=GROUND_DESCRIPTION)
    def _ground(
        question: str,
        mode: str = "current",
        tenant_id: str | None = None,
        k: int = 10,
    ) -> dict:
        return tools.canister_ground(question, mode, tenant_id, k)

    @server.tool(name="canister_claim", description=CLAIM_DESCRIPTION)
    def _claim(claim_key: str | None = None, tenant_id: str | None = None) -> dict:
        return tools.canister_claim(claim_key, tenant_id)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
