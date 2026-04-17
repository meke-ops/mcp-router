import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from internal.registry import UpstreamServerDefinition


def test_initialize_creates_session(client):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {},
        },
    )

    assert response.status_code == 200
    assert response.headers["MCP-Session-Id"]
    assert response.json()["result"]["serverInfo"]["name"] == "mcp-router"


def test_tools_list_requires_session(client):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32001


def test_tools_list_returns_empty_registry(client):
    initialize_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "initialize",
            "params": {},
        },
    )

    response = client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "4",
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["tools"] == []


def test_tools_call_returns_tool_not_found_for_unknown_tool(client):
    initialize_response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "5",
            "method": "initialize",
            "params": {},
        },
    )

    response = client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "6",
            "method": "tools/call",
            "params": {
                "name": "demo.tool",
                "arguments": {"query": "hello"}
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32004


def test_tools_list_merges_http_and_stdio_upstreams(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "7",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "8",
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 200
    tool_names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert tool_names == {"demo.http.reverse", "demo.stdio.echo"}
    tool_meta = {
        tool["name"]: tool["_meta"]["router"] for tool in response.json()["result"]["tools"]
    }
    assert tool_meta["demo.http.reverse"]["serverId"] == "demo-http"
    assert tool_meta["demo.stdio.echo"]["serverId"] == "demo-stdio"
    assert tool_meta["demo.http.reverse"]["version"].startswith("sha256:")


def test_tools_call_routes_to_http_upstream(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "9",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "10",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {"text": "router"},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["reversed"] == "retuor"
    assert (
        response.json()["result"]["structuredContent"]["upstreamSessionId"]
        == "http-upstream-session"
    )
    assert response.json()["result"]["structuredContent"]["tenantId"] == "tenant-a"
    assert response.json()["result"]["structuredContent"]["principalId"] == "user-1"


def test_tools_call_routes_to_stdio_upstream(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
            "X-Principal-Roles": "ops",
        },
        json={
            "jsonrpc": "2.0",
            "id": "11",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={
            "MCP-Session-Id": initialize_response.headers["MCP-Session-Id"],
        },
        json={
            "jsonrpc": "2.0",
            "id": "12",
            "method": "tools/call",
            "params": {
                "name": "demo.stdio.echo",
                "arguments": {"text": "router"},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["transport"] == "stdio"
    assert response.json()["result"]["structuredContent"]["echo"] == "router"
    assert response.json()["result"]["structuredContent"]["tenantId"] == "tenant-a"
    assert response.json()["result"]["structuredContent"]["principalId"] == "user-1"


def test_tools_call_denies_blocked_principal_with_high_priority_rule(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "blocked-user",
            "X-Principal-Roles": "ops",
        },
        json={
            "jsonrpc": "2.0",
            "id": "13",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "14",
            "method": "tools/call",
            "params": {
                "name": "demo.stdio.echo",
                "arguments": {"text": "router"},
            },
        },
    )

    assert response.status_code == 403
    payload = response.json()["error"]
    assert payload["code"] == -32009
    assert payload["message"] == "Principal is blocked from invoking tools in this tenant."
    assert payload["data"]["effect"] == "deny"
    assert payload["data"]["ruleId"] == "deny-blocked-principal"
    assert payload["data"]["isDefault"] is False
    assert payload["data"]["obligations"] == [
        {
            "type": "notify",
            "parameters": {"channel": "security"},
        }
    ]


def test_tools_call_default_denies_without_matching_allow_rule(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-2",
        },
        json={
            "jsonrpc": "2.0",
            "id": "15",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "16",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {"text": "router"},
            },
        },
    )

    assert response.status_code == 403
    payload = response.json()["error"]
    assert payload["code"] == -32009
    assert payload["data"]["effect"] == "deny"
    assert payload["data"]["ruleId"] is None
    assert payload["data"]["isDefault"] is True
    assert payload["data"]["obligations"] == []


def test_session_rejects_context_mismatch(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "13",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={
            "MCP-Session-Id": initialize_response.headers["MCP-Session-Id"],
            "X-Tenant-Id": "tenant-b",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "14",
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32008


def test_session_rejects_role_mismatch(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
            "X-Principal-Roles": "ops",
        },
        json={
            "jsonrpc": "2.0",
            "id": "17",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={
            "MCP-Session-Id": initialize_response.headers["MCP-Session-Id"],
            "X-Principal-Roles": "viewer",
        },
        json={
            "jsonrpc": "2.0",
            "id": "18",
            "method": "tools/list",
            "params": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32008
    assert response.json()["error"]["data"]["expectedRoles"] == ["ops"]
    assert response.json()["error"]["data"]["receivedRoles"] == ["viewer"]


def test_tools_call_rejects_invalid_arguments_against_schema(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "15",
            "method": "initialize",
            "params": {},
        },
    )

    response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "16",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32602
    assert response.json()["error"]["data"]["tool"] == "demo.http.reverse"
    assert response.json()["error"]["data"]["toolVersion"].startswith("sha256:")
    assert "required property" in response.json()["error"]["data"]["message"]


def test_registry_tracks_versions_and_bindings_after_discovery(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "19",
            "method": "initialize",
            "params": {},
        },
    )

    integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "20",
            "method": "tools/list",
            "params": {},
        },
    )

    registry = integrated_client.app.state.services.tool_registry
    registered_tool = asyncio.run(registry.get_tool("demo.http.reverse"))

    assert registered_tool is not None
    assert registered_tool.binding.server_id == "demo-http"
    assert registered_tool.binding.tool_version == registered_tool.version
    assert registered_tool.version in registered_tool.versions


def test_policy_decisions_are_audited_for_allow_and_deny(integrated_client):
    allow_initialize = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "21",
            "method": "initialize",
            "params": {},
        },
    )
    deny_initialize = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "blocked-user",
        },
        json={
            "jsonrpc": "2.0",
            "id": "22",
            "method": "initialize",
            "params": {},
        },
    )

    allow_response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": allow_initialize.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "23",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {"text": "allow"},
            },
        },
    )
    deny_response = integrated_client.post(
        "/mcp",
        headers={"MCP-Session-Id": deny_initialize.headers["MCP-Session-Id"]},
        json={
            "jsonrpc": "2.0",
            "id": "24",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {"text": "deny"},
            },
        },
    )

    assert allow_response.status_code == 200
    assert deny_response.status_code == 403

    audit_log = integrated_client.app.state.services.audit_log
    audit_records = asyncio.run(audit_log.list_policy_decisions())

    matching_records = [
        record
        for record in audit_records
        if record.request_id in {"23", "24"}
    ]
    assert len(matching_records) == 2

    decisions_by_request_id = {
        str(record.request_id): record for record in matching_records
    }
    allow_record = decisions_by_request_id["23"]
    deny_record = decisions_by_request_id["24"]

    assert allow_record.decision == "allow"
    assert allow_record.rule_id == "allow-http-for-user-1"
    assert allow_record.reason == "Principal is allowed to use the HTTP demo tool."
    assert [obligation.to_payload() for obligation in allow_record.obligations] == [
        {
            "type": "audit",
            "parameters": {"level": "full"},
        }
    ]

    assert deny_record.decision == "deny"
    assert deny_record.rule_id == "deny-blocked-principal"
    assert deny_record.reason == "Principal is blocked from invoking tools in this tenant."
    assert [obligation.to_payload() for obligation in deny_record.obligations] == [
        {
            "type": "notify",
            "parameters": {"channel": "security"},
        }
    ]


