import asyncio
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any
from typing import Literal


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
    tool_version: str
    timeout_seconds: float | None = None


@dataclass(slots=True, frozen=True)
class ToolVersion:
    version: str
    definition: ToolDefinition
    schema_digest: str

    def to_mcp_payload(self) -> dict[str, Any]:
        return self.definition.to_mcp_payload()


@dataclass(slots=True, frozen=True)
class RegisteredTool:
    name: str
    latest_version: ToolVersion
    versions: dict[str, ToolVersion]
    binding: ToolBinding

    @property
    def definition(self) -> ToolDefinition:
        return self.latest_version.definition

    @property
    def version(self) -> str:
        return self.latest_version.version

    def to_mcp_payload(self) -> dict[str, Any]:
        payload = self.latest_version.to_mcp_payload()
        payload["_meta"] = {
            "router": {
                "version": self.latest_version.version,
                "serverId": self.binding.server_id,
            }
        }
        return payload


@dataclass(slots=True, frozen=True)
class UpstreamServerDefinition:
    server_id: str
    transport: TransportKind
    endpoint_url: str | None = None
    command: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0


def build_tool_version(definition: ToolDefinition) -> ToolVersion:
    canonical_payload = json.dumps(
        {
            "name": definition.name,
            "description": definition.description,
            "inputSchema": definition.input_schema,
            "outputSchema": definition.output_schema,
            "tags": list(definition.tags),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    schema_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()[:12]
    return ToolVersion(
        version=f"sha256:{schema_digest}",
        definition=definition,
        schema_digest=schema_digest,
    )


def build_registered_tool(
    definition: ToolDefinition,
    server_id: str,
    timeout_seconds: float | None = None,
) -> RegisteredTool:
    tool_version = build_tool_version(definition)
    return RegisteredTool(
        name=definition.name,
        latest_version=tool_version,
        versions={tool_version.version: tool_version},
        binding=ToolBinding(
            server_id=server_id,
            tool_version=tool_version.version,
            timeout_seconds=timeout_seconds,
        ),
    )


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

    async def list_registered_tools(self) -> list[RegisteredTool]:
        async with self._lock:
            return list(self._tools.values())

    async def get_tool(self, name: str) -> RegisteredTool | None:
        async with self._lock:
            return self._tools.get(name)

    async def replace_tools(self, tools: list[RegisteredTool]) -> None:
        async with self._lock:
            self._tools = {tool.name: tool for tool in tools}

    async def list_upstream_servers(self) -> list[UpstreamServerDefinition]:
        async with self._lock:
            return list(self._upstream_servers.values())

    async def get_upstream_server(self, server_id: str) -> UpstreamServerDefinition | None:
        async with self._lock:
            return self._upstream_servers.get(server_id)
