from dataclasses import asdict
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator

from api.http.dependencies import get_services, require_control_plane_principal
from internal.audit import (
    AuditEventRecord,
    PolicyDecisionAuditRecord,
    ToolCallAuditRecord,
)
from internal.auth import AuthenticatedPrincipal
from internal.container import ServiceContainer
from internal.context import RouterRequestContext
from internal.policy import PolicyObligation, PolicyRule
from internal.registry import (
    ToolDefinition,
    UpstreamServerDefinition,
    build_registered_tool,
)


router = APIRouter(tags=["control-plane"])


class PolicyObligationPayload(BaseModel):
    type: str
    parameters: dict[str, object] = Field(default_factory=dict)


class PolicyRulePayload(BaseModel):
    rule_id: str
    effect: str
    reason: str
    priority: int = 0
    tenant_ids: list[str] = Field(default_factory=list)
    principal_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    tool_versions: list[str] = Field(default_factory=list)
    obligations: list[PolicyObligationPayload] = Field(default_factory=list)


class ToolRegistrationPayload(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object] = Field(alias="inputSchema")
    output_schema: dict[str, object] | None = Field(default=None, alias="outputSchema")
    tags: list[str] = Field(default_factory=list)
    server_id: str = Field(alias="serverId")
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")


class UpstreamRegistrationPayload(BaseModel):
    server_id: str
    transport: str
    url: str | None = None
    endpoint_url: str | None = None
    command: str | list[str] | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 10.0
    discover_tools: bool = True
    fallback_server_ids: list[str] = Field(default_factory=list)
    retry_attempts: int = 0
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_seconds: float = 30.0
    origin_client: str | None = None
    origin_path: str | None = None
    managed_by: str | None = None
    last_imported_at: str | None = None

    @model_validator(mode="after")
    def normalize_command(self) -> "UpstreamRegistrationPayload":
        if isinstance(self.command, list):
            parts = [item for item in self.command if item]
            self.command = parts[0] if parts else None
            if parts[1:]:
                self.args = parts[1:]
        return self


