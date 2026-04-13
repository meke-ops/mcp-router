from dataclasses import dataclass
from functools import lru_cache
import os


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
    session_ttl_seconds: int = 1800
    require_dependencies_for_readiness: bool = False
    postgres_dsn: str | None = None
    redis_url: str | None = None
    upstreams_json: str | None = None
    policies_json: str | None = None
    tool_call_rate_limit_capacity: int = 60
    tool_call_rate_limit_refill_rate: float = 30.0
    tool_call_concurrency_limit: int = 8


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
        session_ttl_seconds=int(os.getenv("MCP_ROUTER_SESSION_TTL_SECONDS", "1800")),
        require_dependencies_for_readiness=_bool_env(
            "MCP_ROUTER_REQUIRE_DEPENDENCIES_FOR_READINESS",
            False,
        ),
        postgres_dsn=os.getenv("MCP_ROUTER_POSTGRES_DSN"),
        redis_url=os.getenv("MCP_ROUTER_REDIS_URL"),
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
    )
