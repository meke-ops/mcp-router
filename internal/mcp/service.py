from dataclasses import dataclass
from time import perf_counter

from internal.audit import InMemoryAuditLog
from internal.config import Settings
from internal.context import RequestIdentity, RouterRequestContext
from internal.mcp.errors import JsonRpcErrorCode, JsonRpcFault
from internal.mcp.models import JsonRpcRequest, JsonRpcResponse
from internal.policy import PolicyDecision, PolicyEngine, PolicyEvaluationContext
from internal.resilience import InMemoryCircuitBreakerStore
from internal.registry import (
    build_registered_tool,
    InMemoryToolRegistry,
    RegisteredTool,
    ToolDefinition,
    UpstreamServerDefinition,
)
from internal.schema import (
    ToolArgumentsSchemaValidator,
    ToolSchemaDefinitionFailure,
    ToolSchemaValidationFailure,
)
from internal.session_manager import InMemorySessionManager, SessionRecord
from internal.tracing import InMemoryTraceRecorder, SpanContext
from internal.traffic_control import (
    InMemoryTrafficController,
    TrafficControlContext,
    TrafficControlLease,
    TrafficLimitDecision,
)
from internal.upstream import UpstreamCallResult, UpstreamTransportError, UpstreamTransportGateway


@dataclass(slots=True)
class DispatchResult:
    response: JsonRpcResponse | None
    session_id: str | None = None
    status_code: int = 200


