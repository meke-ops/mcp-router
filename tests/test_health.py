from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from internal.application import create_app
from internal.config import Settings


def test_health_endpoint(client):
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "mcp-router"


def test_ready_endpoint(client):
    response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert len(response.json()["dependencies"]) == 2


def test_ready_endpoint_probes_configured_dependencies():
    writer = MagicMock()
    writer.wait_closed = AsyncMock(return_value=None)
    with patch(
        "internal.health.asyncio.open_connection",
        new=AsyncMock(return_value=(MagicMock(), writer)),
    ) as open_connection:
        app = create_app(
            Settings(
                app_env="test",
                require_dependencies_for_readiness=True,
                postgres_dsn=(
                    "postgresql://mcp_router:mcp_router@postgres.service:5432/mcp_router"
                ),
                redis_url="redis://redis.service:6379/0",
            )
        )
        with TestClient(app) as client:
            response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert all(item["healthy"] for item in response.json()["dependencies"])
    assert all(
        "TCP probe succeeded" in item["detail"]
        for item in response.json()["dependencies"]
    )
    assert open_connection.await_count == 2


def test_ready_endpoint_reports_not_ready_when_required_dependency_is_unreachable():
    with patch(
        "internal.health.asyncio.open_connection",
        new=AsyncMock(side_effect=ConnectionRefusedError("connection refused")),
    ):
        app = create_app(
            Settings(
                app_env="test",
                require_dependencies_for_readiness=True,
                postgres_dsn=(
                    "postgresql://mcp_router:mcp_router@postgres.service:5432/mcp_router"
                ),
                redis_url="redis://redis.service:6379/0",
            )
        )
        with TestClient(app) as client:
            response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "not_ready"
    assert not any(item["healthy"] for item in response.json()["dependencies"])


def test_metrics_endpoint_exposes_prometheus_payload(client):
    client.get("/v1/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "mcp_router_build_info" in response.text
    assert 'mcp_router_http_requests_total{method="GET",path="/v1/health",status_code="200"} 1' in response.text
    assert "mcp_router_readiness_status 1" in response.text
