from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestIdentity:
    tenant_id: str
    principal_id: str
    roles: tuple[str, ...] = ()
    tenant_supplied: bool = False
    principal_supplied: bool = False
    roles_supplied: bool = False
