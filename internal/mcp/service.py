from dataclasses import dataclass

from internal.audit import InMemoryAuditLog
from internal.config import Settings
from internal.context import RequestIdentity
from internal.mcp.errors import JsonRpcErrorCode, JsonRpcFault
from internal.mcp.models import JsonRpcRequest, JsonRpcResponse
from internal.policy import PolicyEngine, PolicyEvaluationContext
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
        audit_log: InMemoryAuditLog,
        upstream_gateway: UpstreamTransportGateway,
    ) -> None:
        self._settings = settings
        self._session_manager = session_manager
        self._tool_registry = tool_registry
        self._policy_engine = policy_engine
        self._audit_log = audit_log
        self._upstream_gateway = upstream_gateway
        self._arguments_schema_validator = ToolArgumentsSchemaValidator()

    async def handle_request(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
    ) -> DispatchResult:
        try:
            if request.method == "initialize":
                return await self._handle_initialize(request, session_id, identity)
            if request.method == "notifications/initialized":
                return await self._handle_initialized_notification(session_id, identity)
            if request.method == "tools/list":
                return await self._handle_tools_list(request, session_id, identity)
            if request.method == "tools/call":
                return await self._handle_tools_call(request, session_id, identity)
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
        await self._initialize_upstreams(session=session, request=request)

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
            )
        return DispatchResult(response=None, session_id=session.session_id, status_code=202)

    async def _handle_tools_list(
        self,
        request: JsonRpcRequest,
        session_id: str | None,
        identity: RequestIdentity,
    ) -> DispatchResult:
        self._require_request_id(request)
        session = await self._require_session(session_id, identity)
        tools = await self._list_available_tools(request=request, session=session)

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

        registered_tool = await self._tool_registry.get_tool(tool_name)
        if registered_tool is None:
            await self._refresh_tools_from_upstreams(request=request, session=session)
            registered_tool = await self._tool_registry.get_tool(tool_name)
        if registered_tool is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.TOOL_NOT_FOUND,
                message=f"Tool is not registered: {tool_name}",
            )
        policy_decision = await self._evaluate_tool_policy(
            request=request,
            session=session,
            registered_tool=registered_tool,
        )
        if policy_decision.effect == "deny":
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
        self._validate_tool_arguments(registered_tool=registered_tool, arguments=arguments)

        upstream_server = await self._tool_registry.get_upstream_server(
            registered_tool.binding.server_id
        )
        if upstream_server is None:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.UPSTREAM_NOT_CONFIGURED,
                message=f"Tool binding is missing an upstream server: {tool_name}",
            )

        upstream_result = await self._send_upstream_request(
            server=upstream_server,
            request=request,
            session=session,
        )
        return self._dispatch_result_from_upstream(
            upstream_result=upstream_result,
            session_id=session.session_id,
            request_id=request.id,
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
    ):
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
    ) -> None:
        for upstream_server in await self._tool_registry.list_upstream_servers():
            upstream_result = await self._send_upstream_request(
                server=upstream_server,
                request=JsonRpcRequest(
                    jsonrpc="2.0",
                    id=request.id,
                    method="initialize",
                    params=request.params,
                ),
                session=session,
            )
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
    ) -> list[RegisteredTool]:
        upstream_servers = await self._tool_registry.list_upstream_servers()
        if not upstream_servers:
            return await self._tool_registry.list_registered_tools()

        await self._refresh_tools_from_upstreams(request=request, session=session)
        return await self._tool_registry.list_registered_tools()

    async def _refresh_tools_from_upstreams(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
    ) -> None:
        discovered_tools: list[RegisteredTool] = []
        seen_tool_names: dict[str, str] = {}

        for upstream_server in await self._tool_registry.list_upstream_servers():
            upstream_result = await self._send_upstream_request(
                server=upstream_server,
                request=JsonRpcRequest(
                    jsonrpc="2.0",
                    id=request.id,
                    method="tools/list",
                    params={},
                ),
                session=session,
            )
            if upstream_result.response is None:
                raise JsonRpcFault(
                    code=JsonRpcErrorCode.INTERNAL_ERROR,
                    message=f"Upstream returned no tools/list response: {upstream_server.server_id}",
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
                    message=f"Upstream tools/list payload is invalid: {upstream_server.server_id}",
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
                message=f"tools/call arguments do not match schema for {registered_tool.name}",
                data={
                    **exc.to_payload(),
                    "tool": registered_tool.name,
                    "toolVersion": registered_tool.version,
                },
            ) from exc

    async def _evaluate_tool_policy(
        self,
        request: JsonRpcRequest,
        session: SessionRecord,
        registered_tool: RegisteredTool,
    ):
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
        return decision

    async def _send_upstream_request(
        self,
        server: UpstreamServerDefinition,
        request: JsonRpcRequest,
        session: SessionRecord,
    ) -> UpstreamCallResult:
        upstream_session_id = await self._session_manager.get_upstream_session(
            session_id=session.session_id,
            server_id=server.server_id,
        )
        try:
            upstream_result = await self._upstream_gateway.send(
                server=server,
                request=request,
                session_id=upstream_session_id,
                tenant_id=session.tenant_id,
                principal_id=session.principal_id,
            )
        except UpstreamTransportError as exc:
            raise JsonRpcFault(
                code=JsonRpcErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"Upstream transport failed: {server.server_id}",
                data={"detail": str(exc)},
            ) from exc

        if upstream_result.upstream_session_id:
            await self._session_manager.set_upstream_session(
                session_id=session.session_id,
                server_id=server.server_id,
                upstream_session_id=upstream_result.upstream_session_id,
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
