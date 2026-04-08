from internal.config import Settings


class ReadinessService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check(self) -> dict[str, object]:
        dependencies = []

        for name, configured in (
            ("postgres", bool(self._settings.postgres_dsn)),
            ("redis", bool(self._settings.redis_url)),
        ):
            if configured:
                dependencies.append(
                    {
                        "name": name,
                        "configured": True,
                        "healthy": not self._settings.require_dependencies_for_readiness,
                        "detail": "Configured. Active connectivity probe will be added in the next milestone.",
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
