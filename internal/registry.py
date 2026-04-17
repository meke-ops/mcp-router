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
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    discover_tools: bool = True
    fallback_server_ids: tuple[str, ...] = ()
    retry_attempts: int = 0
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_seconds: float = 30.0
    origin_client: str | None = None
    origin_path: str | None = None
    managed_by: str | None = None
    last_imported_at: str | None = None

    @property
    def endpoint_url(self) -> str | None:
        return self.url

    @property
    def command_line(self) -> tuple[str, ...]:
        if self.command is None:
            return ()
        return (self.command, *self.args)

    def to_record(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "transport": self.transport,
            "url": self.url,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "headers": dict(self.headers),
            "timeout_seconds": self.timeout_seconds,
            "discover_tools": self.discover_tools,
            "fallback_server_ids": list(self.fallback_server_ids),
            "retry_attempts": self.retry_attempts,
            "circuit_breaker_failure_threshold": self.circuit_breaker_failure_threshold,
            "circuit_breaker_recovery_seconds": self.circuit_breaker_recovery_seconds,
            "origin_client": self.origin_client,
            "origin_path": self.origin_path,
            "managed_by": self.managed_by,
            "last_imported_at": self.last_imported_at,
        }

    @classmethod
    def from_record(cls, raw_item: dict[str, Any]) -> "UpstreamServerDefinition":
        if not isinstance(raw_item, dict):
            raise ValueError("Each upstream definition must be a JSON object.")
        legacy_command = raw_item.get("command")
        command: str | None
        args: tuple[str, ...]
        if isinstance(legacy_command, list):
            if not all(isinstance(part, str) for part in legacy_command):
                raise ValueError("Upstream command must be a JSON array of strings.")
            command = legacy_command[0] if legacy_command else None
            args = tuple(legacy_command[1:])
        else:
            if legacy_command is not None and not isinstance(legacy_command, str):
                raise ValueError("Upstream command must be a string.")
            raw_args = raw_item.get("args", [])
            if not isinstance(raw_args, list) or not all(
                isinstance(part, str) for part in raw_args
            ):
                raise ValueError("Upstream args must be a JSON array of strings.")
            command = legacy_command
            args = tuple(raw_args)

        env = raw_item.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()
        ):
            raise ValueError("Upstream env must be a JSON object of string pairs.")
        headers = raw_item.get("headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in headers.items()
        ):
            raise ValueError("Upstream headers must be a JSON object of string pairs.")

        url = raw_item.get("url", raw_item.get("endpoint_url"))
        if url is not None and not isinstance(url, str):
            raise ValueError("Upstream url must be a string when provided.")

        return cls(
            server_id=str(raw_item["server_id"]),
            transport=raw_item["transport"],
            url=url,
            command=command,
            args=args,
            env=env,
            headers=headers,
            timeout_seconds=float(raw_item.get("timeout_seconds", 10.0)),
            discover_tools=bool(raw_item.get("discover_tools", True)),
            fallback_server_ids=tuple(
                str(item) for item in raw_item.get("fallback_server_ids", [])
            ),
            retry_attempts=int(raw_item.get("retry_attempts", 0)),
            circuit_breaker_failure_threshold=int(
                raw_item.get("circuit_breaker_failure_threshold", 3)
            ),
            circuit_breaker_recovery_seconds=float(
                raw_item.get("circuit_breaker_recovery_seconds", 30.0)
            ),
            origin_client=(
                str(raw_item["origin_client"])
                if raw_item.get("origin_client") is not None
                else None
            ),
            origin_path=(
                str(raw_item["origin_path"])
                if raw_item.get("origin_path") is not None
                else None
            ),
            managed_by=(
                str(raw_item["managed_by"])
                if raw_item.get("managed_by") is not None
                else None
            ),
            last_imported_at=(
                str(raw_item["last_imported_at"])
                if raw_item.get("last_imported_at") is not None
                else None
            ),
        )

    def normalized_signature(self) -> str:
        payload = {
            "transport": self.transport,
            "url": (self.url or "").rstrip("/"),
            "command": self.command or "",
            "args": list(self.args),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    def to_discovery_summary(self) -> str:
        if self.transport == "streamable_http":
            return self.url or "-"
        if self.command is None:
            return "-"
        return " ".join([self.command, *self.args])


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
        initial_tools = {tool.definition.name: tool for tool in tools or []}
        self._discovered_tools = dict(initial_tools)
        self._manual_tools: dict[str, RegisteredTool] = {}
        self._upstream_servers = {
            upstream_server.server_id: upstream_server
            for upstream_server in upstream_servers or []
        }
        self._lock = asyncio.Lock()

    async def list_tools(self) -> list[ToolDefinition]:
        async with self._lock:
            return [tool.definition for tool in self._merged_tools().values()]

    async def list_registered_tools(self) -> list[RegisteredTool]:
        async with self._lock:
            return list(self._merged_tools().values())

    async def get_tool(self, name: str) -> RegisteredTool | None:
        async with self._lock:
            return self._manual_tools.get(name) or self._discovered_tools.get(name)

    async def replace_tools(self, tools: list[RegisteredTool]) -> None:
        async with self._lock:
            self._discovered_tools = {tool.name: tool for tool in tools}

    async def upsert_tool(self, tool: RegisteredTool) -> RegisteredTool:
        async with self._lock:
            self._manual_tools[tool.name] = tool
            return tool

    async def delete_tool(self, name: str) -> RegisteredTool | None:
        async with self._lock:
            return self._manual_tools.pop(name, None)

    async def list_upstream_servers(self) -> list[UpstreamServerDefinition]:
        async with self._lock:
            return list(self._upstream_servers.values())

    async def list_discoverable_upstream_servers(self) -> list[UpstreamServerDefinition]:
        async with self._lock:
            return [
                upstream_server
                for upstream_server in self._upstream_servers.values()
                if upstream_server.discover_tools
            ]

    async def get_upstream_server(self, server_id: str) -> UpstreamServerDefinition | None:
        async with self._lock:
            return self._upstream_servers.get(server_id)

    async def upsert_upstream_server(
        self,
        upstream_server: UpstreamServerDefinition,
    ) -> UpstreamServerDefinition:
        async with self._lock:
            self._upstream_servers[upstream_server.server_id] = upstream_server
            return upstream_server

    async def delete_upstream_server(self, server_id: str) -> UpstreamServerDefinition | None:
        async with self._lock:
            return self._upstream_servers.pop(server_id, None)

    async def find_upstream_by_signature(
        self,
        signature: str,
    ) -> UpstreamServerDefinition | None:
        async with self._lock:
            for upstream_server in self._upstream_servers.values():
                if upstream_server.normalized_signature() == signature:
                    return upstream_server
        return None

    def _merged_tools(self) -> dict[str, RegisteredTool]:
        return {**self._discovered_tools, **self._manual_tools}
