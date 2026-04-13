import asyncio
from dataclasses import dataclass
import time
from typing import Literal


CircuitState = Literal["closed", "open", "half_open"]


@dataclass(slots=True, frozen=True)
class CircuitDecision:
    allowed: bool
    state: CircuitState
    retry_after_seconds: float | None = None

    def to_payload(self) -> dict[str, object | None]:
        return {
            "allowed": self.allowed,
            "state": self.state,
            "retryAfterSeconds": self.retry_after_seconds,
        }


@dataclass(slots=True)
class _CircuitRecord:
    state: CircuitState = "closed"
    consecutive_failures: int = 0
    opened_until_monotonic: float | None = None
    half_open_in_flight: bool = False


class InMemoryCircuitBreakerStore:
    def __init__(self) -> None:
        self._records: dict[str, _CircuitRecord] = {}
        self._lock = asyncio.Lock()

    async def before_request(
        self,
        server_id: str,
    ) -> CircuitDecision:
        now = time.monotonic()
        async with self._lock:
            record = self._records.setdefault(server_id, _CircuitRecord())
            if record.state == "open":
                if record.opened_until_monotonic is not None and now < record.opened_until_monotonic:
                    return CircuitDecision(
                        allowed=False,
                        state="open",
                        retry_after_seconds=round(
                            record.opened_until_monotonic - now,
                            3,
                        ),
                    )
                record.state = "half_open"
                record.opened_until_monotonic = None
                record.half_open_in_flight = True
                return CircuitDecision(allowed=True, state="half_open")
            if record.state == "half_open" and record.half_open_in_flight:
                return CircuitDecision(
                    allowed=False,
                    state="half_open",
                    retry_after_seconds=0.0,
                )
            if record.state == "half_open":
                record.half_open_in_flight = True
                return CircuitDecision(allowed=True, state="half_open")
            return CircuitDecision(allowed=True, state="closed")

    async def record_success(self, server_id: str) -> None:
        async with self._lock:
            record = self._records.setdefault(server_id, _CircuitRecord())
            record.state = "closed"
            record.consecutive_failures = 0
            record.opened_until_monotonic = None
            record.half_open_in_flight = False

    async def record_failure(
        self,
        server_id: str,
        *,
        failure_threshold: int,
        recovery_timeout_seconds: float,
    ) -> CircuitDecision:
        now = time.monotonic()
        async with self._lock:
            record = self._records.setdefault(server_id, _CircuitRecord())
            record.half_open_in_flight = False
            record.consecutive_failures += 1
            if record.state == "half_open" or record.consecutive_failures >= max(failure_threshold, 1):
                record.state = "open"
                record.opened_until_monotonic = now + max(recovery_timeout_seconds, 0.0)
                return CircuitDecision(
                    allowed=False,
                    state="open",
                    retry_after_seconds=round(max(recovery_timeout_seconds, 0.0), 3),
                )
            record.state = "closed"
            return CircuitDecision(allowed=True, state="closed")
