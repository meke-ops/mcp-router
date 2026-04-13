import asyncio
from urllib.parse import urlparse

from internal.config import Settings


class ReadinessService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> dict[str, object]:
        dependencies = []

        for name, raw_target, default_port in (
            ("postgres", self._settings.postgres_dsn, 5432),
            ("redis", self._settings.redis_url, 6379),
        ):
            if raw_target:
                if self._settings.require_dependencies_for_readiness:
                    healthy, detail = await self._probe_tcp_dependency(
                        raw_target,
                        default_port=default_port,
                    )
                else:
                    healthy = True
                    detail = (
                        "Configured. Active probe skipped because readiness gating "
                        "is disabled."
                    )
                dependencies.append(
                    {
                        "name": name,
                        "configured": True,
                        "healthy": healthy,
                        "detail": detail,
                    }
                )
            else:
                dependencies.append(
                    {
                        "name": name,
                        "configured": False,
                        "healthy": not self._settings.require_dependencies_for_readiness,
                        "detail": "Not configured.",
                    }
                )

        ready = all(item["healthy"] for item in dependencies)

        return {
            "status": "ready" if ready else "not_ready",
            "service": self._settings.app_name,
            "dependencies": dependencies,
        }

    async def _probe_tcp_dependency(
        self,
        raw_target: str,
        *,
        default_port: int,
    ) -> tuple[bool, str]:
        parsed_target = urlparse(raw_target)
        host = parsed_target.hostname
        port = parsed_target.port or default_port

        if not host:
            return False, "Configured but host could not be parsed."

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self._settings.readiness_probe_timeout_seconds,
            )
        except Exception as exc:
            return False, f"TCP probe failed for {host}:{port}: {exc}"

        writer.close()
        await writer.wait_closed()
        return True, f"TCP probe succeeded for {host}:{port}"
