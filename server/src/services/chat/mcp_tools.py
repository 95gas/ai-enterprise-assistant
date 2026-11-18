import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urlparse


@dataclass(frozen=True)
class MCPTool:
    server_name: str
    name: str
    description: str
    input_schema: Dict[str, Any]

    @property
    def qualified_name(self) -> str:
        name = f"mcp_{self.server_name}_{self.name}".lower()
        return re.sub(r"[^a-z0-9_-]+", "_", name)


class MCPToolClient:
    """Calls only explicitly allowlisted tools on configured HTTP MCP servers."""

    def __init__(self, server_configs=None, timeout_seconds: float = 30) -> None:
        self._server_configs = (
            server_configs if server_configs is not None else self._load_server_configs()
        )
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _load_server_configs() -> List[Dict[str, Any]]:
        raw_config = os.getenv("MCP_SERVERS_JSON", "[]")
        try:
            servers = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            raise ValueError("MCP_SERVERS_JSON must be valid JSON.") from exc
        if not isinstance(servers, list):
            raise ValueError("MCP_SERVERS_JSON must contain a list of MCP servers.")

        validated = []
        seen_names = set()
        for server in servers:
            if not isinstance(server, dict):
                raise ValueError("Each MCP server configuration must be an object.")
            name, url, allowed_tools = (
                server.get("name"),
                server.get("url"),
                server.get("allowed_tools"),
            )
            parsed_url = urlparse(url or "")
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]+", name)
                or name in seen_names
            ):
                raise ValueError("MCP server names must be unique alphanumeric identifiers.")
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError(f"MCP server '{name}' must use an HTTP(S) URL.")
            if not isinstance(allowed_tools, list) or not all(
                isinstance(tool, str) and tool for tool in allowed_tools
            ):
                raise ValueError(
                    f"MCP server '{name}' must define an explicit allowed_tools list."
                )
            seen_names.add(name)
            validated.append(server)
        return validated

    def _headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        token_env = config.get("token_env")
        if not token_env:
            return {}
        token = os.getenv(token_env)
        if not token:
            raise RuntimeError(
                f"MCP authentication token environment variable '{token_env}' is not set."
            )
        return {"Authorization": f"Bearer {token}"}

    async def list_allowed_tools(self) -> List[MCPTool]:
        tools = []
        for config in self._server_configs:
            if not config["allowed_tools"]:
                continue
            result = await self._request(config, "list_tools")
            for tool in result.tools:
                if tool.name not in config["allowed_tools"]:
                    continue
                tools.append(MCPTool(
                    server_name=config["name"],
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                ))
        return tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]):
        config = next(
            (item for item in self._server_configs if item["name"] == server_name),
            None,
        )
        if config is None or tool_name not in config["allowed_tools"]:
            raise PermissionError(f"MCP tool '{server_name}/{tool_name}' is not allowed.")

        result = await self._request(
            config,
            "call_tool",
            tool_name=tool_name,
            arguments=arguments,
        )
        if result.isError:
            raise RuntimeError(f"MCP tool '{server_name}/{tool_name}' failed.")
        return "\n".join(
            content.text
            for content in result.content
            if getattr(content, "text", None)
        )

    async def _request(
        self,
        config: Dict[str, Any],
        operation: str,
        tool_name: str = None,
        arguments: Dict[str, Any] = None,
    ):
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            raise RuntimeError("The MCP Python SDK is required for MCP tools.") from exc

        async def execute():
            async with streamablehttp_client(
                config["url"],
                headers=self._headers(config),
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    if operation == "list_tools":
                        return await session.list_tools()
                    return await session.call_tool(tool_name, arguments=arguments or {})

        return await asyncio.wait_for(execute(), timeout=self._timeout_seconds)
