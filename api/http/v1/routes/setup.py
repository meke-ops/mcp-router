from typing import cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.http.dependencies import get_authenticated_principal, get_services, require_control_plane_principal
from api.http.mcp import _parse_roles_header
from internal.auth import AuthenticatedPrincipal
from internal.container import ServiceContainer
from internal.context import RequestIdentity, RouterRequestContext


router = APIRouter(prefix="/setup", tags=["setup"])


class ClientPreviewPayload(BaseModel):
    client_id: str = Field(alias="clientId")
    scope: str = "user"
    mcp_url: str | None = Field(default=None, alias="mcpUrl")
    token: str | None = None
    config_path: str | None = Field(default=None, alias="configPath")
    server_name: str = Field(default="mcp-router", alias="serverName")


class ClientApplyPayload(ClientPreviewPayload):
    pass


class ImportPayload(BaseModel):
    candidate_ids: list[str] = Field(alias="candidateIds")
    refresh: bool = True


class VerifyPayload(BaseModel):
    auth_mode: str = Field(default="none", alias="authMode")
    tenant_id: str | None = Field(default=None, alias="tenantId")
    principal_id: str | None = Field(default=None, alias="principalId")
    roles: str | None = None


@router.get("/clients")
async def list_clients(
    request: Request,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    return {
        "items": services.setup_service.list_clients(),
        "authEnabled": services.settings.auth_enabled,
        "defaultMcpUrl": str(request.base_url).rstrip("/") + "/mcp",
        "statePath": str(services.state_store.state_path),
    }


@router.post("/client-preview")
async def client_preview(
    request: Request,
    payload: ClientPreviewPayload,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    preview = services.setup_service.preview_client(
        client_id=payload.client_id,
        scope=payload.scope,
        mcp_url=payload.mcp_url or (str(request.base_url).rstrip("/") + "/mcp"),
        token=payload.token,
        config_path=payload.config_path,
        server_name=payload.server_name,
    )
    await _record_setup_event(
        request=request,
        services=services,
        event_type="setup.client.previewed",
        detail={"clientId": payload.client_id, "scope": payload.scope},
    )
    return {"item": preview.to_payload()}


@router.post("/client-apply")
async def client_apply(
    request: Request,
    payload: ClientApplyPayload,
    services: ServiceContainer = Depends(get_services),
    principal: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    preview = services.setup_service.preview_client(
        client_id=payload.client_id,
        scope=payload.scope,
        mcp_url=payload.mcp_url or (str(request.base_url).rstrip("/") + "/mcp"),
        token=payload.token,
        config_path=payload.config_path,
        server_name=payload.server_name,
    )
    applied = services.setup_service.apply_client_preview(preview)
    verification = await services.setup_service.verify_router(
        auth_mode=applied.auth_mode,
        request_context=_request_context(request),
        identity=_verification_identity(principal),
    )
    await _record_setup_event(
        request=request,
        services=services,
        event_type="setup.client.applied",
        detail={"clientId": payload.client_id, "scope": payload.scope},
    )
    return {
        "item": applied.to_payload(),
        "verification": verification.to_payload(),
    }


@router.get("/discovery")
async def setup_discovery(
    request: Request,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    candidates = services.setup_service.discover_candidates()
    await _record_setup_event(
        request=request,
        services=services,
        event_type="setup.discovery.completed",
        detail={"count": len(candidates)},
    )
    return {"items": [candidate.to_payload() for candidate in candidates]}


@router.post("/import")
async def setup_import(
    request: Request,
    payload: ImportPayload,
    services: ServiceContainer = Depends(get_services),
    _: AuthenticatedPrincipal | None = Depends(require_control_plane_principal),
) -> dict[str, object]:
    result = await services.setup_service.import_candidates(
        candidate_ids=payload.candidate_ids,
        refresh=payload.refresh,
        request_context=_request_context(request),
    )
    await _record_setup_event(
        request=request,
        services=services,
        event_type="setup.import.completed",
        detail=result.to_payload(),
    )
    return {"item": result.to_payload()}


@router.post("/verify")
async def setup_verify(
    request: Request,
    payload: VerifyPayload,
    services: ServiceContainer = Depends(get_services),
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal),
) -> dict[str, object]:
    verification = await services.setup_service.verify_router(
        auth_mode=payload.auth_mode,
        request_context=_request_context(request),
        identity=_verification_identity(
            principal,
            tenant_id=payload.tenant_id,
            principal_id=payload.principal_id,
            roles=payload.roles,
        ),
    )
    await _record_setup_event(
        request=request,
        services=services,
        event_type="setup.verify.completed",
        detail=verification.to_payload(),
    )
    return {"item": verification.to_payload()}


def _verification_identity(
    principal: AuthenticatedPrincipal | None,
    *,
    tenant_id: str | None = None,
    principal_id: str | None = None,
    roles: str | None = None,
) -> RequestIdentity:
    if principal is None:
        return RequestIdentity(
            tenant_id=tenant_id or "public",
            principal_id=principal_id or "dashboard",
            roles=_parse_roles_header(roles),
        )
    resolved_tenant = tenant_id or (principal.tenant_ids[0] if principal.tenant_ids else "public")
    return RequestIdentity(
        tenant_id=resolved_tenant,
        principal_id=principal.subject,
        roles=principal.roles,
        tenant_supplied=True,
        principal_supplied=True,
        roles_supplied=True,
    )


def _request_context(request: Request) -> RouterRequestContext:
    return cast(RouterRequestContext, request.state.request_context)


async def _record_setup_event(
    *,
    request: Request,
    services: ServiceContainer,
    event_type: str,
    detail: dict[str, object],
) -> None:
    request_context = _request_context(request)
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
