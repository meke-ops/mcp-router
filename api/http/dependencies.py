from dataclasses import replace
from typing import cast
from uuid import uuid4

from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from starlette.requests import HTTPConnection

from internal.auth import AuthenticatedPrincipal, AuthenticationError, JwtAuthenticator
from internal.container import ServiceContainer
from internal.context import RouterRequestContext
from internal.tracing import build_inbound_span_context


def get_services(connection: HTTPConnection) -> ServiceContainer:
    return cast(ServiceContainer, connection.app.state.services)


async def get_authenticated_principal(
    connection: HTTPConnection,
    services: ServiceContainer = Depends(get_services),
) -> AuthenticatedPrincipal | None:
    if not services.settings.auth_enabled:
        return None
    return await _authenticate_connection(connection, services)


async def require_control_plane_principal(
    connection: HTTPConnection,
    services: ServiceContainer = Depends(get_services),
) -> AuthenticatedPrincipal | None:
    if not services.settings.auth_enabled:
        return None
    principal = await _authenticate_connection(connection, services)
    if not any(role in services.settings.control_plane_allowed_roles for role in principal.roles):
        _raise_connection_error(
            connection,
            status_code=403,
            detail="Principal does not have control-plane access.",
        )
    return principal


def ensure_request_context(connection: HTTPConnection) -> RouterRequestContext:
    if hasattr(connection.state, "request_context"):
        return cast(RouterRequestContext, connection.state.request_context)

    request_id = connection.headers.get("X-Request-Id", str(uuid4()))
    inbound_trace_context = build_inbound_span_context(
        connection.headers.get("traceparent")
    )
    request_context = RouterRequestContext(
        request_id=request_id,
        trace_id=inbound_trace_context.trace_id,
        span_id=inbound_trace_context.span_id,
        parent_span_id=inbound_trace_context.parent_span_id,
        traceparent=inbound_trace_context.traceparent,
    )
    connection.state.request_context = request_context
    return request_context


async def _authenticate_connection(
    connection: HTTPConnection,
    services: ServiceContainer,
) -> AuthenticatedPrincipal:
    cached_principal = cast(
        AuthenticatedPrincipal | None,
        getattr(connection.state, "auth_principal", None),
    )
    if cached_principal is not None:
        return cached_principal

    request_context = ensure_request_context(connection)
    raw_authorization = connection.headers.get("Authorization")
    if raw_authorization is None:
        access_token = connection.query_params.get("access_token")
        if access_token:
            raw_authorization = f"Bearer {access_token}"

    authenticator = JwtAuthenticator(services.settings)
    try:
        principal = authenticator.authenticate_bearer_token(raw_authorization)
    except AuthenticationError as exc:
        _raise_connection_error(
            connection,
            status_code=exc.status_code,
            detail=exc.message,
        )

    connection.state.auth_principal = principal
    connection.state.request_context = replace(
        request_context,
        token_hash=principal.token_hash,
        authenticated_principal_id=principal.subject,
        authenticated_tenant_ids=principal.tenant_ids,
        authenticated_roles=principal.roles,
    )

    if not getattr(connection.state, "auth_audited", False):
        await services.audit_log.record_event(
            trace_id=connection.state.request_context.trace_id,
            span_id=connection.state.request_context.span_id,
            session_id=None,
            request_id=connection.state.request_context.request_id,
            tenant_id=principal.tenant_ids[0] if principal.tenant_ids else None,
            principal_id=principal.subject,
            tool_name=None,
            event_type="auth.authenticated",
            detail={
                "principalId": principal.subject,
                "tenantIds": list(principal.tenant_ids),
                "roles": list(principal.roles),
                "tokenHash": principal.token_hash,
            },
        )
        connection.state.auth_audited = True

    return principal


def _raise_connection_error(
    connection: HTTPConnection,
    *,
    status_code: int,
    detail: str,
) -> None:
    if isinstance(connection, WebSocket):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=detail,
        )
    raise HTTPException(status_code=status_code, detail=detail)
