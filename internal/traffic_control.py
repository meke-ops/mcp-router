import asyncio
from dataclasses import dataclass
import time


@dataclass(slots=True, frozen=True)
class TrafficControlContext:
    tenant_id: str
    principal_id: str
    tool_name: str


@dataclass(slots=True, frozen=True)
class TrafficLimitDecision:
    allowed: bool
    reason: str
    limit_type: str
    key: str
    retry_after_seconds: float | None = None
    remaining_tokens: float | None = None
    active_count: int | None = None
    concurrency_limit: int | None = None

    def to_payload(self) -> dict[str, object | None]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "limitType": self.limit_type,
            "key": self.key,
            "retryAfterSeconds": self.retry_after_seconds,
            "remainingTokens": self.remaining_tokens,
            "activeCount": self.active_count,
            "concurrencyLimit": self.concurrency_limit,
        }


@dataclass(slots=True)
class _TokenBucketState:
    tokens: float
    last_refill_monotonic: float


class TrafficControlLease:
    def __init__(self, controller: "InMemoryTrafficController", key: str) -> None:
        self._controller = controller
        self._key = key
        self._released = False

    async def release(self) -> int:
        if self._released:
            return await self._controller.current_active_count(self._key)
        self._released = True
        return await self._controller.release(self._key)


class InMemoryTrafficController:
    def __init__(
        self,
        *,
        rate_limit_capacity: int,
        rate_limit_refill_rate: float,
        concurrency_limit: int,
    ) -> None:
        self._rate_limit_capacity = max(rate_limit_capacity, 1)
        self._rate_limit_refill_rate = max(rate_limit_refill_rate, 0.0)
        self._concurrency_limit = max(concurrency_limit, 1)
        self._buckets: dict[str, _TokenBucketState] = {}
        self._active_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        context: TrafficControlContext,
    ) -> tuple[TrafficLimitDecision, TrafficControlLease | None]:
        key = self._key_for(context)
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _TokenBucketState(
                    tokens=float(self._rate_limit_capacity),
                    last_refill_monotonic=now,
                )
                self._buckets[key] = bucket

            self._refill(bucket=bucket, now=now)
            if bucket.tokens < 1.0:
                return (
                    TrafficLimitDecision(
                        allowed=False,
                        reason="Rate limit exceeded for this tenant/principal/tool combination.",
                        limit_type="rate_limit",
                        key=key,
                        retry_after_seconds=self._retry_after_seconds(bucket.tokens),
                        remaining_tokens=max(bucket.tokens, 0.0),
                        active_count=self._active_counts.get(key, 0),
                        concurrency_limit=self._concurrency_limit,
                    ),
                    None,
                )

            active_count = self._active_counts.get(key, 0)
            if active_count >= self._concurrency_limit:
                return (
                    TrafficLimitDecision(
                        allowed=False,
                        reason="Concurrency limit exceeded for this tenant/principal/tool combination.",
                        limit_type="concurrency",
                        key=key,
                        remaining_tokens=bucket.tokens,
                        active_count=active_count,
                        concurrency_limit=self._concurrency_limit,
                    ),
                    None,
                )

            bucket.tokens -= 1.0
            self._active_counts[key] = active_count + 1
            return (
                TrafficLimitDecision(
                    allowed=True,
                    reason="Traffic control checks passed.",
                    limit_type="allow",
                    key=key,
                    remaining_tokens=bucket.tokens,
                    active_count=self._active_counts[key],
                    concurrency_limit=self._concurrency_limit,
                ),
                TrafficControlLease(self, key),
            )

    async def release(self, key: str) -> int:
        async with self._lock:
            current = self._active_counts.get(key, 0)
            if current <= 1:
                self._active_counts.pop(key, None)
                return 0
            self._active_counts[key] = current - 1
            return self._active_counts[key]

    async def current_active_count(self, key: str) -> int:
        async with self._lock:
            return self._active_counts.get(key, 0)

    def _refill(self, *, bucket: _TokenBucketState, now: float) -> None:
        elapsed = max(now - bucket.last_refill_monotonic, 0.0)
        if elapsed <= 0:
            return
        bucket.tokens = min(
            float(self._rate_limit_capacity),
            bucket.tokens + (elapsed * self._rate_limit_refill_rate),
        )
        bucket.last_refill_monotonic = now

    def _retry_after_seconds(self, tokens: float) -> float | None:
        if self._rate_limit_refill_rate <= 0:
            return None
        missing_tokens = max(1.0 - tokens, 0.0)
        return round(missing_tokens / self._rate_limit_refill_rate, 3)

    def _key_for(self, context: TrafficControlContext) -> str:
        return (
            f"tenant:{context.tenant_id}|principal:{context.principal_id}|tool:{context.tool_name}"
        )
