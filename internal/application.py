from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from api.http.mcp import router as mcp_router
from api.http.v1.router import router as api_v1_router
from internal.config import Settings, get_settings
from internal.container import ServiceContainer
from internal.health import ReadinessService
from internal.logging import configure_logging
from internal.mcp.service import MCPRouterService
from internal.registry import InMemoryToolRegistry
from internal.session_manager import InMemorySessionManager


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def create_service_container(settings: Settings) -> ServiceContainer:
    session_manager = InMemorySessionManager(ttl_seconds=settings.session_ttl_seconds)
    tool_registry = InMemoryToolRegistry()
    readiness_service = ReadinessService(settings=settings)
    mcp_service = MCPRouterService(
        settings=settings,
        session_manager=session_manager,
        tool_registry=tool_registry,
    )

    return ServiceContainer(
        settings=settings,
        readiness_service=readiness_service,
        session_manager=session_manager,
        tool_registry=tool_registry,
        mcp_service=mcp_service,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = create_service_container(app_settings)
        yield

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_v1_router, prefix=app_settings.api_v1_prefix)
    app.include_router(mcp_router, prefix=app_settings.mcp_prefix)

    return app


app = create_app()
