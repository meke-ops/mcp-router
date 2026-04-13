from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestIdentity:
    tenant_id: str
    principal_id: str
    roles: tuple[str, ...] = ()
    tenant_supplied: bool = False
    principal_supplied: bool = False
    roles_supplied: bool = False


@dataclass(slots=True, frozen=True)
class RouterRequestContext:
    request_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    traceparent: str
    token_hash: str | None = None
    authenticated_principal_id: str | None = None
    authenticated_tenant_ids: tuple[str, ...] = ()
    authenticated_roles: tuple[str, ...] = ()
