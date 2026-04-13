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
        headers={"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
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
