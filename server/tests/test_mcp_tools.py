import asyncio
from types import SimpleNamespace

import pytest

from src.services.chat.mcp_tools import MCPToolClient


def test_mcp_server_requires_explicit_tool_allowlist(monkeypatch):
    monkeypatch.setenv(
        "MCP_SERVERS_JSON",
        '[{"name":"docs","url":"https://mcp.example.test","allowed_tools":[]}]',
    )

    client = MCPToolClient()

    assert client._server_configs[0]["allowed_tools"] == []


def test_mcp_server_rejects_missing_allowlist(monkeypatch):
    monkeypatch.setenv(
        "MCP_SERVERS_JSON",
        '[{"name":"docs","url":"https://mcp.example.test"}]',
    )

    with pytest.raises(ValueError, match="explicit allowed_tools"):
        MCPToolClient()


def test_mcp_authentication_uses_configured_bearer_token(monkeypatch):
    client = MCPToolClient(server_configs=[{
        "name": "docs",
        "url": "https://mcp.example.test",
        "allowed_tools": ["search"],
        "token_env": "DOCS_MCP_TOKEN",
    }])

    monkeypatch.setenv("DOCS_MCP_TOKEN", "test-token")
    assert client._headers(client._server_configs[0]) == {
        "Authorization": "Bearer test-token"
    }

    monkeypatch.delenv("DOCS_MCP_TOKEN")
    with pytest.raises(RuntimeError, match="DOCS_MCP_TOKEN"):
        client._headers(client._server_configs[0])


def test_only_allowlisted_remote_tools_are_exposed(monkeypatch):
    client = MCPToolClient(server_configs=[{
        "name": "docs",
        "url": "https://mcp.example.test",
        "allowed_tools": ["search"],
    }])

    async def fake_request(config, operation, tool_name=None, arguments=None):
        assert operation == "list_tools"
        return SimpleNamespace(tools=[
            SimpleNamespace(name="search", description="Search", inputSchema={"type": "object"}),
            SimpleNamespace(name="delete_all", description="Unsafe", inputSchema={}),
        ])

    monkeypatch.setattr(client, "_request", fake_request)
    tools = asyncio.run(client.list_allowed_tools())

    assert [tool.qualified_name for tool in tools] == ["mcp_docs_search"]


def test_calling_non_allowlisted_tool_is_denied():
    client = MCPToolClient(server_configs=[{
        "name": "docs",
        "url": "https://mcp.example.test",
        "allowed_tools": ["search"],
    }])

    with pytest.raises(PermissionError, match="not allowed"):
        asyncio.run(client.call_tool("docs", "delete_all", {}))
