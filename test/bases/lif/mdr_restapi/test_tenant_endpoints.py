"""Endpoint tests for POST /tenants/provision.

Uses a minimal FastAPI app with just AuthMiddleware and the tenant router
— the DB service is mocked so these run without a live Postgres. The
Postgres-backed tests that verify clone_lif_schema's actual behavior
belong in integration_tests/ (PR 5), not here.
"""

# database_setup constructs a SQLAlchemy engine at import time from the
# POSTGRESQL_* env vars. These tests never touch the engine (the session
# dependency is overridden below), but the URL still has to parse.
import os

os.environ.setdefault("POSTGRESQL_USER", "test")
os.environ.setdefault("POSTGRESQL_PASSWORD", "test")
os.environ.setdefault("POSTGRESQL_HOST", "localhost")
os.environ.setdefault("POSTGRESQL_PORT", "5432")
os.environ.setdefault("POSTGRESQL_DB", "test")

from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from lif.mdr_auth.core import AuthMiddleware  # noqa: E402
from lif.mdr_restapi import tenant_endpoints  # noqa: E402
from lif.mdr_services.tenant_service import (  # noqa: E402
    InvalidGroupNameError,
    TenantAlreadyExistsError,
)

pytestmark = pytest.mark.asyncio

VALID_SERVICE_KEY = "changeme1"  # matches settings.mdr__auth__service_api_key__graphql in defaults


def _build_app(mock_provision: mock.AsyncMock) -> FastAPI:
    """Create a minimal app with AuthMiddleware and the tenant router.

    Overrides both provision_tenant (the service function) and get_session
    (so we don't need a real DB engine). The middleware's Cognito-JWT and
    API-key paths are exercised as-is.
    """
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    async def fake_session():
        yield mock.MagicMock()  # session instance is never touched in these tests

    app.dependency_overrides[tenant_endpoints.get_session] = fake_session
    app.include_router(tenant_endpoints.router, prefix="/tenants")

    # Patch the provision_tenant name that the endpoint resolved at import time.
    return app


@pytest.fixture
def mock_provision(monkeypatch):
    fake = mock.AsyncMock()
    monkeypatch.setattr(tenant_endpoints, "provision_tenant", fake)
    return fake


@pytest.fixture
async def client(mock_provision):
    app = _build_app(mock_provision)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestProvisionEndpointAuth:
    """Only service callers (API-key principals) can provision tenants."""

    async def test_no_auth_returns_401(self, client):
        resp = await client.post("/tenants/provision", json={"group_name": "lif-team"})
        assert resp.status_code == 401

    async def test_user_jwt_returns_403(self, client, mock_provision):
        """Users with a valid Cognito/legacy JWT must not be able to provision
        tenants — only internal services. Simulated here with a plain bearer
        token that the middleware accepts as the legacy HS256 path."""
        from lif.mdr_auth.core import create_access_token

        token = create_access_token({"sub": "alice@example.com"})
        resp = await client.post(
            "/tenants/provision", json={"group_name": "lif-team"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        mock_provision.assert_not_awaited()

    async def test_invalid_api_key_returns_401(self, client, mock_provision):
        resp = await client.post(
            "/tenants/provision", json={"group_name": "lif-team"}, headers={"X-API-Key": "not-a-real-key"}
        )
        assert resp.status_code == 401
        mock_provision.assert_not_awaited()


class TestProvisionEndpointHappyPath:
    async def test_service_key_returns_201_with_tenant_schema(self, client, mock_provision):
        mock_provision.return_value = "tenant_eval_jsmith"
        resp = await client.post(
            "/tenants/provision", json={"group_name": "eval-jsmith"}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 201
        assert resp.json() == {"tenant_schema": "tenant_eval_jsmith", "created": True}
        mock_provision.assert_awaited_once()
        # Confirm the raw group_name was passed through — sanitization happens in the service layer.
        assert mock_provision.await_args.args[1] == "eval-jsmith"


class TestProvisionEndpointErrorHandling:
    async def test_duplicate_schema_returns_200_idempotent(self, client, mock_provision):
        """Post-confirmation Lambda may retry on Cognito-side errors; re-invoking
        provision for an existing tenant must not fail."""
        mock_provision.side_effect = TenantAlreadyExistsError("tenant_lif_team")
        resp = await client.post(
            "/tenants/provision", json={"group_name": "lif-team"}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 200
        assert resp.json() == {"tenant_schema": "tenant_lif_team", "created": False}

    async def test_invalid_group_name_returns_400(self, client, mock_provision):
        mock_provision.side_effect = InvalidGroupNameError("Group name '---' does not produce a valid tenant schema")
        resp = await client.post(
            "/tenants/provision", json={"group_name": "---"}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 400

    async def test_empty_group_name_rejected_by_pydantic(self, client, mock_provision):
        """Pydantic min_length=1 guard stops empty strings before hitting the service."""
        resp = await client.post(
            "/tenants/provision", json={"group_name": ""}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 422
        mock_provision.assert_not_awaited()

    async def test_missing_body_returns_422(self, client, mock_provision):
        resp = await client.post("/tenants/provision", headers={"X-API-Key": VALID_SERVICE_KEY})
        assert resp.status_code == 422
        mock_provision.assert_not_awaited()
