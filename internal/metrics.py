import asyncio
from dataclasses import dataclass
from time import time
from typing import Any

from internal.config import Settings


@dataclass(slots=True)
class _DurationMetric:
    count: int = 0
    total_seconds: float = 0.0


class InMemoryMetricsRecorder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._started_at = time()
        self._http_request_totals: dict[tuple[str, str, int], int] = {}
        self._http_request_durations: dict[tuple[str, str], _DurationMetric] = {}
        self._lock = asyncio.Lock()

    async def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        async with self._lock:
            request_key = (method, path, status_code)
            self._http_request_totals[request_key] = (
                self._http_request_totals.get(request_key, 0) + 1
            )
            duration_key = (method, path)
            duration_metric = self._http_request_durations.setdefault(
                duration_key,
                _DurationMetric(),
            )
            duration_metric.count += 1
            duration_metric.total_seconds += duration_seconds

    async def render_prometheus(
        self,
        *,
        readiness: dict[str, Any] | None = None,
    ) -> str:
        async with self._lock:
            http_request_totals = dict(self._http_request_totals)
            http_request_durations = {
                key: _DurationMetric(
                    count=value.count,
                    total_seconds=value.total_seconds,
                )
                for key, value in self._http_request_durations.items()
            }

        lines = [
            "# HELP mcp_router_build_info Static build and environment information.",
            "# TYPE mcp_router_build_info gauge",
            (
                "mcp_router_build_info"
                f'{{service="{self._settings.app_name}",'
                f'environment="{self._settings.app_env}",'
                f'version="{self._settings.app_version}"}} 1'
            ),
            "# HELP mcp_router_uptime_seconds Process uptime in seconds.",
            "# TYPE mcp_router_uptime_seconds gauge",
            f"mcp_router_uptime_seconds {time() - self._started_at:.6f}",
            "# HELP mcp_router_http_requests_total Total HTTP requests handled.",
            "# TYPE mcp_router_http_requests_total counter",
        ]

        for (method, path, status_code), count in sorted(http_request_totals.items()):
            lines.append(
                "mcp_router_http_requests_total"
                f'{{method="{method}",path="{path}",status_code="{status_code}"}} '
                f"{count}"
            )

        lines.extend(
            [
                "# HELP mcp_router_http_request_duration_seconds "
                "Total duration and count for HTTP requests.",
                "# TYPE mcp_router_http_request_duration_seconds summary",
            ]
        )
        for (method, path), metric in sorted(http_request_durations.items()):
            lines.append(
                "mcp_router_http_request_duration_seconds_count"
                f'{{method="{method}",path="{path}"}} {metric.count}'
            )
            lines.append(
                "mcp_router_http_request_duration_seconds_sum"
                f'{{method="{method}",path="{path}"}} '
                f"{metric.total_seconds:.6f}"
            )

        lines.extend(
            [
                "# HELP mcp_router_readiness_status Current readiness state.",
                "# TYPE mcp_router_readiness_status gauge",
            ]
        )
        ready = readiness is not None and readiness.get("status") == "ready"
        lines.append(f"mcp_router_readiness_status {1 if ready else 0}")

        lines.extend(
            [
                "# HELP mcp_router_readiness_dependency_healthy "
                "Dependency readiness result by dependency.",
                "# TYPE mcp_router_readiness_dependency_healthy gauge",
            ]
        )
        for dependency in readiness.get("dependencies", []) if readiness else []:
            lines.append(
                "mcp_router_readiness_dependency_healthy"
                f'{{dependency="{dependency["name"]}",'
                f'configured="{str(dependency["configured"]).lower()}"}} '
                f'{1 if dependency["healthy"] else 0}'
            )

        return "\n".join(lines) + "\n"
