import asyncio
from pathlib import Path
import sys
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Header, Response
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from internal.application import create_app
from internal.config import Settings
from internal.policy import PolicyObligation, PolicyRule
from internal.registry import UpstreamServerDefinition


HTTP_UPSTREAM_SESSION_ID = "http-upstream-session"
INTEGRATION_FIXTURES = {
    "integrated_app",
    "integrated_app_factory",
    "integrated_client",
    "http_upstream_app_factory",
}


def build_demo_policy_rules() -> list[PolicyRule]:
    return [
        PolicyRule(
            rule_id="deny-blocked-principal",
            effect="deny",
            reason="Principal is blocked from invoking tools in this tenant.",
            priority=100,
            tenant_ids=("tenant-a",),
            principal_ids=("blocked-user",),
            tool_names=("demo.*",),
            obligations=(
                PolicyObligation(
                    obligation_type="notify",
                    parameters={"channel": "security"},
                ),
            ),
        ),
        PolicyRule(
            rule_id="allow-http-for-user-1",
            effect="allow",
            reason="Principal is allowed to use the HTTP demo tool.",
            priority=50,
            tenant_ids=("tenant-a",),
            principal_ids=("user-1",),
            tool_names=("demo.http.reverse",),
            obligations=(
                PolicyObligation(
                    obligation_type="audit",
                    parameters={"level": "full"},
                ),
            ),
        ),
        PolicyRule(
            rule_id="allow-stdio-for-ops-role",
            effect="allow",
            reason="Ops role may use stdio demo tools.",
            priority=50,
            tenant_ids=("tenant-a",),
            roles=("ops",),
            tool_names=("demo.stdio.echo",),
            obligations=(
                PolicyObligation(
                    obligation_type="audit",
                    parameters={"level": "full"},
                ),
            ),
        ),
    ]


def create_http_upstream_app(
    *,
    server_info_name: str = "demo-http-upstream",
    expected_tool_name: str = "demo.http.reverse",
    fail_first_tool_calls: int = 0,
    always_fail_tool_calls: bool = False,
) -> FastAPI:
    app = FastAPI()
    app.state.tool_call_attempts = 0

    @app.post("/mcp")
    async def handle_mcp(
        payload: dict,
        response: Response,
        mcp_session_id: str | None = Header(default=None, alias="MCP-Session-Id"),
        x_mcp_router_tenant_id: str | None = Header(
            default=None,
            alias="X-MCP-Router-Tenant-Id",
        ),
        x_mcp_router_principal_id: str | None = Header(
            default=None,
            alias="X-MCP-Router-Principal-Id",
        ),
        x_mcp_router_request_id: str | None = Header(
            default=None,
            alias="X-MCP-Router-Request-Id",
        ),
        traceparent: str | None = Header(default=None, alias="traceparent"),
    ) -> dict:
        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params", {})

        if method == "initialize":
            response.headers["MCP-Session-Id"] = HTTP_UPSTREAM_SESSION_ID
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {
                        "name": server_info_name,
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        }
                    },
                },
            }

        if method == "tools/list":
            if mcp_session_id != HTTP_UPSTREAM_SESSION_ID:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32001,
                        "message": "HTTP upstream session is missing.",
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": expected_tool_name,
                            "description": "Reverses text using the HTTP upstream.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "delayMs": {"type": "integer"},
                                },
                                "required": ["text"],
                            },
                        }
                    ]
                },
            }

        if method == "tools/call":
            if mcp_session_id != HTTP_UPSTREAM_SESSION_ID:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32001,
                        "message": "HTTP upstream session is missing.",
                    },
                }
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if tool_name != expected_tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32004,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            app.state.tool_call_attempts += 1
            if always_fail_tool_calls or app.state.tool_call_attempts <= fail_first_tool_calls:
                return PlainTextResponse(
                    f"{server_info_name} transport failure",
                    status_code=502,
                )
            text = arguments.get("text", "")
            delay_ms = arguments.get("delayMs", 0)
            if isinstance(delay_ms, int) and delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text[::-1],
                        }
                    ],
                    "structuredContent": {
                        "tool": tool_name,
                        "transport": "streamable_http",
                        "reversed": text[::-1],
                        "serverName": server_info_name,
                        "upstreamSessionId": mcp_session_id,
                        "tenantId": x_mcp_router_tenant_id,
                        "principalId": x_mcp_router_principal_id,
                        "requestId": x_mcp_router_request_id,
                        "traceparent": traceparent,
                    },
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unsupported method: {method}",
            },
        }

    return app


def build_test_settings(**overrides) -> Settings:
    test_root = Path("/tmp") / f"mcp-router-test-{uuid4().hex}"
    base_settings = {
        "app_env": "test",
        "require_dependencies_for_readiness": False,
        "session_ttl_seconds": 60,
        "tool_call_rate_limit_capacity": 10,
        "tool_call_rate_limit_refill_rate": 10.0,
        "tool_call_concurrency_limit": 4,
        "local_state_path": str(test_root / "router-state.json"),
        "workspace_root": str(test_root / "workspace"),
        "user_home": str(test_root / "home"),
    }
    base_settings.update(overrides)
    return Settings(**base_settings)


def build_integrated_app(**setting_overrides) -> FastAPI:
    upstream_servers = setting_overrides.pop("upstream_servers", None)
    http_transport_overrides = setting_overrides.pop("http_transport_overrides", None)
    policy_rules = setting_overrides.pop("policy_rules", None)

    if upstream_servers is None:
        http_upstream_app = create_http_upstream_app()
        http_transport = httpx.ASGITransport(app=http_upstream_app)
        stdio_script = Path(__file__).parent / "fixtures" / "demo_stdio_upstream.py"
        upstream_servers = [
            UpstreamServerDefinition(
                server_id="demo-http",
                transport="streamable_http",
                url="http://demo-http/mcp",
            ),
            UpstreamServerDefinition(
                server_id="demo-stdio",
                transport="stdio",
                command=sys.executable,
                args=(str(stdio_script),),
            ),
        ]
        http_transport_overrides = {
            "http://demo-http/mcp": http_transport,
        }

    return create_app(
        build_test_settings(**setting_overrides),
        policy_rules=policy_rules or build_demo_policy_rules(),
        upstream_servers=upstream_servers,
        http_transport_overrides=http_transport_overrides,
    )


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        build_test_settings()
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def integrated_app() -> FastAPI:
    return build_integrated_app()


@pytest.fixture
def integrated_app_factory():
    return build_integrated_app


@pytest.fixture
def http_upstream_app_factory():
    return create_http_upstream_app


@pytest.fixture
def integrated_client(integrated_app: FastAPI) -> TestClient:
    with TestClient(integrated_app) as test_client:
        yield test_client


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        fixture_names = set(getattr(item, "fixturenames", ()))
        marker = (
            pytest.mark.integration
            if fixture_names & INTEGRATION_FIXTURES
            else pytest.mark.unit
        )
        item.add_marker(marker)
