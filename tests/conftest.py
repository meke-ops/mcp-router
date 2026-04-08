import pytest
from fastapi.testclient import TestClient

from internal.application import create_app
from internal.config import Settings


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
