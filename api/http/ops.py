from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from api.http.dependencies import get_services
from internal.container import ServiceContainer

router = APIRouter(tags=["ops"])


@router.get("/metrics")
async def metrics(
    services: ServiceContainer = Depends(get_services),
) -> PlainTextResponse:
    readiness = await services.readiness_service.check()
    payload = await services.metrics_recorder.render_prometheus(readiness=readiness)
    return PlainTextResponse(
        content=payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