def test_tools_call_rate_limit_returns_429_and_audit_event(integrated_app_factory):
    app = integrated_app_factory(
        tool_call_rate_limit_capacity=1,
        tool_call_rate_limit_refill_rate=0.0,
        tool_call_concurrency_limit=4,
    )

    with TestClient(app) as client:
        initialize_response = client.post(
            "/mcp",
            headers={
                "X-Tenant-Id": "tenant-a",
                "X-Principal-Id": "user-1",
            },
            json={
                "jsonrpc": "2.0",
                "id": "25",
                "method": "initialize",
                "params": {},
            },
        )
        session_id = initialize_response.headers["MCP-Session-Id"]

        first_response = client.post(
            "/mcp",
            headers={"MCP-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": "26",
                "method": "tools/call",
                "params": {
                    "name": "demo.http.reverse",
                    "arguments": {"text": "first"},
                },
            },
        )
        second_response = client.post(
            "/mcp",
            headers={"MCP-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": "27",
                "method": "tools/call",
                "params": {
                    "name": "demo.http.reverse",
                    "arguments": {"text": "second"},
                },
            },
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == -32010
    assert second_response.json()["error"]["data"]["limitType"] == "rate_limit"

    tool_call_records = asyncio.run(app.state.services.audit_log.list_tool_calls())
    audit_event_records = asyncio.run(app.state.services.audit_log.list_audit_events())

    rate_limited_record = next(
        record for record in tool_call_records if str(record.request_id) == "27"
    )
    assert rate_limited_record.outcome == "rate_limit"
    assert rate_limited_record.status_code == 429
    assert rate_limited_record.error_code == -32010

    rejected_event = next(
        event
        for event in audit_event_records
        if str(event.request_id) == "27"
        and event.event_type == "traffic.rate_limit.rejected"
    )
    assert rejected_event.detail["limitType"] == "rate_limit"


def test_tools_call_propagates_traceparent_and_records_trace_chain(integrated_client):
    initialize_response = integrated_client.post(
        "/mcp",
        headers={
            "X-Tenant-Id": "tenant-a",
            "X-Principal-Id": "user-1",
        },
        json={
            "jsonrpc": "2.0",
            "id": "28",
            "method": "initialize",
            "params": {},
        },
    )

    inbound_traceparent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    response = integrated_client.post(
        "/mcp",
        headers={
            "MCP-Session-Id": initialize_response.headers["MCP-Session-Id"],
            "traceparent": inbound_traceparent,
        },
        json={
            "jsonrpc": "2.0",
            "id": "29",
            "method": "tools/call",
            "params": {
                "name": "demo.http.reverse",
                "arguments": {"text": "trace"},
            },
        },
    )

    assert response.status_code == 200
    trace_id = "0123456789abcdef0123456789abcdef"
    assert response.headers["X-Trace-Id"] == trace_id
    assert response.headers["traceparent"].startswith(f"00-{trace_id}-")
    structured_content = response.json()["result"]["structuredContent"]
    assert structured_content["traceparent"].startswith(f"00-{trace_id}-")
    assert structured_content["requestId"] == response.headers["X-Request-Id"]

    trace_records = asyncio.run(integrated_client.app.state.services.trace_recorder.list_spans())
    trace_spans = [record for record in trace_records if record.trace_id == trace_id]
    span_by_name = {record.name: record for record in trace_spans}

    assert "mcp.tools.call" in span_by_name
    assert "traffic.check" in span_by_name
    assert "policy.evaluate" in span_by_name
    assert "upstream.resilience" in span_by_name
    assert "upstream.call" in span_by_name
    assert span_by_name["traffic.check"].parent_span_id == span_by_name["mcp.tools.call"].span_id
    assert span_by_name["policy.evaluate"].parent_span_id == span_by_name["mcp.tools.call"].span_id
    assert (
        span_by_name["upstream.resilience"].parent_span_id
        == span_by_name["mcp.tools.call"].span_id
    )
    assert (
        span_by_name["upstream.call"].parent_span_id
        == span_by_name["upstream.resilience"].span_id
    )

    tool_call_records = asyncio.run(integrated_client.app.state.services.audit_log.list_tool_calls())
    traced_record = next(record for record in tool_call_records if str(record.request_id) == "29")
    assert traced_record.trace_id == trace_id
    assert traced_record.outcome == "success"


@pytest.mark.anyio
async def test_tools_call_concurrency_gate_returns_429_and_audit_event(
    integrated_app_factory,
):
    app = integrated_app_factory(
        tool_call_rate_limit_capacity=10,
        tool_call_rate_limit_refill_rate=10.0,
        tool_call_concurrency_limit=1,
    )
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            initialize_response = await client.post(
                "/mcp",
                headers={
                    "X-Tenant-Id": "tenant-a",
                    "X-Principal-Id": "user-1",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": "30",
                    "method": "initialize",
                    "params": {},
                },
            )
            session_id = initialize_response.headers["MCP-Session-Id"]

            await client.post(
                "/mcp",
                headers={"MCP-Session-Id": session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": "31",
                    "method": "tools/list",
                    "params": {},
                },
            )

            async def slow_call():
                return await client.post(
                    "/mcp",
                    headers={"MCP-Session-Id": session_id},
                    json={
                        "jsonrpc": "2.0",
                        "id": "32",
                        "method": "tools/call",
                        "params": {
                            "name": "demo.http.reverse",
                            "arguments": {"text": "slow", "delayMs": 200},
                        },
                    },
                )

            async def concurrent_call():
                await asyncio.sleep(0.05)
                return await client.post(
                    "/mcp",
                    headers={"MCP-Session-Id": session_id},
                    json={
                        "jsonrpc": "2.0",
                        "id": "33",
                        "method": "tools/call",
                        "params": {
                            "name": "demo.http.reverse",
                            "arguments": {"text": "fast"},
                        },
                    },
                )

            first_response, second_response = await asyncio.gather(
                slow_call(),
                concurrent_call(),
            )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == -32011
    assert second_response.json()["error"]["data"]["limitType"] == "concurrency"

    tool_call_records = await app.state.services.audit_log.list_tool_calls()
    audit_event_records = await app.state.services.audit_log.list_audit_events()

    concurrency_limited_record = next(
        record for record in tool_call_records if str(record.request_id) == "33"
    )
    assert concurrency_limited_record.outcome == "concurrency"
    assert concurrency_limited_record.status_code == 429
    assert concurrency_limited_record.error_code == -32011

    rejected_event = next(
        event
        for event in audit_event_records
        if str(event.request_id) == "33"
        and event.event_type == "traffic.concurrency.rejected"
    )
    assert rejected_event.detail["limitType"] == "concurrency"


def test_tools_call_falls_back_to_hidden_upstream_on_transport_failure(
    integrated_app_factory,
    http_upstream_app_factory,
):
    primary_app = http_upstream_app_factory(
        server_info_name="primary-http-upstream",
        always_fail_tool_calls=True,
    )
    fallback_app = http_upstream_app_factory(
        server_info_name="fallback-http-upstream",
    )
    app = integrated_app_factory(
        upstream_servers=[
            UpstreamServerDefinition(
                server_id="demo-http-primary",
                transport="streamable_http",
                url="http://demo-http-primary/mcp",
                fallback_server_ids=("demo-http-fallback",),
                retry_attempts=1,
                circuit_breaker_failure_threshold=2,
                circuit_breaker_recovery_seconds=30.0,
            ),
            UpstreamServerDefinition(
                server_id="demo-http-fallback",
                transport="streamable_http",
                url="http://demo-http-fallback/mcp",
                discover_tools=False,
            ),
        ],
        http_transport_overrides={
            "http://demo-http-primary/mcp": httpx.ASGITransport(app=primary_app),
            "http://demo-http-fallback/mcp": httpx.ASGITransport(app=fallback_app),
        },
    )

    with TestClient(app) as client:
        initialize_response = client.post(
            "/mcp",
            headers={
                "X-Tenant-Id": "tenant-a",
                "X-Principal-Id": "user-1",
            },
            json={
                "jsonrpc": "2.0",
                "id": "34",
                "method": "initialize",
                "params": {},
            },
        )
        response = client.post(
            "/mcp",
            headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
            json={
                "jsonrpc": "2.0",
                "id": "35",
                "method": "tools/call",
                "params": {
                    "name": "demo.http.reverse",
                    "arguments": {"text": "fallback"},
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["serverName"] == "fallback-http-upstream"
    assert primary_app.state.tool_call_attempts == 2
    assert fallback_app.state.tool_call_attempts == 1

    audit_event_records = asyncio.run(app.state.services.audit_log.list_audit_events())
    event_types = {
        event.event_type
        for event in audit_event_records
        if str(event.request_id) == "35"
    }
    assert "upstream.retry.scheduled" in event_types
    assert "upstream.fallback.selected" in event_types
    assert "upstream.fallback.succeeded" in event_types


def test_circuit_breaker_skips_primary_and_uses_fallback_on_next_call(
    integrated_app_factory,
    http_upstream_app_factory,
):
    primary_app = http_upstream_app_factory(
        server_info_name="primary-http-upstream",
        always_fail_tool_calls=True,
    )
    fallback_app = http_upstream_app_factory(
        server_info_name="fallback-http-upstream",
    )
    app = integrated_app_factory(
        upstream_servers=[
            UpstreamServerDefinition(
                server_id="demo-http-primary",
                transport="streamable_http",
                url="http://demo-http-primary/mcp",
                fallback_server_ids=("demo-http-fallback",),
                retry_attempts=0,
                circuit_breaker_failure_threshold=1,
                circuit_breaker_recovery_seconds=60.0,
            ),
            UpstreamServerDefinition(
                server_id="demo-http-fallback",
                transport="streamable_http",
                url="http://demo-http-fallback/mcp",
                discover_tools=False,
            ),
        ],
        http_transport_overrides={
            "http://demo-http-primary/mcp": httpx.ASGITransport(app=primary_app),
            "http://demo-http-fallback/mcp": httpx.ASGITransport(app=fallback_app),
        },
    )

    with TestClient(app) as client:
        initialize_response = client.post(
            "/mcp",
            headers={
                "X-Tenant-Id": "tenant-a",
                "X-Principal-Id": "user-1",
            },
            json={
                "jsonrpc": "2.0",
                "id": "36",
                "method": "initialize",
                "params": {},
            },
        )
        session_id = initialize_response.headers["MCP-Session-Id"]

        first_response = client.post(
            "/mcp",
            headers={"MCP-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": "37",
                "method": "tools/call",
                "params": {
                    "name": "demo.http.reverse",
                    "arguments": {"text": "first"},
                },
            },
        )
        second_response = client.post(
            "/mcp",
            headers={"MCP-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": "38",
                "method": "tools/call",
                "params": {
                    "name": "demo.http.reverse",
                    "arguments": {"text": "second"},
                },
            },
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["result"]["structuredContent"]["serverName"] == "fallback-http-upstream"
    assert second_response.json()["result"]["structuredContent"]["serverName"] == "fallback-http-upstream"
    assert primary_app.state.tool_call_attempts == 1
    assert fallback_app.state.tool_call_attempts == 2

    audit_event_records = asyncio.run(app.state.services.audit_log.list_audit_events())
    second_call_events = [
        event
        for event in audit_event_records
        if str(event.request_id) == "38"
    ]
    event_types = {event.event_type for event in second_call_events}
    assert "circuit.open.rejected" in event_types
    assert "upstream.fallback.selected" in event_types
    rejection_event = next(
        event for event in second_call_events if event.event_type == "circuit.open.rejected"
    )
    assert rejection_event.detail["serverId"] == "demo-http-primary"
