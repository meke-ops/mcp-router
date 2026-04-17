from dataclasses import dataclass

from internal.audit import InMemoryAuditLog
from internal.config import Settings
from internal.health import ReadinessService
from internal.mcp.service import MCPRouterService
from internal.metrics import InMemoryMetricsRecorder
from internal.policy import InMemoryPolicyStore, PolicyEngine
from internal.resilience import InMemoryCircuitBreakerStore
from internal.registry import InMemoryToolRegistry
from internal.session_manager import InMemorySessionManager
from internal.state_store import RouterStateStore
from internal.setup import SetupService
from internal.tracing import InMemoryTraceRecorder
from internal.traffic_control import InMemoryTrafficController
from internal.upstream import UpstreamTransportGateway


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    readiness_service: ReadinessService
    metrics_recorder: InMemoryMetricsRecorder
    session_manager: InMemorySessionManager
    tool_registry: InMemoryToolRegistry
    policy_store: InMemoryPolicyStore
    policy_engine: PolicyEngine
    circuit_breaker_store: InMemoryCircuitBreakerStore
    audit_log: InMemoryAuditLog
    trace_recorder: InMemoryTraceRecorder
    traffic_controller: InMemoryTrafficController
    upstream_gateway: UpstreamTransportGateway
    mcp_service: MCPRouterService
    state_store: RouterStateStore
    setup_service: SetupService