class MCPRouterService:
    def __init__(
        self,
        settings: Settings,
        session_manager: InMemorySessionManager,
        tool_registry: InMemoryToolRegistry,
        policy_engine: PolicyEngine,
        circuit_breaker_store: InMemoryCircuitBreakerStore,
        audit_log: InMemoryAuditLog,
        trace_recorder: InMemoryTraceRecorder,
        traffic_controller: InMemoryTrafficController,
        upstream_gateway: UpstreamTransportGateway,
    ) -> None:
        self._settings = settings
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._policy_engine = policy_engine
        self._circuit_breaker_store = circuit_breaker_store
        self._audit_log = audit_log
        self._trace_recorder = trace_recorder
        self._traffic_controller = traffic_controller
        self._upstream_gateway = upstream_gateway
        self._arguments_schema_validator = ToolArgumentsSchemaValidator()

    async def handle_request(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
        request_context: RouterRequestContext,
    ) -> DispatchResult:
        try:
            if request.method == "initialize":
                return await self._handle_initialize(
                    request,
                    session_id,
                    identity,
                    request_context,
                )
            if request.method == "notifications/initialized":
                return await self._handle_initialized_notification(
                    session_id,
                    identity,
                    request_context,
                )
            if request.method == "tools/list":
                return await self._handle_tools_list(
                    request,
                    session_id,
                    identity,
                    request_context,
                )
            if request.method == "tools/call":
                return await self._handle_tools_call(
                    request,
                    session_id,
                    identity,
                    request_context,
                )
            raise JsonRpcFault(
                code=JsonRpcErrorCode.METHOD_NOT_FOUND,
                message=f"Unsupported MCP method: {request.method}",
            )
        except JsonRpcFault as exc:
            return DispatchResult(
                response=JsonRpcResponse(
                    id=request.id,
                    error={
                        "code": int(exc.code),
                        "message": exc.message,
                        "data": exc.data,
                    },
                ),
                session_id=session_id,
            )

    async def _handle_initialize(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
        request_context: RouterRequestContext,
    ) -> DispatchResult:
        self._require_request_id(request)
        try:
            session = await self._session_manager.get_or_create(
                session_id=session_id,
                tenant_id=identity.tenant_id,
                principal_id=identity.principal_id,
                roles=identity.roles,
            )
        except ValueError as exc:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.IDENTITY_MISMATCH,
                message="Session is already bound to a different tenant or principal.",
            ) from exc
        await self._initialize_upstreams(
            session=session,
            request=request,
            request_context=request_context,
        )

        return DispatchResult(
            response=JsonRpcResponse(
                id=request.id,
                result={
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {
                        "name": self._settings.app_name,
                        "version": self._settings.app_version,
                    },
                    "identity": {
                        "tenantId": session.tenant_id,
                        "principalId": session.principal_id,
                        "roles": list(session.roles),
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": True,
                        }
                    },
                },
            ),
            session_id=session.session_id,
        )

    async def _handle_initialized_notification(
        self,
        session_id: str | None,
        identity: RequestIdentity,
        request_context: RouterRequestContext,
    ) -> DispatchResult:
        session = await self._require_session(session_id, identity)
        await self._session_manager.touch(session.session_id)
        for upstream_server in await self._tool_registry.list_upstream_servers():
            await self._send_upstream_request(
                server=upstream_server,
                request=JsonRpcRequest(
                    jsonrpc="2.0",
                    method="notifications/initialized",
                    params={},
                ),
                session=session,
                request_context=request_context,
                parent_span_id=request_context.span_id,
            )
        return DispatchResult(response=None, session_id=session.session_id, status_code=202)

    async def _handle_tools_list(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
        request_context: RouterRequestContext,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._require_session(session_id, identity)
        tools = await self._list_available_tools(
            request=request,
            session=session,
            request_context=request_context,
        )

        return DispatchResult(
            response=JsonRpcResponse(
                id=request.id,
                result={"tools": [tool.to_mcp_payload() for tool in tools]},
            ),
            session_id=session.session_id,
        )

    async def _handle_tools_call(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
        request_context: RouterRequestContext,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._require_session(session_id, identity)
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        if not isinstance(tool_name, str) or not tool_name.strip():
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_PARAMS,
                message="tools/call requires a non-empty tool name.",
            )
        if not isinstance(arguments, dict):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_PARAMS,
                message="tools/call arguments must be an object.",
            )

        started_at = perf_counter()
        registered_tool: RegisteredTool | None = None
        traffic_decision: TrafficLimitDecision | None = None
        lease: TrafficControlLease | None = None
        resolved_tool_name = tool_name.strip()

        async with self._trace_recorder.span(
            name="mcp.tools.call",
            trace_id=request_context.trace_id,
            parent_span_id=request_context.span_id,
            attributes={
                "mcp.method": request.method,
                "mcp.tool_name": resolved_tool_name,
                "tenant.id": session.tenant_id,
                "principal.id": session.principal_id,
            },
        ) as tool_call_span:
            await self._audit_log.record_event(
                trace_id=request_context.trace_id,
                span_id=tool_call_span.span_id,
                session_id=session.session_id,
                request_id=request.id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
                tool_name=resolved_tool_name,
                event_type="tool_call.started",
                detail={"roles": list(session.roles)},
            )
            try:
                registered_tool = await self._tool_registry.get_tool(resolved_tool_name)
                if registered_tool is None:
                    await self._refresh_tools_from_upstreams(
                        request=request,
                        session=session,
                        request_context=request_context,
                    )
                    registered_tool = await self._tool_registry.get_tool(resolved_tool_name)
                if registered_tool is None:
                    raise JsonRpcFault(
                        code=JsonRpcErrorCode.TOOL_NOT_FOUND,
                        message=f"Tool is not registered: {resolved_tool_name}",
                    )

                traffic_decision, lease = await self._check_traffic_limits(
                    session=session,
                    request=request,
                    request_context=request_context,
                    registered_tool=registered_tool,
                    parent_span_context=tool_call_span,
                )
                if not traffic_decision.allowed:
                    error_code = (
                        JsonRpcErrorCode.CONCURRENCY_LIMITED
                        if traffic_decision.limit_type == "concurrency"
                        else JsonRpcErrorCode.RATE_LIMITED
                    )
                    await self._record_tool_call_audit(
                        request=request,
                        session=session,
                        request_context=request_context,
                        span_id=tool_call_span.span_id,
                        registered_tool=registered_tool,
                        outcome=traffic_decision.limit_type,
                        status_code=429,
                        error_code=int(error_code),
                        error_message=traffic_decision.reason,
                        started_at=started_at,
                        traffic_decision=traffic_decision,
                    )
                    return DispatchResult(
                        response=JsonRpcResponse(
                            id=request.id,
                            error={
                                "code": int(error_code),
                                "message": traffic_decision.reason,
                                "data": traffic_decision.to_payload(),
                            },
                        ),
                        session_id=session.session_id,
                        status_code=429,
                    )

                policy_decision = await self._evaluate_tool_policy(
                    request=request,
                    session=session,
                    request_context=request_context,
                    registered_tool=registered_tool,
                    parent_span_context=tool_call_span,
                )
                if policy_decision.effect == "deny":
                    await self._record_tool_call_audit(
                        request=request,
                        session=session,
                        request_context=request_context,
                        span_id=tool_call_span.span_id,
                        registered_tool=registered_tool,
                        outcome="policy_denied",
                        status_code=403,
                        error_code=int(JsonRpcErrorCode.POLICY_DENIED),
                        error_message=policy_decision.reason,
                        started_at=started_at,
                        traffic_decision=traffic_decision,
                    )
                    return DispatchResult(
                        response=JsonRpcResponse(
                            id=request.id,
                            error={
                                "code": int(JsonRpcErrorCode.POLICY_DENIED),
                                "message": policy_decision.reason,
                                "data": policy_decision.to_payload(),
                            },
                        ),
                        session_id=session.session_id,
                        status_code=403,
                    )

                self._validate_tool_arguments(
                    registered_tool=registered_tool,
                    arguments=arguments,
                )

                upstream_server = await self._tool_registry.get_upstream_server(
                    registered_tool.binding.server_id
                )
                if upstream_server is None:
                    raise JsonRpcFault(
                        code=JsonRpcErrorCode.UPSTREAM_NOT_CONFIGURED,
                        message=(
                            f"Tool binding is missing an upstream server: {resolved_tool_name}"
                        ),
                    )

                upstream_result = await self._send_tool_call_with_resilience(
                    primary_server=upstream_server,
                    request=request,
                    session=session,
                    request_context=request_context,
                    parent_span_id=tool_call_span.span_id,
                    registered_tool=registered_tool,
                )
                dispatch_result = self._dispatch_result_from_upstream(
                    upstream_result=upstream_result,
                    session_id=session.session_id,
                    request_id=request.id,
                )
                response_error = (
                    dispatch_result.response.error
                    if dispatch_result.response is not None
                    else None
                )
                outcome = "success" if response_error is None else "upstream_error"
                event_type = (
                    "tool_call.completed"
                    if response_error is None
                    else "tool_call.failed"
                )
                await self._audit_log.record_event(
                    trace_id=request_context.trace_id,
                    span_id=tool_call_span.span_id,
                    session_id=session.session_id,
                    request_id=request.id,
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    tool_name=registered_tool.name,
                    event_type=event_type,
                    detail={
                        "statusCode": dispatch_result.status_code,
                        "jsonRpcErrorCode": (
                            response_error.code if response_error is not None else None
                        ),
                    },
                )
                await self._record_tool_call_audit(
                    request=request,
                    session=session,
                    request_context=request_context,
                    span_id=tool_call_span.span_id,
                    registered_tool=registered_tool,
                    outcome=outcome,
                    status_code=dispatch_result.status_code,
                    error_code=(
                        response_error.code if response_error is not None else None
                    ),
                    error_message=(
                        response_error.message if response_error is not None else None
                    ),
                    started_at=started_at,
                    traffic_decision=traffic_decision,
                    server_id_override=upstream_result.server_id,
                )
                return dispatch_result
            except JsonRpcFault as exc:
                await self._audit_log.record_event(
                    trace_id=request_context.trace_id,
                    span_id=tool_call_span.span_id,
                    session_id=session.session_id,
                    request_id=request.id,
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    tool_name=(
                        registered_tool.name
                        if registered_tool is not None
                        else resolved_tool_name
                    ),
                    event_type="tool_call.failed",
                    detail={
                        "statusCode": 200,
                        "jsonRpcErrorCode": int(exc.code),
                        "message": exc.message,
                    },
                )
                await self._record_tool_call_audit(
                    request=request,
                    session=session,
                    request_context=request_context,
                    span_id=tool_call_span.span_id,
                    registered_tool=registered_tool,
                    fallback_tool_name=resolved_tool_name,
                    outcome=self._tool_call_outcome_from_fault(exc),
                    status_code=200,
                    error_code=int(exc.code),
                    error_message=exc.message,
                    started_at=started_at,
                    traffic_decision=traffic_decision,
                )
                raise
            finally:
                if lease is not None and traffic_decision is not None:
                    active_count = await lease.release()
                    await self._audit_log.record_event(
                        trace_id=request_context.trace_id,
                        span_id=tool_call_span.span_id,
                        session_id=session.session_id,
                        request_id=request.id,
                        tenant_id=session.tenant_id,
                        principal_id=session.principal_id,
                        tool_name=(
                            registered_tool.name
                            if registered_tool is not None
                            else resolved_tool_name
                        ),
                        event_type="traffic.concurrency.released",
                        detail={
                            "key": traffic_decision.key,
                            "activeCount": active_count,
                        },
                    )

    def _require_request_id(self, request: JsonRpcRequest) -> None:
        if request.id is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_REQUEST,
                message="A JSON-RPC id is required for request/response flows.",
            )

    async def _require_session(
        self,
        session_id: str | None,
        identity: RequestIdentity,
    ) -> SessionRecord:
        if session_id is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.SESSION_REQUIRED,
                message="MCP-Session-Id header is required. Call initialize first.",
            )

        session = await self._session_manager.get(session_id)
        if session is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.SESSION_REQUIRED,
                message="Session is missing or expired. Call initialize again.",
            )
        if identity.tenant_supplied and identity.tenant_id != session.tenant_id:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.IDENTITY_MISMATCH,
                message="X-Tenant-Id does not match the bound session tenant.",
                data={
                    "expectedTenantId": session.tenant_id,
                    "receivedTenantId": identity.tenant_id,
                },
            )
        if identity.principal_supplied and identity.principal_id != session.principal_id:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.IDENTITY_MISMATCH,
                message="X-Principal-Id does not match the bound session principal.",
                data={
                    "expectedPrincipalId": session.principal_id,
                    "receivedPrincipalId": identity.principal_id,
                },
            )
        if identity.roles_supplied and identity.roles != session.roles:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.IDENTITY_MISMATCH,
                message="X-Principal-Roles does not match the bound session roles.",
                data={
                    "expectedRoles": list(session.roles),
                    "receivedRoles": list(identity.roles),
                },
            )
        return session

    async def _initialize_upstreams(
        self,
        session: SessionRecord,
        request: JsonRpcRequest,
        request_context: RouterRequestContext,
    ) -> None:
        for upstream_server in await self._tool_registry.list_upstream_servers():
            try:
                upstream_result = await self._send_upstream_request(
                    server=upstream_server,
                    request=JsonRpcRequest(
                        jsonrpc="2.0",
                        id=request.id,
                        method="initialize",
                        params=request.params,
                    ),
                    session=session,
                    request_context=request_context,
                    parent_span_id=request_context.span_id,
                )
            except JsonRpcFault as exc:
                if upstream_server.discover_tools:
                    raise
                await self._audit_log.record_event(
                    trace_id=request_context.trace_id,
                    span_id=request_context.span_id,
                    session_id=session.session_id,
                    request_id=request.id,
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    tool_name=None,
                    event_type="fallback.initialize.skipped",
                    detail={
                        "serverId": upstream_server.server_id,
                        "message": exc.message,
                    },
                )
                continue
            if upstream_result.response is not None and upstream_result.response.error is not None:
                raise JsonRpcFault(
                    code=upstream_result.response.error.code,
                    message=upstream_result.response.error.message,
                    data=upstream_result.response.error.data,
                )

    async def _list_available_tools(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
    ) -> list[RegisteredTool]:
        upstream_servers = await self._tool_registry.list_upstream_servers()
        if not upstream_servers:
            return await self._tool_registry.list_registered_tools()

        await self._refresh_tools_from_upstreams(
            request=request,
            session=session,
            request_context=request_context,
        )
        return await self._tool_registry.list_registered_tools()

    async def _refresh_tools_from_upstreams(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
    ) -> None:
        discovered_tools: list[RegisteredTool] = []
        seen_tool_names: dict[str, str] = {}

        for upstream_server in await self._tool_registry.list_discoverable_upstream_servers():
            upstream_result = await self._send_upstream_request(
                server=upstream_server,
                request=JsonRpcRequest(
                    jsonrpc="2.0",
                    id=request.id,
                    method="tools/list",
                    params={},
                ),
                session=session,
                request_context=request_context,
                parent_span_id=request_context.span_id,
            )
            if upstream_result.response is None:
                raise JsonRpcFault(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message=(
                        f"Upstream returned no tools/list response: {upstream_server.server_id}"
                    ),
                )
            if upstream_result.response.error is not None:
                raise JsonRpcFault(
                    code=upstream_result.response.error.code,
                    message=upstream_result.response.error.message,
                    data=upstream_result.response.error.data,
                )

            payload = upstream_result.response.result or {}
            raw_tools = payload.get("tools")
            if not isinstance(raw_tools, list):
                raise JsonRpcFault(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message=(
                        f"Upstream tools/list payload is invalid: {upstream_server.server_id}"
                    ),
                )

            for raw_tool in raw_tools:
                tool_definition = self._tool_definition_from_payload(raw_tool)
                previous_server = seen_tool_names.get(tool_definition.name)
                if previous_server is not None and previous_server != upstream_server.server_id:
                    raise JsonRpcFault(
                        code=JsonRpcErrorCode.TOOL_NAME_CONFLICT,
                        message=f"Duplicate tool discovered: {tool_definition.name}",
                        data={
                            "tool": tool_definition.name,
                            "servers": [previous_server, upstream_server.server_id],
                        },
                    )
                seen_tool_names[tool_definition.name] = upstream_server.server_id
                discovered_tools.append(
                    build_registered_tool(
                        definition=tool_definition,
                        server_id=upstream_server.server_id,
                        timeout_seconds=upstream_server.timeout_seconds,
                    )
                )

        await self._tool_registry.replace_tools(discovered_tools)

    def _tool_definition_from_payload(self, payload: object) -> ToolDefinition:
        if not isinstance(payload, dict):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message="Upstream tool payload must be an object.",
            )

        name = payload.get("name")
        description = payload.get("description", "")
        input_schema = payload.get("inputSchema", {})
        output_schema = payload.get("outputSchema")
        annotations = payload.get("annotations", {})
        tags = annotations.get("tags", []) if isinstance(annotations, dict) else []

        if not isinstance(name, str) or not name.strip():
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message="Upstream tool payload is missing a valid name.",
            )
        if not isinstance(description, str):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message=f"Upstream tool description must be a string: {name}",
            )
        if not isinstance(input_schema, dict):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message=f"Upstream inputSchema must be an object: {name}",
            )
        if output_schema is not None and not isinstance(output_schema, dict):
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message=f"Upstream outputSchema must be an object: {name}",
            )

        normalized_tags = tuple(tag for tag in tags if isinstance(tag, str))
        return ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            tags=normalized_tags,
        )

    def _validate_tool_arguments(
        self,
        registered_tool: RegisteredTool,
        arguments: dict,
    ) -> None:
        try:
            self._arguments_schema_validator.validate(
                schema=registered_tool.definition.input_schema,
                arguments=arguments,
            )
        except ToolSchemaDefinitionFailure as exc:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INTERNAL_ERROR,
                message=f"Registered schema is invalid for {registered_tool.name}",
                data={
                    "tool": registered_tool.name,
                    "toolVersion": registered_tool.version,
                    "detail": exc.message,
                },
            ) from exc
        except ToolSchemaValidationFailure as exc:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.INVALID_PARAMS,
                message=(
                    f"tools/call arguments do not match schema for {registered_tool.name}"
                ),
                data={
                    **exc.to_payload(),
                    "tool": registered_tool.name,
                    "toolVersion": registered_tool.version,
                },
            ) from exc

    async def _check_traffic_limits(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
        registered_tool: RegisteredTool,
        parent_span_context: SpanContext,
    ) -> tuple[TrafficLimitDecision, TrafficControlLease | None]:
        async with self._trace_recorder.span(
            name="traffic.check",
            trace_id=request_context.trace_id,
            parent_span_id=parent_span_context.span_id,
            attributes={
                "mcp.tool_name": registered_tool.name,
                "tenant.id": session.tenant_id,
                "principal.id": session.principal_id,
            },
        ) as traffic_span:
            decision, lease = await self._traffic_controller.acquire(
                TrafficControlContext(
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    tool_name=registered_tool.name,
                )
            )
            event_type = (
                "traffic.allowed"
                if decision.allowed
                else f"traffic.{decision.limit_type}.rejected"
            )
            await self._audit_log.record_event(
                trace_id=request_context.trace_id,
                span_id=traffic_span.span_id,
                session_id=session.session_id,
                request_id=request.id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
                tool_name=registered_tool.name,
                event_type=event_type,
                detail=decision.to_payload(),
            )
            return decision, lease

    async def _evaluate_tool_policy(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
        registered_tool: RegisteredTool,
        parent_span_context: SpanContext,
    ) -> PolicyDecision:
        async with self._trace_recorder.span(
            name="policy.evaluate",
            trace_id=request_context.trace_id,
            parent_span_id=parent_span_context.span_id,
            attributes={
                "mcp.tool_name": registered_tool.name,
                "mcp.tool_version": registered_tool.version,
                "mcp.server_id": registered_tool.binding.server_id,
            },
        ) as policy_span:
            decision = self._policy_engine.evaluate(
                PolicyEvaluationContext(
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    roles=session.roles,
                    tool_name=registered_tool.name,
                    tool_version=registered_tool.version,
                    server_id=registered_tool.binding.server_id,
                )
            )
            await self._audit_log.record_policy_decision(
                trace_id=request_context.trace_id,
                span_id=policy_span.span_id,
                session_id=session.session_id,
                request_id=request.id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
                roles=session.roles,
                tool_name=registered_tool.name,
                tool_version=registered_tool.version,
                server_id=registered_tool.binding.server_id,
                decision=decision.effect,
                reason=decision.reason,
                rule_id=decision.rule_id,
                is_default=decision.is_default,
                obligations=decision.obligations,
            )
            await self._audit_log.record_event(
                trace_id=request_context.trace_id,
                span_id=policy_span.span_id,
                session_id=session.session_id,
                request_id=request.id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
                tool_name=registered_tool.name,
                event_type=f"policy.{decision.effect}",
                detail=decision.to_payload(),
            )
            return decision

    async def _send_tool_call_with_resilience(
        self,
        *,
        primary_server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
        parent_span_id: str,
        registered_tool: RegisteredTool,
    ) -> UpstreamCallResult:
        route_servers = await self._resolve_route_servers(primary_server)
        route_failures: list[dict[str, object | None]] = []

        async with self._trace_recorder.span(
            name="upstream.resilience",
            trace_id=request_context.trace_id,
            parent_span_id=parent_span_id,
            attributes={
                "mcp.tool_name": registered_tool.name,
                "mcp.primary_server_id": primary_server.server_id,
            },
        ) as resilience_span:
            for index, route_server in enumerate(route_servers):
                circuit_decision = await self._circuit_breaker_store.before_request(
                    route_server.server_id
                )
                if not circuit_decision.allowed:
                    route_failures.append(
                        {
                            "serverId": route_server.server_id,
                            "type": "circuit_open",
                            "retryAfterSeconds": circuit_decision.retry_after_seconds,
                        }
                    )
                    await self._audit_log.record_event(
                        trace_id=request_context.trace_id,
                        span_id=resilience_span.span_id,
                        session_id=session.session_id,
                        request_id=request.id,
                        tenant_id=session.tenant_id,
                        principal_id=session.principal_id,
                        tool_name=registered_tool.name,
                        event_type="circuit.open.rejected",
                        detail={
                            "serverId": route_server.server_id,
                            **circuit_decision.to_payload(),
                        },
                    )
                    if index < len(route_servers) - 1:
                        await self._audit_log.record_event(
                            trace_id=request_context.trace_id,
                            span_id=resilience_span.span_id,
                            session_id=session.session_id,
                            request_id=request.id,
                            tenant_id=session.tenant_id,
                            principal_id=session.principal_id,
                            tool_name=registered_tool.name,
                            event_type="upstream.fallback.selected",
                            detail={
                                "fromServerId": route_server.server_id,
                                "toServerId": route_servers[index + 1].server_id,
                                "reason": "circuit_open",
                            },
                        )
                    continue

                last_transport_error: str | None = None
                for attempt_index in range(route_server.retry_attempts + 1):
                    try:
                        upstream_result = await self._send_upstream_request(
                            server=route_server,
                            request=request,
                            session=session,
                            request_context=request_context,
                            parent_span_id=resilience_span.span_id,
                            convert_transport_errors=False,
                        )
                    except UpstreamTransportError as exc:
                        last_transport_error = str(exc)
                        route_failures.append(
                            {
                                "serverId": route_server.server_id,
                                "type": "transport_error",
                                "attempt": attempt_index + 1,
                                "detail": last_transport_error,
                            }
                        )
                        breaker_result = await self._circuit_breaker_store.record_failure(
                            route_server.server_id,
                            failure_threshold=route_server.circuit_breaker_failure_threshold,
                            recovery_timeout_seconds=route_server.circuit_breaker_recovery_seconds,
                        )
                        await self._audit_log.record_event(
                            trace_id=request_context.trace_id,
                            span_id=resilience_span.span_id,
                            session_id=session.session_id,
                            request_id=request.id,
                            tenant_id=session.tenant_id,
                            principal_id=session.principal_id,
                            tool_name=registered_tool.name,
                            event_type="upstream.retry.failed",
                            detail={
                                "serverId": route_server.server_id,
                                "attempt": attempt_index + 1,
                                "detail": last_transport_error,
                            },
                        )
                        if breaker_result.state == "open":
                            await self._audit_log.record_event(
                                trace_id=request_context.trace_id,
                                span_id=resilience_span.span_id,
                                session_id=session.session_id,
                                request_id=request.id,
                                tenant_id=session.tenant_id,
                                principal_id=session.principal_id,
                                tool_name=registered_tool.name,
                                event_type="circuit.opened",
                                detail={
                                    "serverId": route_server.server_id,
                                    **breaker_result.to_payload(),
                                },
                            )
                            break
                        if attempt_index < route_server.retry_attempts:
                            await self._audit_log.record_event(
                                trace_id=request_context.trace_id,
                                span_id=resilience_span.span_id,
                                session_id=session.session_id,
                                request_id=request.id,
                                tenant_id=session.tenant_id,
                                principal_id=session.principal_id,
                                tool_name=registered_tool.name,
                                event_type="upstream.retry.scheduled",
                                detail={
                                    "serverId": route_server.server_id,
                                    "nextAttempt": attempt_index + 2,
                                },
                            )
                            continue
                        break
                    else:
                        await self._circuit_breaker_store.record_success(route_server.server_id)
                        if route_server.server_id != primary_server.server_id:
                            await self._audit_log.record_event(
                                trace_id=request_context.trace_id,
                                span_id=resilience_span.span_id,
                                session_id=session.session_id,
                                request_id=request.id,
                                tenant_id=session.tenant_id,
                                principal_id=session.principal_id,
                                tool_name=registered_tool.name,
                                event_type="upstream.fallback.succeeded",
                                detail={
                                    "primaryServerId": primary_server.server_id,
                                    "selectedServerId": route_server.server_id,
                                },
                            )
                        return upstream_result

                if index < len(route_servers) - 1:
                    await self._audit_log.record_event(
                        trace_id=request_context.trace_id,
                        span_id=resilience_span.span_id,
                        session_id=session.session_id,
                        request_id=request.id,
                        tenant_id=session.tenant_id,
                        principal_id=session.principal_id,
                        tool_name=registered_tool.name,
                        event_type="upstream.fallback.selected",
                        detail={
                            "fromServerId": route_server.server_id,
                            "toServerId": route_servers[index + 1].server_id,
                            "reason": last_transport_error or "transport_error",
                        },
                    )

            raise JsonRpcFault(
                code=JsonRpcErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"All upstream routes failed for tool: {registered_tool.name}",
                data={
                    "tool": registered_tool.name,
                    "primaryServerId": primary_server.server_id,
                    "routesTried": route_failures,
                },
            )

    async def _resolve_route_servers(
        self,
        primary_server: UpstreamServerDefinition,
    ) -> list[UpstreamServerDefinition]:
        ordered_servers: list[UpstreamServerDefinition] = []
        visited: set[str] = set()
        pending_server_ids = [primary_server.server_id]

        while pending_server_ids:
            server_id = pending_server_ids.pop(0)
            if server_id in visited:
                continue
            visited.add(server_id)
            server = await self._tool_registry.get_upstream_server(server_id)
            if server is None:
                continue
            ordered_servers.append(server)
            pending_server_ids.extend(server.fallback_server_ids)

        return ordered_servers

    async def _send_upstream_request(
        self,
        server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
        parent_span_id: str,
        convert_transport_errors: bool = True,
    ) -> UpstreamCallResult:
        upstream_session_id = await self._session_manager.get_upstream_session(
            session_id=session.session_id,
            server_id=server.server_id,
        )
        async with self._trace_recorder.span(
            name="upstream.call",
            trace_id=request_context.trace_id,
            parent_span_id=parent_span_id,
            attributes={
                "mcp.method": request.method,
                "mcp.server_id": server.server_id,
                "mcp.transport": server.transport,
            },
        ) as upstream_span:
            try:
                upstream_result = await self._upstream_gateway.send(
                    server=server,
                    request=request,
                    session_id=upstream_session_id,
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    request_id=request_context.request_id,
                    traceparent=upstream_span.traceparent,
                )
            except UpstreamTransportError as exc:
                await self._audit_log.record_event(
                    trace_id=request_context.trace_id,
                    span_id=upstream_span.span_id,
                    session_id=session.session_id,
                    request_id=request.id,
                    tenant_id=session.tenant_id,
                    principal_id=session.principal_id,
                    tool_name=request.params.get("name")
                    if isinstance(request.params.get("name"), str)
                    else None,
                    event_type="upstream.call.failed",
                    detail={"serverId": server.server_id, "detail": str(exc)},
                )
                if convert_transport_errors:
                    raise JsonRpcFault(
                        code=JsonRpcErrorCode.UPSTREAM_UNAVAILABLE,
                        message=f"Upstream transport failed: {server.server_id}",
                        data={"detail": str(exc)},
                    ) from exc
                raise

            if upstream_result.upstream_session_id:
                await self._session_manager.set_upstream_session(
                    session_id=session.session_id,
                    server_id=server.server_id,
                    upstream_session_id=upstream_result.upstream_session_id,
                )

            await self._audit_log.record_event(
                trace_id=request_context.trace_id,
                span_id=upstream_span.span_id,
                session_id=session.session_id,
                request_id=request.id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
                tool_name=request.params.get("name")
                if isinstance(request.params.get("name"), str)
                else None,
                event_type="upstream.call.completed",
                detail={
                    "serverId": server.server_id,
                    "transport": server.transport,
                    "upstreamSessionId": upstream_result.upstream_session_id,
                },
            )
            return upstream_result

    def _dispatch_result_from_upstream(
        self,
        upstream_result: UpstreamCallResult,
        session_id: str,
        request_id: str | int | None,
    ) -> DispatchResult:
        if upstream_result.response is None:
            return DispatchResult(
                response=JsonRpcResponse(id=request_id, result={}),
                session_id=session_id,
            )
        if upstream_result.response.error is not None:
            return DispatchResult(
                response=JsonRpcResponse(
                    id=request_id,
                    error=upstream_result.response.error,
                ),
                session_id=session_id,
            )
        return DispatchResult(
            response=JsonRpcResponse(
                id=request_id,
                result=upstream_result.response.result,
            ),
            session_id=session_id,
        )

    async def _record_tool_call_audit(
        self,
        *,
        request: JsonRpcRequest,
        session: SessionRecord,
        request_context: RouterRequestContext,
        span_id: str | None,
        outcome: str,
        status_code: int,
        error_code: int | None,
        error_message: str | None,
        started_at: float,
        registered_tool: RegisteredTool | None = None,
        fallback_tool_name: str | None = None,
        traffic_decision: TrafficLimitDecision | None = None,
        server_id_override: str | None = None,
    ) -> None:
        tool_name = (
            registered_tool.name
            if registered_tool is not None
            else (fallback_tool_name or "unknown")
        )
        tool_version = (
            registered_tool.version if registered_tool is not None else "unresolved"
        )
        server_id = (
            server_id_override
            or (
                registered_tool.binding.server_id
                if registered_tool is not None
                else "unresolved"
            )
        )
        await self._audit_log.record_tool_call(
            trace_id=request_context.trace_id,
            span_id=span_id,
            session_id=session.session_id,
            request_id=request.id,
            tenant_id=session.tenant_id,
            principal_id=session.principal_id,
            roles=session.roles,
            tool_name=tool_name,
            tool_version=tool_version,
            server_id=server_id,
            outcome=outcome,
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            rate_limit_key=traffic_decision.key if traffic_decision is not None else None,
            remaining_tokens=(
                traffic_decision.remaining_tokens
                if traffic_decision is not None
                else None
            ),
            concurrency_limit=(
                traffic_decision.concurrency_limit
                if traffic_decision is not None
                else None
            ),
        )

    def _tool_call_outcome_from_fault(self, fault: JsonRpcFault) -> str:
        if int(fault.code) == int(JsonRpcErrorCode.INVALID_PARAMS):
            return "schema_invalid"
        if int(fault.code) == int(JsonRpcErrorCode.TOOL_NOT_FOUND):
            return "tool_not_found"
        if int(fault.code) == int(JsonRpcErrorCode.UPSTREAM_NOT_CONFIGURED):
            return "routing_error"
        if int(fault.code) == int(JsonRpcErrorCode.UPSTREAM_UNAVAILABLE):
            return "upstream_error"
        return "error"
