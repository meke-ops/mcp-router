from dataclasses import dataclass, field
from typing import Any


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


class InMemoryToolRegistry:
    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools or []}

    async def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)
