from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "mcp-router"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/v1"
    mcp_prefix: str = "/mcp"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "plain"
    session_ttl_seconds: int = 1800
    require_dependencies_for_readiness: bool = False
    readiness_probe_timeout_seconds: float = 1.5
    postgres_dsn: str | None = None
    redis_url: str | None = None
    metrics_enabled: bool = True
    upstreams_json: str | None = None
    policies_json: str | None = None
    tool_call_rate_limit_capacity: int = 60
    tool_call_rate_limit_refill_rate: float = 30.0
    tool_call_concurrency_limit: int = 8
    auth_enabled: bool = False
    jwt_secret: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_clock_skew_seconds: int = 30
    control_plane_allowed_roles: tuple[str, ...] = ("control-plane", "admin")
    local_state_path: str = ""
    workspace_root: str = ""
    user_home: str = ""

    def resolved_home(self) -> Path:
        if self.user_home:
            return Path(self.user_home).expanduser()
        return Path.home()

    def resolved_local_state_path(self) -> Path:
        if self.local_state_path:
            return Path(self.local_state_path).expanduser()
        return (
            self.resolved_home()
            / "Library"
            / "Application Support"
            / "mcp-router"
            / "router-state.json"
        )

    def resolved_workspace_root(self) -> Path:
        if self.workspace_root:
            return Path(self.workspace_root).expanduser()
        return Path.cwd()


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("MCP_ROUTER_APP_NAME", "mcp-router"),
        app_env=os.getenv("MCP_ROUTER_APP_ENV", "development"),
        app_version=os.getenv("MCP_ROUTER_APP_VERSION", "0.1.0"),
        api_v1_prefix=os.getenv("MCP_ROUTER_API_V1_PREFIX", "/v1"),
        mcp_prefix=os.getenv("MCP_ROUTER_MCP_PREFIX", "/mcp"),
        host=os.getenv("MCP_ROUTER_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_ROUTER_PORT", "8000")),
        log_level=os.getenv("MCP_ROUTER_LOG_LEVEL", "INFO"),
        log_format=os.getenv("MCP_ROUTER_LOG_FORMAT", "plain"),
        session_ttl_seconds=int(os.getenv("MCP_ROUTER_SESSION_TTL_SECONDS", "1800")),
        require_dependencies_for_readiness=_bool_env(
            "MCP_ROUTER_REQUIRE_DEPENDENCIES_FOR_READINESS",
            False,
        ),
        readiness_probe_timeout_seconds=float(
            os.getenv("MCP_ROUTER_READINESS_PROBE_TIMEOUT_SECONDS", "1.5")
        ),
        postgres_dsn=os.getenv("MCP_ROUTER_POSTGRES_DSN"),
        redis_url=os.getenv("MCP_ROUTER_REDIS_URL"),
        metrics_enabled=_bool_env("MCP_ROUTER_METRICS_ENABLED", True),
        upstreams_json=os.getenv("MCP_ROUTER_UPSTREAMS_JSON"),
        policies_json=os.getenv("MCP_ROUTER_POLICIES_JSON"),
        tool_call_rate_limit_capacity=int(
            os.getenv("MCP_ROUTER_TOOL_CALL_RATE_LIMIT_CAPACITY", "60")
        ),
        tool_call_rate_limit_refill_rate=float(
            os.getenv("MCP_ROUTER_TOOL_CALL_RATE_LIMIT_REFILL_RATE", "30.0")
        ),
        tool_call_concurrency_limit=int(
            os.getenv("MCP_ROUTER_TOOL_CALL_CONCURRENCY_LIMIT", "8")
        ),
        auth_enabled=_bool_env("MCP_ROUTER_AUTH_ENABLED", False),
        jwt_secret=os.getenv("MCP_ROUTER_JWT_SECRET"),
        jwt_issuer=os.getenv("MCP_ROUTER_JWT_ISSUER"),
        jwt_audience=os.getenv("MCP_ROUTER_JWT_AUDIENCE"),
        jwt_clock_skew_seconds=int(
            os.getenv("MCP_ROUTER_JWT_CLOCK_SKEW_SECONDS", "30")
        ),
        control_plane_allowed_roles=tuple(
            role.strip()
            for role in os.getenv(
                "MCP_ROUTER_CONTROL_PLANE_ALLOWED_ROLES",
                "control-plane,admin",
            ).split(",")
            if role.strip()
        ),
        local_state_path=os.getenv("MCP_ROUTER_LOCAL_STATE_PATH", ""),
        workspace_root=os.getenv("MCP_ROUTER_WORKSPACE_ROOT", ""),
        user_home=os.getenv("MCP_ROUTER_USER_HOME", ""),
    )
