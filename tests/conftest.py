from pathlib import Path
import sys

import httpx
import pytest
from fastapi import FastAPI, Header, Response
from fastapi.testclient import TestClient

from internal.application import create_app
from internal.config import Settings
from internal.policy import PolicyObligation, PolicyRule
from internal.registry import UpstreamServerDefinition


HTTP_UPSTREAM_SESSION_ID = "http-upstream-session"


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


def create_http_upstream_app() -> FastAPI:
    app = FastAPI()

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
                        "name": "demo-http-upstream",
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
                            "name": "demo.http.reverse",
                            "description": "Reverses text using the HTTP upstream.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
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
            if tool_name != "demo.http.reverse":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32004,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            text = arguments.get("text", "")
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
                        "upstreamSessionId": mcp_session_id,
                        "tenantId": x_mcp_router_tenant_id,
                        "principalId": x_mcp_router_principal_id,
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


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        Settings(
            app_env="test",
            require_dependencies_for_readiness=False,
            session_ttl_seconds=60,
        )
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def integrated_client() -> TestClient:
    http_upstream_app = create_http_upstream_app()
    http_transport = httpx.ASGITransport(app=http_upstream_app)
    stdio_script = Path(__file__).parent / "fixtures" / "demo_stdio_upstream.py"

    app = create_app(
        Settings(
            app_env="test",
            require_dependencies_for_readiness=False,
            session_ttl_seconds=60,
        ),
        policy_rules=build_demo_policy_rules(),
        upstream_servers=[
            UpstreamServerDefinition(
                server_id="demo-http",
                transport="streamable_http",
                endpoint_url="http://demo-http/mcp",
            ),
            UpstreamServerDefinition(
                server_id="demo-stdio",
                transport="stdio",
                command=(sys.executable, str(stdio_script)),
            ),
        ],
        http_transport_overrides={
            "http://demo-http/mcp": http_transport,
        },
    )

    with TestClient(app) as test_client:
        yield test_client
