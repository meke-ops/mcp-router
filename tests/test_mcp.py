import asyncio


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
