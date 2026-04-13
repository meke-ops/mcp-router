from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from api.http.dependencies import get_authenticated_principal, get_services
from internal.auth import AuthenticatedPrincipal
from internal.container import ServiceContainer
from internal.context import RequestIdentity, RouterRequestContext
from internal.mcp.models import JsonRpcRequest

router = APIRouter(tags=["mcp"])


def _parse_roles_header(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    roles = [part.strip() for part in raw_value.split(",")]
    return tuple(role for role in roles if role)


@router.post("")
async def handle_mcp(
    http_request: Request,
    request: JsonRpcRequest,
    services: ServiceContainer = Depends(get_services),
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal),
    mcp_session_id: str | None = Header(default=None, alias="MCP-Session-Id"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_principal_id: str | None = Header(default=None, alias="X-Principal-Id"),
    x_principal_roles: str | None = Header(default=None, alias="X-Principal-Roles"),
) -> Response:
    request_context: RouterRequestContext = http_request.state.request_context
    dispatch_result = await services.mcp_service.handle_request(
        request=request,
        session_id=mcp_session_id,
        identity=_resolve_identity(
            principal=principal,
            x_tenant_id=x_tenant_id,
            x_principal_id=x_principal_id,
            x_principal_roles=x_principal_roles,
        ),
        request_context=request_context,
    )

    if dispatch_result.response is None:
        response: Response = Response(status_code=dispatch_result.status_code)
    else:
        response = JSONResponse(
            status_code=dispatch_result.status_code,
            content=dispatch_result.response.model_dump(mode="json", exclude_none=True),
        )

    if dispatch_result.session_id:
        response.headers["MCP-Session-Id"] = dispatch_result.session_id

    return response


def _resolve_identity(
    *,
    principal: AuthenticatedPrincipal | None,
    x_tenant_id: str | None,
    x_principal_id: str | None,
    x_principal_roles: str | None,
) -> RequestIdentity:
    parsed_roles = _parse_roles_header(x_principal_roles)
    if principal is None:
        return RequestIdentity(
            tenant_id=x_tenant_id or "public",
            principal_id=x_principal_id or "anonymous",
            roles=parsed_roles,
            tenant_supplied=x_tenant_id is not None,
            principal_supplied=x_principal_id is not None,
            roles_supplied=x_principal_roles is not None,
        )

    if x_principal_id is not None and x_principal_id != principal.subject:
        raise HTTPException(
            status_code=403,
            detail="X-Principal-Id does not match the authenticated principal.",
        )
    if x_principal_roles is not None and parsed_roles != principal.roles:
        raise HTTPException(
            status_code=403,
            detail="X-Principal-Roles does not match the authenticated principal roles.",
        )

    return RequestIdentity(
        tenant_id=_resolve_authenticated_tenant(principal, x_tenant_id),
        principal_id=principal.subject,
        roles=principal.roles,
        tenant_supplied=True,
        principal_supplied=True,
        roles_supplied=True,
    )


def _resolve_authenticated_tenant(
    principal: AuthenticatedPrincipal,
    x_tenant_id: str | None,
) -> str:
    allowed_tenants = set(principal.tenant_ids)
    wildcard_access = "*" in allowed_tenants

    if x_tenant_id is not None:
        if not wildcard_access and x_tenant_id not in allowed_tenants:
            raise HTTPException(
                status_code=403,
                detail="X-Tenant-Id is not allowed for this token.",
            )
        return x_tenant_id

    if wildcard_access or len(principal.tenant_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail="X-Tenant-Id is required when the token covers multiple tenants.",
        )

    return principal.tenant_ids[0]
