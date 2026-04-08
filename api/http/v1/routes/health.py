from fastapi import APIRouter, Depends

from api.http.dependencies import get_services
from internal.container import ServiceContainer

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(services: ServiceContainer = Depends(get_services)) -> dict[str, object]:
    return {
        "status": "ok",
        "service": services.settings.app_name,
        "environment": services.settings.app_env,
        "version": services.settings.app_version,
    }


@router.get("/ready")
async def ready(services: ServiceContainer = Depends(get_services)) -> dict[str, object]:
    readiness = await services.readiness_service.check()
    return readiness
