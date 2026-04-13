import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from internal.policy import PolicyObligation


@dataclass(slots=True, frozen=True)
class PolicyDecisionAuditRecord:
    event_id: str
    recorded_at: datetime
    session_id: str
    request_id: str | int | None
    tenant_id: str
    principal_id: str
    roles: tuple[str, ...]
    tool_name: str
    tool_version: str
    server_id: str
    decision: str
    reason: str
    rule_id: str | None
    is_default: bool
    obligations: tuple[PolicyObligation, ...]


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._policy_records: list[PolicyDecisionAuditRecord] = []
        self._lock = asyncio.Lock()

    async def record_policy_decision(
        self,
        *,
        session_id: str,
        request_id: str | int | None,
        tenant_id: str,
        principal_id: str,
        roles: tuple[str, ...],
        tool_name: str,
        tool_version: str,
        server_id: str,
        decision: str,
        reason: str,
        rule_id: str | None,
        is_default: bool,
        obligations: tuple[PolicyObligation, ...],
    ) -> PolicyDecisionAuditRecord:
        record = PolicyDecisionAuditRecord(
            event_id=str(uuid4()),
            recorded_at=datetime.now(UTC),
            session_id=session_id,
            request_id=request_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            roles=roles,
            tool_name=tool_name,
            tool_version=tool_version,
            server_id=server_id,
            decision=decision,
            reason=reason,
            rule_id=rule_id,
            is_default=is_default,
            obligations=obligations,
        )
        async with self._lock:
            self._policy_records.append(record)
        return record

    async def list_policy_decisions(self) -> list[PolicyDecisionAuditRecord]:
        async with self._lock:
            return list(self._policy_records)
