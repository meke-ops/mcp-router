from fastapi import APIRouter

from api.http.v1.routes.health import router as health_router

router = APIRouter()
router.include_router(health_router)
