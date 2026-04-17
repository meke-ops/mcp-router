from internal.application import create_service_container
from internal.config import Settings
from internal.registry import UpstreamServerDefinition


def test_upstream_definition_supports_legacy_command_array():
    upstream = UpstreamServerDefinition.from_record(
        {
            "server_id": "legacy-stdio",
            "transport": "stdio",
            "command": ["python3", "server.py", "--debug"],
            "env": {"TOKEN": "demo"},
        }
    )

    assert upstream.command == "python3"
    assert upstream.args == ("server.py", "--debug")
    assert upstream.env["TOKEN"] == "demo"


def test_codex_preview_replaces_existing_router_block(tmp_path):
    settings = Settings(
        app_env="test",
        session_ttl_seconds=60,
        tool_call_rate_limit_capacity=10,
        tool_call_rate_limit_refill_rate=10.0,
        tool_call_concurrency_limit=4,
        user_home=str(tmp_path / "home"),
        workspace_root=str(tmp_path / "workspace"),
        local_state_path=str(tmp_path / "state" / "router-state.json"),
    )
    codex_config = settings.resolved_home() / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True, exist_ok=True)
    codex_config.write_text(
        """
model = "gpt-5.4"

[mcp_servers.keep]
command = "npx"
args = [ "@playwright/mcp@latest" ]

[mcp_servers.mcp-router]
url = "https://old-router.example/mcp"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    services = create_service_container(settings)
    preview = services.setup_service.preview_client(
        client_id="codex",
        scope="user",
        mcp_url="https://new-router.example/mcp",
        token="secret-token",
        config_path=str(codex_config),
    )

    assert preview.merged_config_text.count("[mcp_servers.mcp-router]") == 1
    assert 'url = "https://new-router.example/mcp"' in preview.merged_config_text
    assert 'command = "npx"' in preview.merged_config_text
    assert 'Authorization = "Bearer secret-token"' in preview.merged_config_text
