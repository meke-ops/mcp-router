import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
import secrets
from typing import Any


TRACE_VERSION = "00"
TRACE_FLAGS = "01"


@dataclass(slots=True, frozen=True)
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    trace_flags: str = TRACE_FLAGS

    @property
    def traceparent(self) -> str:
        return (
            f"{TRACE_VERSION}-{self.trace_id}-{self.span_id}-{self.trace_flags}"
        )


@dataclass(slots=True)
class SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    ended_at: datetime | None = None
    status: str = "in_progress"
    error: str | None = None


def build_inbound_span_context(traceparent_header: str | None) -> SpanContext:
    trace_id: str | None = None
    parent_span_id: str | None = None
    trace_flags = TRACE_FLAGS

    if traceparent_header:
        parsed = _parse_traceparent(traceparent_header)
        if parsed is not None:
            trace_id, parent_span_id, trace_flags = parsed

    return SpanContext(
        trace_id=trace_id or _generate_trace_id(),
        span_id=_generate_span_id(),
        parent_span_id=parent_span_id,
        trace_flags=trace_flags,
    )


class InMemoryTraceRecorder:
    def __init__(self) -> None:
        self._records: list[SpanRecord] = []
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        span_context: SpanContext | None = None,
    ):
        context = span_context or SpanContext(
            trace_id=trace_id or _generate_trace_id(),
            span_id=_generate_span_id(),
            parent_span_id=parent_span_id,
        )
        record = SpanRecord(
            trace_id=context.trace_id,
            span_id=context.span_id,
            parent_span_id=context.parent_span_id,
            name=name,
            started_at=datetime.now(UTC),
            attributes=dict(attributes or {}),
        )
        async with self._lock:
            self._records.append(record)
        try:
            yield context
        except Exception as exc:
            record.status = "error"
            record.error = str(exc)
            raise
        else:
            record.status = "ok"
        finally:
            record.ended_at = datetime.now(UTC)

    async def list_spans(self) -> list[SpanRecord]:
        async with self._lock:
            return list(self._records)


def _parse_traceparent(header_value: str) -> tuple[str, str, str] | None:
    parts = header_value.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, trace_flags = parts
    if version != TRACE_VERSION:
        return None
    if not _is_valid_hex(trace_id, expected_length=32):
        return None
    if not _is_valid_hex(span_id, expected_length=16):
        return None
    if not _is_valid_hex(trace_flags, expected_length=2):
        return None
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return trace_id, span_id, trace_flags


def _is_valid_hex(value: str, *, expected_length: int) -> bool:
    if len(value) != expected_length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _generate_trace_id() -> str:
    return secrets.token_hex(16)


def _generate_span_id() -> str:
    return secrets.token_hex(8)
