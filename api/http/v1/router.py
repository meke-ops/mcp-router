from fastapi import APIRouter

from api.http.v1.routes.control_plane import router as control_plane_router
from api.http.v1.routes.health import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(control_plane_router)