@router.get("/tools")
async def list_tools(
    request: Request,
    refresh: bool = Query(default=False),
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    if refresh:
        await services.mcp_service.refresh_registry(_request_context(request))

    tools = await services.tool_registry.list_registered_tools()
    return {
        "items": [
            {
                "name": tool.name,
                "version": tool.version,
                "serverId": tool.binding.server_id,
                "timeoutSeconds": tool.binding.timeout_seconds,
                "definition": tool.definition.to_mcp_payload(),
                "versions": list(tool.versions.keys()),
            }
            for tool in tools
        ]
    }


@router.post("/tools/refresh")
async def refresh_tools(
    request: Request,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    tools = await services.mcp_service.refresh_registry(_request_context(request))
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.tools.refreshed",
        detail={"count": len(tools)},
    )
    return {"count": len(tools)}


@router.post("/tools/register")
async def register_tool(
    request: Request,
    payload: ToolRegistrationPayload,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    upstream_server = await services.tool_registry.get_upstream_server(payload.server_id)
    if upstream_server is None:
        raise HTTPException(status_code=404, detail="Upstream server not found.")

    registered_tool = build_registered_tool(
        definition=ToolDefinition(
            name=payload.name,
            description=payload.description,
            input_schema=payload.input_schema,
            output_schema=payload.output_schema,
            tags=tuple(payload.tags),
        ),
        server_id=payload.server_id,
        timeout_seconds=payload.timeout_seconds,
    )
    await services.tool_registry.upsert_tool(registered_tool)
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.tool.registered",
        detail={"tool": payload.name, "serverId": payload.server_id},
    )
    return {
        "item": {
            "name": registered_tool.name,
            "version": registered_tool.version,
            "serverId": registered_tool.binding.server_id,
        }
    }


@router.delete("/tools/{tool_name}")
async def delete_tool(
    request: Request,
    tool_name: str,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    deleted = await services.tool_registry.delete_tool(tool_name)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Tool not found in manual registry.")
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.tool.deleted",
        detail={"tool": tool_name},
    )
    return {"deleted": tool_name}


@router.get("/upstreams")
async def list_upstreams(
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    upstreams = await services.tool_registry.list_upstream_servers()
    return {
        "items": [
            {
                "serverId": upstream.server_id,
                "transport": upstream.transport,
                "url": upstream.url,
                "endpointUrl": upstream.endpoint_url,
                "command": upstream.command,
                "args": list(upstream.args),
                "env": upstream.env,
                "headers": upstream.headers,
                "timeoutSeconds": upstream.timeout_seconds,
                "discoverTools": upstream.discover_tools,
                "fallbackServerIds": list(upstream.fallback_server_ids),
                "retryAttempts": upstream.retry_attempts,
                "circuitBreakerFailureThreshold": upstream.circuit_breaker_failure_threshold,
                "circuitBreakerRecoverySeconds": upstream.circuit_breaker_recovery_seconds,
                "originClient": upstream.origin_client,
                "originPath": upstream.origin_path,
                "managedBy": upstream.managed_by,
                "lastImportedAt": upstream.last_imported_at,
            }
            for upstream in upstreams
        ]
    }


@router.post("/upstreams")
async def register_upstream(
    request: Request,
    payload: UpstreamRegistrationPayload,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    upstream = UpstreamServerDefinition(
        server_id=payload.server_id,
        transport=payload.transport,  # type: ignore[arg-type]
        url=payload.url or payload.endpoint_url,
        command=payload.command if isinstance(payload.command, str) else None,
        args=tuple(payload.args),
        env=payload.env,
        headers=payload.headers,
        timeout_seconds=payload.timeout_seconds,
        discover_tools=payload.discover_tools,
        fallback_server_ids=tuple(payload.fallback_server_ids),
        retry_attempts=payload.retry_attempts,
        circuit_breaker_failure_threshold=payload.circuit_breaker_failure_threshold,
        circuit_breaker_recovery_seconds=payload.circuit_breaker_recovery_seconds,
        origin_client=payload.origin_client,
        origin_path=payload.origin_path,
        managed_by=payload.managed_by or "dashboard",
        last_imported_at=payload.last_imported_at,
    )
    await services.tool_registry.upsert_upstream_server(upstream)
    services.state_store.upsert_upstream(upstream)
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.upstream.registered",
        detail={"serverId": payload.server_id, "transport": payload.transport},
    )
    return {"item": {"serverId": upstream.server_id}}


@router.delete("/upstreams/{server_id}")
async def delete_upstream(
    request: Request,
    server_id: str,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    deleted = await services.tool_registry.delete_upstream_server(server_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Upstream not found.")
    services.state_store.delete_upstream(server_id)
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.upstream.deleted",
        detail={"serverId": server_id},
    )
    return {"deleted": server_id}


@router.get("/policies")
async def list_policies(
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    return {
        "items": [_serialize_policy_rule(rule) for rule in services.policy_store.list_rules()]
    }


@router.post("/policies")
async def upsert_policy(
    request: Request,
    payload: PolicyRulePayload,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    rule = PolicyRule(
        rule_id=payload.rule_id,
        effect=payload.effect,  # type: ignore[arg-type]
        reason=payload.reason,
        priority=payload.priority,
        tenant_ids=tuple(payload.tenant_ids),
        principal_ids=tuple(payload.principal_ids),
        roles=tuple(payload.roles),
        tool_names=tuple(payload.tool_names),
        tool_versions=tuple(payload.tool_versions),
        obligations=tuple(
            PolicyObligation(
                obligation_type=item.type,
                parameters=item.parameters,
            )
            for item in payload.obligations
        ),
    )
    await services.policy_store.upsert_rule(rule)
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.policy.upserted",
        detail={"ruleId": payload.rule_id, "effect": payload.effect},
    )
    return {"item": _serialize_policy_rule(rule)}


@router.delete("/policies/{rule_id}")
async def delete_policy(
    request: Request,
    rule_id: str,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    deleted = await services.policy_store.delete_rule(rule_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Policy not found.")
    await _record_control_event(
        services=services,
        request_context=_request_context(request),
        event_type="control.policy.deleted",
        detail={"ruleId": rule_id},
    )
    return {"deleted": rule_id}


@router.get("/audit/policy-decisions")
async def list_policy_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    items = await services.audit_log.list_policy_decisions()
    return {"items": [_serialize_dataclass(item) for item in items[-limit:][::-1]]}


@router.get("/audit/tool-calls")
async def list_tool_calls(
    limit: int = Query(default=50, ge=1, le=500),
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    items = await services.audit_log.list_tool_calls()
    return {"items": [_serialize_dataclass(item) for item in items[-limit:][::-1]]}


@router.get("/audit/events")
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    items = await services.audit_log.list_audit_events()
    if event_type:
        items = [item for item in items if item.event_type == event_type]
    return {"items": [_serialize_dataclass(item) for item in items[-limit:][::-1]]}


@router.websocket("/events/ws")
async def events_websocket(
    websocket: WebSocket,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> None:
    await websocket.accept()
    queue = await services.audit_log.subscribe_events()
    try:
        recent_events = await services.audit_log.list_audit_events()
        for event in recent_events[-10:]:
            await websocket.send_json(_serialize_dataclass(event))
        while True:
            event = await queue.get()
            await websocket.send_json(_serialize_dataclass(event))
    except WebSocketDisconnect:
        pass
    finally:
        await services.audit_log.unsubscribe_events(queue)


def _serialize_policy_rule(rule: PolicyRule) -> dict[str, object]:
    return {
        "ruleId": rule.rule_id,
        "effect": rule.effect,
        "reason": rule.reason,
        "priority": rule.priority,
        "tenantIds": list(rule.tenant_ids),
        "principalIds": list(rule.principal_ids),
        "roles": list(rule.roles),
        "toolNames": list(rule.tool_names),
        "toolVersions": list(rule.tool_versions),
        "obligations": [obligation.to_payload() for obligation in rule.obligations],
    }


def _serialize_dataclass(
    item: AuditEventRecord | PolicyDecisionAuditRecord | ToolCallAuditRecord,
) -> dict[str, object]:
    payload = asdict(item)
    for key, value in list(payload.items()):
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
    return cast(dict[str, object], payload)


def _request_context(request: Request) -> RouterRequestContext:
    return cast(RouterRequestContext, request.state.request_context)


async def _record_control_event(
    *,
    services: ServiceContainer,
    request_context: RouterRequestContext,
    event_type: str,
    detail: dict[str, object],
) -> None:
    await services.audit_log.record_event(
        trace_id=request_context.trace_id,
        span_id=request_context.span_id,
        session_id=None,
        request_id=request_context.request_id,
        tenant_id=(
            request_context.authenticated_tenant_ids[0]
            if request_context.authenticated_tenant_ids
            else "control-plane"
        ),
        principal_id=request_context.authenticated_principal_id or "dashboard",
        tool_name=None,
        event_type=event_type,
        detail=detail,
    )
