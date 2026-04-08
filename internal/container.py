from dataclasses import dataclass

from internal.config import Settings
from internal.health import ReadinessService
from internal.mcp.service import MCPRouterService
from internal.registry import InMemoryToolRegistry
from internal.session_manager import InMemorySessionManager


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    readiness_service: ReadinessService
    session_manager: InMemorySessionManager
    tool_registry: InMemoryToolRegistry
    mcp_service: MCPRouterService
