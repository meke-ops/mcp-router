def test_dashboard_page_renders(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Operations Atlas" in response.text
    assert "/v1/events/ws" in response.text


def test_control_plane_refreshes_and_lists_tools(integrated_client):
    initial_response = integrated_client.get("/v1/tools")
    assert initial_response.status_code == 200
    assert initial_response.json()["items"] == []

    refresh_response = integrated_client.post("/v1/tools/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["count"] == 2

    tools_response = integrated_client.get("/v1/tools")
    tool_names = {item["name"] for item in tools_response.json()["items"]}
    assert tool_names == {"demo.http.reverse", "demo.stdio.echo"}


def test_control_plane_policy_crud(client):
    create_response = client.post(
        "/v1/policies",
        json={
            "rule_id": "allow-dashboard-test",
            "effect": "allow",
            "reason": "Dashboard created policy.",
            "priority": 25,
            "tenant_ids": ["tenant-a"],
            "principal_ids": [],
            "roles": [],
            "tool_names": ["demo.http.reverse"],
            "tool_versions": [],
            "obligations": [],
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["item"]["ruleId"] == "allow-dashboard-test"

    list_response = client.get("/v1/policies")
    rule_ids = {item["ruleId"] for item in list_response.json()["items"]}
    assert "allow-dashboard-test" in rule_ids

    delete_response = client.delete("/v1/policies/allow-dashboard-test")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == "allow-dashboard-test"


def test_control_plane_registers_upstream_and_manual_tool(client):
    upstream_response = client.post(
        "/v1/upstreams",
        json={
            "server_id": "manual-http",
            "transport": "streamable_http",
            "endpoint_url": "http://manual-http/mcp",
            "command": [],
            "env": {},
            "fallback_server_ids": [],
        },
    )
    assert upstream_response.status_code == 200

    tool_response = client.post(
        "/v1/tools/register",
        json={
            "name": "manual.echo",
            "description": "Manual tool from control plane.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            "outputSchema": None,
            "tags": ["manual"],
            "serverId": "manual-http",
            "timeoutSeconds": 5,
        },
    )
    assert tool_response.status_code == 200
    assert tool_response.json()["item"]["name"] == "manual.echo"

    tools_response = client.get("/v1/tools")
    tool_names = {item["name"] for item in tools_response.json()["items"]}
    assert "manual.echo" in tool_names


def test_control_plane_audit_queries_and_websocket_feed(integrated_client):
    integrated_client.post("/v1/tools/refresh")

    with integrated_client.websocket_connect("/v1/events/ws") as websocket:
        response = integrated_client.post(
            "/v1/policies",
            json={
                "rule_id": "ws-policy",
                "effect": "allow",
                "reason": "Generated through websocket test.",
                "priority": 10,
                "tenant_ids": ["tenant-a"],
                "principal_ids": [],
                "roles": [],
                "tool_names": ["demo.http.reverse"],
                "tool_versions": [],
                "obligations": [],
            },
        )
        assert response.status_code == 200

        received = None
        for _ in range(6):
            payload = websocket.receive_json()
            if payload["event_type"] == "control.policy.upserted":
                received = payload
                break

    assert received is not None
    assert received["detail"]["ruleId"] == "ws-policy"

    audit_response = integrated_client.get("/v1/audit/events?event_type=control.policy.upserted")
    assert audit_response.status_code == 200
    assert any(
        item["detail"]["ruleId"] == "ws-policy"
        for item in audit_response.json()["items"]
    )
