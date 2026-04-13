from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestIdentity:
    tenant_id: str
    principal_id: str
    tenant_supplied: bool = False
    principal_supplied: bool = False
