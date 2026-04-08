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
