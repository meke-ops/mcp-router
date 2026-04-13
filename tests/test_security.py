import asyncio
import base64
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from internal.redaction import hash_token


JWT_SECRET = "milestone-10-secret"
JWT_ISSUER = "mcp-router-tests"
JWT_AUDIENCE = "mcp-router-clients"


def _build_authenticated_client(integrated_app_factory, **overrides) -> TestClient:
    app = integrated_app_factory(
        auth_enabled=True,
        jwt_secret=JWT_SECRET,
        jwt_issuer=JWT_ISSUER,
        jwt_audience=JWT_AUDIENCE,
        **overrides,
    )
    return TestClient(app)


def _encode_segment(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _mint_token(
    *,
    sub: str = "user-1",
    tenant_ids: tuple[str, ...] = ("tenant-a",),
    roles: tuple[str, ...] = (),
    exp_offset_seconds: int = 300,
    secret: str = JWT_SECRET,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(time.time()) + exp_offset_seconds,
        "tenant_ids": list(tenant_ids),
        "roles": list(roles),
    }
    encoded_header = _encode_segment(header)
    encoded_payload = _encode_segment(payload)
    signed_portion = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_portion,
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def _bearer_headers(token: str, **extra_headers: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        **extra_headers,
    }


def test_control_plane_requires_bearer_token_when_auth_enabled(integrated_app_factory):
    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.get("/v1/tools")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header is required."


def test_control_plane_rejects_principal_without_control_plane_role(
    integrated_app_factory,
):
    token = _mint_token(roles=("viewer",))

    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.get("/v1/tools", headers=_bearer_headers(token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Principal does not have control-plane access."


def test_mcp_requires_bearer_token_when_auth_enabled(integrated_app_factory):
    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "security-1",
                "method": "initialize",
                "params": {},
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authorization header is required."


def test_mcp_binds_sessions_to_authenticated_identity(integrated_app_factory):
    token = _mint_token(sub="user-1", roles=("ops",))
    attacker_token = _mint_token(sub="user-2", roles=("ops",))

    with _build_authenticated_client(integrated_app_factory) as client:
        initialize_response = client.post(
            "/mcp",
            headers=_bearer_headers(token),
            json={
                "jsonrpc": "2.0",
                "id": "security-2",
                "method": "initialize",
                "params": {},
            },
        )

        tool_response = client.post(
            "/mcp",
            headers=_bearer_headers(
                token,
                **{"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
            ),
            json={
                "jsonrpc": "2.0",
                "id": "security-3",
                "method": "tools/call",
                "params": {
                    "name": "demo.stdio.echo",
                    "arguments": {"text": "router"},
                },
            },
        )

        hijack_response = client.post(
            "/mcp",
            headers=_bearer_headers(
                attacker_token,
                **{"MCP-Session-Id": initialize_response.headers["MCP-Session-Id"]},
            ),
            json={
                "jsonrpc": "2.0",
                "id": "security-4",
                "method": "tools/list",
                "params": {},
            },
        )

    assert initialize_response.status_code == 200
    assert tool_response.status_code == 200
    assert tool_response.json()["result"]["structuredContent"]["tenantId"] == "tenant-a"
    assert tool_response.json()["result"]["structuredContent"]["principalId"] == "user-1"

    assert hijack_response.status_code == 200
    assert hijack_response.json()["error"]["code"] == -32008
    assert hijack_response.json()["error"]["data"]["expectedPrincipalId"] == "user-1"
    assert hijack_response.json()["error"]["data"]["receivedPrincipalId"] == "user-2"


def test_mcp_rejects_cross_tenant_header_override(integrated_app_factory):
    token = _mint_token(tenant_ids=("tenant-a",))

    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.post(
            "/mcp",
            headers=_bearer_headers(token, **{"X-Tenant-Id": "tenant-b"}),
            json={
                "jsonrpc": "2.0",
                "id": "security-5",
                "method": "initialize",
                "params": {},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "X-Tenant-Id is not allowed for this token."


def test_mcp_requires_explicit_tenant_for_multi_tenant_token(integrated_app_factory):
    token = _mint_token(tenant_ids=("tenant-a", "tenant-b"))

    with _build_authenticated_client(integrated_app_factory) as client:
        missing_tenant_response = client.post(
            "/mcp",
            headers=_bearer_headers(token),
            json={
                "jsonrpc": "2.0",
                "id": "security-6",
                "method": "initialize",
                "params": {},
            },
        )
        explicit_tenant_response = client.post(
            "/mcp",
            headers=_bearer_headers(token, **{"X-Tenant-Id": "tenant-b"}),
            json={
                "jsonrpc": "2.0",
                "id": "security-7",
                "method": "initialize",
                "params": {},
            },
        )

    assert missing_tenant_response.status_code == 400
    assert (
        missing_tenant_response.json()["detail"]
        == "X-Tenant-Id is required when the token covers multiple tenants."
    )
    assert explicit_tenant_response.status_code == 200


def test_auth_audit_redacts_email_subject_and_hashes_token(integrated_app_factory):
    token = _mint_token(
        sub="alice@example.com",
        roles=("control-plane",),
    )

    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.get("/v1/tools", headers=_bearer_headers(token))
        events = asyncio.run(client.app.state.services.audit_log.list_audit_events())

    assert response.status_code == 200
    auth_events = [item for item in events if item.event_type == "auth.authenticated"]
    assert auth_events
    latest_event = auth_events[-1]
    assert latest_event.principal_id == "a***@example.com"
    assert latest_event.detail["principalId"] == "a***@example.com"
    assert latest_event.detail["tokenHash"] == hash_token(token)
    assert token not in json.dumps(latest_event.detail, sort_keys=True)


def test_mcp_rejects_expired_token(integrated_app_factory):
    token = _mint_token(exp_offset_seconds=-60)

    with _build_authenticated_client(integrated_app_factory) as client:
        response = client.post(
            "/mcp",
            headers=_bearer_headers(token),
            json={
                "jsonrpc": "2.0",
                "id": "security-8",
                "method": "initialize",
                "params": {},
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "JWT has expired."
