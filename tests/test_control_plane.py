def test_dashboard_page_renders(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Connect once. Route everywhere." in response.text
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
    state_snapshot = client.app.state.services.state_store.load()
    assert any(item.server_id == "manual-http" for item in state_snapshot.upstreams)


def test_control_plane_deletes_upstream(client):
    client.post(
        "/v1/upstreams",
        json={
            "server_id": "delete-me",
            "transport": "streamable_http",
            "url": "http://delete-me/mcp",
            "command": None,
            "args": [],
            "env": {},
            "headers": {},
            "fallback_server_ids": [],
        },
    )

    response = client.delete("/v1/upstreams/delete-me")

    assert response.status_code == 200
    assert response.json()["deleted"] == "delete-me"
    upstream_ids = {item.server_id for item in client.app.state.services.state_store.load().upstreams}
    assert "delete-me" not in upstream_ids


def test_setup_preview_and_apply_cursor_config(client):
    services = client.app.state.services
    project_config_path = (
        services.settings.resolved_workspace_root() / ".cursor" / "mcp.json"
    )

    preview_response = client.post(
        "/v1/setup/client-preview",
        json={
            "clientId": "cursor",
            "scope": "project",
            "mcpUrl": "http://127.0.0.1:8000/mcp",
            "token": "test-token",
            "configPath": str(project_config_path),
        },
    )

    assert preview_response.status_code == 200
    preview_item = preview_response.json()["item"]
    assert preview_item["clientId"] == "cursor"
    assert '"mcp-router"' in preview_item["mergedConfigText"]
    assert '"Authorization": "Bearer test-token"' in preview_item["mergedConfigText"]

    apply_response = client.post(
        "/v1/setup/client-apply",
        json={
            "clientId": "cursor",
            "scope": "project",
            "mcpUrl": "http://127.0.0.1:8000/mcp",
            "token": "test-token",
            "configPath": str(project_config_path),
        },
    )

    assert apply_response.status_code == 200
    body = apply_response.json()
    assert body["item"]["applied"] is True
    assert project_config_path.exists()
    assert "mcp-router" in project_config_path.read_text(encoding="utf-8")
    assert body["verification"]["sessionId"]


def test_setup_discovers_and_imports_existing_servers(client):
    services = client.app.state.services
    workspace_root = services.settings.resolved_workspace_root()
    home_root = services.settings.resolved_home()

    cursor_project_path = workspace_root / ".cursor" / "mcp.json"
    cursor_project_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_project_path.write_text(
        """
        {
          "mcpServers": {
            "workspace-echo": {
              "command": "python3",
              "args": ["server.py", "--debug"],
              "env": {
                "API_KEY": "demo"
              }
            }
          }
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    opencode_path = home_root / ".config" / "opencode" / "opencode.json"
    opencode_path.parent.mkdir(parents=True, exist_ok=True)
    opencode_path.write_text(
        """
        {
          "$schema": "https://opencode.ai/config.json",
          "mcp": {
            "router-remote": {
              "type": "remote",
              "url": "https://example.com/mcp",
              "enabled": true,
              "headers": {
                "Authorization": "Bearer abc"
              }
            }
          }
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    discovery_response = client.get("/v1/setup/discovery")

    assert discovery_response.status_code == 200
    items = discovery_response.json()["items"]
    candidate_names = {item["serverName"] for item in items}
    assert {"workspace-echo", "router-remote"} <= candidate_names

    candidate_ids = [item["candidateId"] for item in items]
    import_response = client.post(
        "/v1/setup/import",
        json={"candidateIds": candidate_ids, "refresh": False},
    )

    assert import_response.status_code == 200
    result = import_response.json()["item"]
    assert result["importedCount"] >= 2

    upstreams_response = client.get("/v1/upstreams")
    upstream_names = {item["serverId"] for item in upstreams_response.json()["items"]}
    assert "workspace-echo" in upstream_names
    assert "router-remote" in upstream_names


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
