import asyncio
from dataclasses import dataclass, field
from typing import Literal
from typing import Any


TransportKind = Literal["stdio", "streamable_http"]


@dataclass(slots=True, frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_mcp_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.output_schema is not None:
            payload["outputSchema"] = self.output_schema
        if self.tags:
            payload["annotations"] = {"tags": list(self.tags)}
        return payload


@dataclass(slots=True, frozen=True)
class ToolBinding:
    server_id: str


@dataclass(slots=True, frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    binding: ToolBinding


@dataclass(slots=True, frozen=True)
class UpstreamServerDefinition:
    server_id: str
    transport: TransportKind
    endpoint_url: str | None = None
    command: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0


class InMemoryToolRegistry:
    def __init__(
        self,
        tools: list[RegisteredTool] | None = None,
        upstream_servers: list[UpstreamServerDefinition] | None = None,
    ) -> None:
        self._tools = {tool.definition.name: tool for tool in tools or []}
        self._upstream_servers = {
            upstream_server.server_id: upstream_server
            for upstream_server in upstream_servers or []
        }
        self._lock = asyncio.Lock()

    async def list_tools(self) -> list[ToolDefinition]:
        async with self._lock:
            return [tool.definition for tool in self._tools.values()]

    async def get_tool(self, name: str) -> RegisteredTool | None:
        async with self._lock:
            return self._tools.get(name)

    async def replace_tools(self, tools: list[RegisteredTool]) -> None:
        async with self._lock:
            self._tools = {tool.definition.name: tool for tool in tools}

    async def list_upstream_servers(self) -> list[UpstreamServerDefinition]:
        async with self._lock:
            return list(self._upstream_servers.values())

    async def get_upstream_server(self, server_id: str) -> UpstreamServerDefinition | None:
        async with self._lock:
            return self._upstream_servers.get(server_id)
