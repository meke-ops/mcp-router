from dataclasses import dataclass

from internal.audit import InMemoryAuditLog
from internal.config import Settings
from internal.health import ReadinessService
from internal.mcp.service import MCPRouterService
from internal.policy import InMemoryPolicyStore, PolicyEngine
from internal.registry import InMemoryToolRegistry
from internal.session_manager import InMemorySessionManager
from internal.tracing import InMemoryTraceRecorder
from internal.traffic_control import InMemoryTrafficController
from internal.upstream import UpstreamTransportGateway


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    readiness_service: ReadinessService
    session_manager: InMemorySessionManager
    tool_registry: InMemoryToolRegistry
    policy_store: InMemoryPolicyStore
    policy_engine: PolicyEngine
    audit_log: InMemoryAuditLog
    trace_recorder: InMemoryTraceRecorder
    traffic_controller: InMemoryTrafficController
    upstream_gateway: UpstreamTransportGateway
    mcp_service: MCPRouterService
