from contextlib import asynccontextmanager
import json
import logging
from time import perf_counter
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from api.http.dashboard import router as dashboard_router
from api.http.mcp import router as mcp_router
from api.http.ops import router as ops_router
from api.http.v1.router import router as api_v1_router
from internal.audit import InMemoryAuditLog
from internal.config import Settings, get_settings
from internal.container import ServiceContainer
from internal.context import RouterRequestContext
from internal.health import ReadinessService
from internal.logging import configure_logging
from internal.mcp.service import MCPRouterService
from internal.metrics import InMemoryMetricsRecorder
from internal.policy import InMemoryPolicyStore, PolicyEngine, PolicyObligation, PolicyRule
from internal.resilience import InMemoryCircuitBreakerStore
from internal.registry import InMemoryToolRegistry, UpstreamServerDefinition
from internal.session_manager import InMemorySessionManager
from internal.setup import SetupService
from internal.state_store import RouterStateStore
from internal.tracing import InMemoryTraceRecorder, build_inbound_span_context
from internal.traffic_control import InMemoryTrafficController
from internal.upstream import UpstreamTransportGateway


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = perf_counter()
        request_id = request.headers.get("X-Request-Id", str(uuid4()))
        inbound_trace_context = build_inbound_span_context(
            request.headers.get("traceparent")
        )
        request_context = RouterRequestContext(
            request_id=request_id,
            trace_id=inbound_trace_context.trace_id,
            span_id=inbound_trace_context.span_id,
            parent_span_id=inbound_trace_context.parent_span_id,
            traceparent=inbound_trace_context.traceparent,
        )
        request.state.request_id = request_id
        request.state.request_context = request_context
        services = getattr(request.app.state, "services", None)
        if services is None:
            response = await call_next(request)
        else:
            async with services.trace_recorder.span(
                name=f"http {request.method} {request.url.path}",
                span_context=inbound_trace_context,
                attributes={
                    "http.method": request.method,
                    "http.route": request.url.path,
                    "request.id": request_id,
                },
            ):
                response = await call_next(request)

        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        duration_seconds = perf_counter() - started_at
        if services is not None and services.settings.metrics_enabled:
            await services.metrics_recorder.record_http_request(
                method=request.method,
                path=route_path,
                status_code=response.status_code,
                duration_seconds=duration_seconds,
            )
        logging.getLogger("mcp_router.http").info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": route_path,
                "status_code": response.status_code,
                "duration_ms": round(duration_seconds * 1000, 3),
                "request_id": request_id,
                "trace_id": request_context.trace_id,
            },
        )
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = request_context.trace_id
        response.headers["traceparent"] = request_context.traceparent
        return response


def create_service_container(
    settings: Settings,
    upstream_servers: list[UpstreamServerDefinition] | None = None,
    policy_rules: list[PolicyRule] | None = None,
    http_transport_overrides: dict[str, httpx.AsyncBaseTransport] | None = None,
) -> ServiceContainer:
    state_store = RouterStateStore(settings.resolved_local_state_path())
    resolved_upstream_servers = _merge_upstream_sources(
        env_upstreams=upstream_servers or _load_upstream_servers(settings),
        persisted_upstreams=state_store.load().upstreams,
    )
    resolved_policy_rules = policy_rules or _load_policy_rules(settings)
    session_manager = InMemorySessionManager(ttl_seconds=settings.session_ttl_seconds)
    tool_registry = InMemoryToolRegistry(upstream_servers=resolved_upstream_servers)
    readiness_service = ReadinessService(settings=settings)
    metrics_recorder = InMemoryMetricsRecorder(settings=settings)
    policy_store = InMemoryPolicyStore(rules=resolved_policy_rules)
    policy_engine = PolicyEngine(store=policy_store)
    circuit_breaker_store = InMemoryCircuitBreakerStore()
    audit_log = InMemoryAuditLog()
    trace_recorder = InMemoryTraceRecorder()
    traffic_controller = InMemoryTrafficController(
        rate_limit_capacity=settings.tool_call_rate_limit_capacity,
        rate_limit_refill_rate=settings.tool_call_rate_limit_refill_rate,
        concurrency_limit=settings.tool_call_concurrency_limit,
    )
    upstream_gateway = UpstreamTransportGateway(
        http_transport_overrides=http_transport_overrides,
    )
    mcp_service = MCPRouterService(
        settings=settings,
        session_manager=session_manager,
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        circuit_breaker_store=circuit_breaker_store,
        audit_log=audit_log,
        trace_recorder=trace_recorder,
        traffic_controller=traffic_controller,
        upstream_gateway=upstream_gateway,
    )
    setup_service = SetupService(
        settings=settings,
        state_store=state_store,
        tool_registry=tool_registry,
        mcp_service=mcp_service,
    )

    return ServiceContainer(
        settings=settings,
        readiness_service=readiness_service,
        metrics_recorder=metrics_recorder,
        session_manager=session_manager,
        tool_registry=tool_registry,
        policy_store=policy_store,
        policy_engine=policy_engine,
        circuit_breaker_store=circuit_breaker_store,
        audit_log=audit_log,
        trace_recorder=trace_recorder,
        traffic_controller=traffic_controller,
        upstream_gateway=upstream_gateway,
        mcp_service=mcp_service,
        state_store=state_store,
        setup_service=setup_service,
    )


