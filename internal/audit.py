import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from internal.policy import PolicyObligation


@dataclass(slots=True, frozen=True)
class PolicyDecisionAuditRecord:
    event_id: str
    recorded_at: datetime
    trace_id: str
    span_id: str | None
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


@dataclass(slots=True, frozen=True)
class ToolCallAuditRecord:
    event_id: str
    recorded_at: datetime
    trace_id: str
    span_id: str | None
    session_id: str
    request_id: str | int | None
    tenant_id: str
    principal_id: str
    roles: tuple[str, ...]
    tool_name: str
    tool_version: str
    server_id: str
    outcome: str
    status_code: int
    error_code: int | None
    error_message: str | None
    duration_ms: float
    rate_limit_key: str | None
    remaining_tokens: float | None
    concurrency_limit: int | None


@dataclass(slots=True, frozen=True)
class AuditEventRecord:
    event_id: str
    recorded_at: datetime
    trace_id: str
    span_id: str | None
    session_id: str | None
    request_id: str | int | None
    tenant_id: str | None
    principal_id: str | None
    tool_name: str | None
    event_type: str
    detail: dict[str, Any]


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._policy_records: list[PolicyDecisionAuditRecord] = []
        self._tool_call_records: list[ToolCallAuditRecord] = []
        self._event_records: list[AuditEventRecord] = []
        self._lock = asyncio.Lock()

    async def record_policy_decision(
        self,
        *,
        trace_id: str,
        span_id: str | None,
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
            trace_id=trace_id,
            span_id=span_id,
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

    async def record_tool_call(
        self,
        *,
        trace_id: str,
        span_id: str | None,
        session_id: str,
        request_id: str | int | None,
        tenant_id: str,
        principal_id: str,
        roles: tuple[str, ...],
        tool_name: str,
        tool_version: str,
        server_id: str,
        outcome: str,
        status_code: int,
        error_code: int | None,
        error_message: str | None,
        duration_ms: float,
        rate_limit_key: str | None,
        remaining_tokens: float | None,
        concurrency_limit: int | None,
    ) -> ToolCallAuditRecord:
        record = ToolCallAuditRecord(
            event_id=str(uuid4()),
            recorded_at=datetime.now(UTC),
            trace_id=trace_id,
            span_id=span_id,
            session_id=session_id,
            request_id=request_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            roles=roles,
            tool_name=tool_name,
            tool_version=tool_version,
            server_id=server_id,
            outcome=outcome,
            status_code=status_code,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
            rate_limit_key=rate_limit_key,
            remaining_tokens=remaining_tokens,
            concurrency_limit=concurrency_limit,
        )
        async with self._lock:
            self._tool_call_records.append(record)
        return record

    async def record_event(
        self,
        *,
        trace_id: str,
        span_id: str | None,
        session_id: str | None,
        request_id: str | int | None,
        tenant_id: str | None,
        principal_id: str | None,
        tool_name: str | None,
        event_type: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditEventRecord:
        record = AuditEventRecord(
            event_id=str(uuid4()),
            recorded_at=datetime.now(UTC),
            trace_id=trace_id,
            span_id=span_id,
            session_id=session_id,
            request_id=request_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            tool_name=tool_name,
            event_type=event_type,
            detail=dict(detail or {}),
        )
        async with self._lock:
            self._event_records.append(record)
        return record

    async def list_policy_decisions(self) -> list[PolicyDecisionAuditRecord]:
        async with self._lock:
            return list(self._policy_records)

    async def list_tool_calls(self) -> list[ToolCallAuditRecord]:
        async with self._lock:
            return list(self._tool_call_records)

    async def list_audit_events(self) -> list[AuditEventRecord]:
        async with self._lock:
            return list(self._event_records)
