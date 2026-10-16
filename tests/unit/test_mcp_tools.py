"""MCP tool schema and fail-closed tests. No network, no database."""

from __future__ import annotations

import asyncio

import pytest
from canister_graph import GraphUnavailable
from canister_mcp.server import build_server
from canister_mcp.tools import canister_claim, canister_ground


def _tools_by_name() -> dict:
    tools = asyncio.run(build_server().list_tools())
    return {tool.name: tool for tool in tools}


def test_tool_schemas_without_network() -> None:
    tools = _tools_by_name()
    assert set(tools) == {"canister_ground", "canister_claim"}

    ground = tools["canister_ground"].input_schema
    assert set(ground["properties"]) == {"question", "mode", "tenant_id", "k"}
    assert ground["required"] == ["question"]
    assert ground["properties"]["mode"]["default"] == "current"
    assert tools["canister_ground"].description

    claim = tools["canister_claim"].input_schema
    assert set(claim["properties"]) == {"claim_key", "tenant_id"}


def test_ground_fails_closed_when_graph_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", "1")
    with pytest.raises(GraphUnavailable):
        canister_ground("What is the current starter plan price for Acme Corp?")


def test_claim_fails_closed_when_graph_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", "1")
    with pytest.raises(GraphUnavailable):
        canister_claim(tenant_id="demo")


def test_ground_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        canister_ground("hi", mode="nonsense")