def _load_upstream_servers(settings: Settings) -> list[UpstreamServerDefinition] | None:
    if not settings.upstreams_json:
        return None

    raw_items = json.loads(settings.upstreams_json)
    if not isinstance(raw_items, list):
        raise ValueError("MCP_ROUTER_UPSTREAMS_JSON must be a JSON array.")

    upstream_servers: list[UpstreamServerDefinition] = []
    for raw_item in raw_items:
        upstream_servers.append(UpstreamServerDefinition.from_record(raw_item))

    return upstream_servers


def _merge_upstream_sources(
    *,
    env_upstreams: list[UpstreamServerDefinition] | None,
    persisted_upstreams: list[UpstreamServerDefinition],
) -> list[UpstreamServerDefinition]:
    merged = {
        upstream.server_id: upstream for upstream in env_upstreams or []
    }
    for upstream in persisted_upstreams:
        merged[upstream.server_id] = upstream
    return list(merged.values())


def _load_policy_rules(settings: Settings) -> list[PolicyRule] | None:
    if not settings.policies_json:
        return None

    raw_items = json.loads(settings.policies_json)
    if not isinstance(raw_items, list):
        raise ValueError("MCP_ROUTER_POLICIES_JSON must be a JSON array.")

    policy_rules: list[PolicyRule] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Each policy rule must be a JSON object.")
        obligations = raw_item.get("obligations", [])
        if not isinstance(obligations, list):
            raise ValueError("Policy obligations must be a JSON array.")

        parsed_obligations: list[PolicyObligation] = []
        for raw_obligation in obligations:
            if not isinstance(raw_obligation, dict):
                raise ValueError("Each obligation must be a JSON object.")
            obligation_type = raw_obligation.get("type")
            parameters = raw_obligation.get("parameters", {})
            if not isinstance(obligation_type, str) or not obligation_type:
                raise ValueError("Policy obligation type must be a non-empty string.")
            if not isinstance(parameters, dict):
                raise ValueError("Policy obligation parameters must be a JSON object.")
            parsed_obligations.append(
                PolicyObligation(
                    obligation_type=obligation_type,
                    parameters=parameters,
                )
            )

        policy_rules.append(
            PolicyRule(
                rule_id=str(raw_item["rule_id"]),
                effect=raw_item["effect"],
                reason=str(raw_item["reason"]),
                priority=int(raw_item.get("priority", 0)),
                tenant_ids=tuple(str(item) for item in raw_item.get("tenant_ids", [])),
                principal_ids=tuple(str(item) for item in raw_item.get("principal_ids", [])),
                roles=tuple(str(item) for item in raw_item.get("roles", [])),
                tool_names=tuple(str(item) for item in raw_item.get("tool_names", [])),
                tool_versions=tuple(str(item) for item in raw_item.get("tool_versions", [])),
                obligations=tuple(parsed_obligations),
            )
        )

    return policy_rules


def create_app(
    settings: Settings | None = None,
    upstream_servers: list[UpstreamServerDefinition] | None = None,
    policy_rules: list[PolicyRule] | None = None,
    http_transport_overrides: dict[str, httpx.AsyncBaseTransport] | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level, app_settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = create_service_container(
            app_settings,
            upstream_servers=upstream_servers,
            policy_rules=policy_rules,
            http_transport_overrides=http_transport_overrides,
        )
        yield

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_v1_router, prefix=app_settings.api_v1_prefix)
    app.include_router(mcp_router, prefix=app_settings.mcp_prefix)
    app.include_router(dashboard_router)
    app.include_router(ops_router)

    return app


app = create_app()
