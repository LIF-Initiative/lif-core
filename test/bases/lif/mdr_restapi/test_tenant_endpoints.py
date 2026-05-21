"""Endpoint tests for POST /tenants/provision.

Uses a minimal FastAPI app with just AuthMiddleware and the tenant router
— the DB service is mocked so these run without a live Postgres. The
Postgres-backed tests that verify clone_lif_schema's actual behavior
live in test_clone_lif_schema_sql.py.
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


# --- Workspace listing & selection (issue #884 Phase 3 PR 1) ---


def _hs256_user_token(sub: str = "alice@example.com") -> str:
    """Create a legacy HS256 token. Not Cognito — has no cognito:groups."""
    from lif.mdr_auth.core import create_access_token

    return create_access_token({"sub": sub})


def _stub_cognito_principal(
    monkeypatch, principal: str, groups: list[str], *, cognito_sub: str | None = "cognito-sub-test"
):
    """Replace the middleware's auth path so test requests get the desired
    principal + cognito_groups without needing a real Cognito JWT.

    The actual JWT plumbing has its own integration tests in
    test_middleware.py; here we want to exercise endpoint behavior given
    a known authenticated request, not re-validate the JWT plumbing."""
    from lif.mdr_auth import core as auth_core

    original_dispatch = auth_core.AuthMiddleware.dispatch

    async def fake_dispatch(self, request, call_next):
        request.state.principal = principal
        request.state.cognito_groups = groups
        request.state.cognito_sub = cognito_sub
        request.state.tenant_schema = None
        return await call_next(request)

    monkeypatch.setattr(auth_core.AuthMiddleware, "dispatch", fake_dispatch)
    return original_dispatch


class TestListMyWorkspaces:
    async def test_no_auth_returns_401(self, client):
        resp = await client.get("/tenants/mine")
        assert resp.status_code == 401

    async def test_service_principal_returns_403(self, client):
        resp = await client.get("/tenants/mine", headers={"X-API-Key": VALID_SERVICE_KEY})
        assert resp.status_code == 403

    async def test_returns_workspaces_for_user_groups(self, client, monkeypatch):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team", "acme-univ"])
        resp = await client.get("/tenants/mine")
        assert resp.status_code == 200
        assert resp.json() == {
            "workspaces": [
                {"group": "lif-team", "tenant_schema": "tenant_lif_team"},
                {"group": "acme-univ", "tenant_schema": "tenant_acme_univ"},
            ]
        }

    async def test_user_with_no_groups_returns_empty_list(self, client, monkeypatch):
        """Cognito user with no groups: empty list, not 500. Frontend shows
        a 'no workspaces yet' state."""
        _stub_cognito_principal(monkeypatch, "user@example.com", [])
        resp = await client.get("/tenants/mine")
        assert resp.status_code == 200
        assert resp.json() == {"workspaces": []}

    async def test_hs256_user_returns_empty_list(self, client):
        """Legacy HS256 callers have no group concept; empty list is the right answer."""
        resp = await client.get("/tenants/mine", headers={"Authorization": f"Bearer {_hs256_user_token()}"})
        assert resp.status_code == 200
        assert resp.json() == {"workspaces": []}


class TestSelectWorkspace:
    async def test_no_auth_returns_401(self, client):
        resp = await client.post("/tenants/select", json={"group": "lif-team"})
        assert resp.status_code == 401

    async def test_service_principal_returns_403(self, client):
        resp = await client.post(
            "/tenants/select", json={"group": "lif-team"}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 403

    async def test_selecting_a_user_group_sets_cookie(self, client, monkeypatch):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team", "acme-univ"])
        resp = await client.post("/tenants/select", json={"group": "acme-univ"})
        assert resp.status_code == 200
        assert resp.json() == {"group": "acme-univ", "tenant_schema": "tenant_acme_univ"}
        # The Set-Cookie header carries the lif_workspace cookie
        set_cookie = resp.headers.get("set-cookie", "")
        assert "lif_workspace=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()

    async def test_selecting_a_non_member_group_returns_404(self, client, monkeypatch):
        """User isn't in 'acme-univ' — refuse rather than trust the request body."""
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        resp = await client.post("/tenants/select", json={"group": "acme-univ"})
        assert resp.status_code == 404
        assert "lif_workspace=" not in resp.headers.get("set-cookie", "")

    async def test_empty_group_rejected_by_pydantic(self, client, monkeypatch):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        resp = await client.post("/tenants/select", json={"group": ""})
        assert resp.status_code == 422


# --- Invite link endpoints (issue #884 Phase 3 PR 2) ---


class TestCreateInvite:
    async def test_no_auth_returns_401(self, client):
        resp = await client.post("/tenants/invite", json={"group": "lif-team"})
        assert resp.status_code == 401

    async def test_service_principal_returns_403(self, client):
        resp = await client.post(
            "/tenants/invite", json={"group": "lif-team"}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 403

    async def test_creating_invite_for_user_group_returns_token(self, client, monkeypatch):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team", "acme-univ"])
        resp = await client.post("/tenants/invite", json={"group": "acme-univ"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["group"] == "acme-univ"
        assert "." in body["token"]
        assert body["expires_at"] > 0

    async def test_creating_invite_for_non_member_group_returns_404(self, client, monkeypatch):
        """Can't invite to a group you don't belong to. Same 404 semantics as /select."""
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        resp = await client.post("/tenants/invite", json={"group": "acme-univ"})
        assert resp.status_code == 404

    async def test_creating_invite_without_cognito_sub_returns_400(self, client, monkeypatch):
        """HS256 legacy users have no Cognito sub — can't be invite issuers."""
        _stub_cognito_principal(monkeypatch, "demo-user", ["lif-team"], cognito_sub=None)
        resp = await client.post("/tenants/invite", json={"group": "lif-team"})
        assert resp.status_code == 400


class TestAcceptInvite:
    @pytest.fixture
    def mock_cognito(self, monkeypatch):
        """Patch the cognito Admin API at the endpoint's import site so we don't
        need real AWS credentials to test the success/failure branches."""
        from lif.mdr_restapi import tenant_endpoints

        fake = mock.MagicMock()
        monkeypatch.setattr(tenant_endpoints, "add_user_to_group", fake)
        return fake

    def _make_token(self, group: str = "acme-univ", inviter_sub: str = "inviter-sub", max_age: int = 3600) -> str:
        from lif.mdr_auth.invite_token import encode_invite_token

        # Match the default jwt secret used by the endpoint
        return encode_invite_token(group, inviter_sub, secret="changeme4", max_age_seconds=max_age)

    async def test_no_auth_returns_401(self, client, mock_cognito):
        resp = await client.post("/tenants/invite/accept", json={"token": self._make_token()})
        assert resp.status_code == 401
        mock_cognito.assert_not_called()

    async def test_service_principal_returns_403(self, client, mock_cognito):
        resp = await client.post(
            "/tenants/invite/accept", json={"token": self._make_token()}, headers={"X-API-Key": VALID_SERVICE_KEY}
        )
        assert resp.status_code == 403
        mock_cognito.assert_not_called()

    async def test_valid_token_adds_user_to_group(self, client, monkeypatch, mock_cognito):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"], cognito_sub="acceptor-sub-1")
        resp = await client.post("/tenants/invite/accept", json={"token": self._make_token(group="acme-univ")})
        assert resp.status_code == 200
        assert resp.json() == {"group": "acme-univ", "tenant_schema": "tenant_acme_univ", "inviter_sub": "inviter-sub"}
        # Confirm we called Cognito with the acceptor's sub, not the inviter's
        call = mock_cognito.call_args
        assert call.kwargs["username"] == "acceptor-sub-1"
        assert call.kwargs["group_name"] == "acme-univ"

    async def test_malformed_token_returns_400(self, client, monkeypatch, mock_cognito):
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        resp = await client.post("/tenants/invite/accept", json={"token": "not-a-real-token"})
        assert resp.status_code == 400
        mock_cognito.assert_not_called()

    async def test_expired_token_returns_410(self, client, monkeypatch, mock_cognito):
        """Expired tokens get the dedicated 410 Gone status (not 400) so the
        frontend can show 'ask for a fresh invite' instead of a generic error."""
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        token = self._make_token(max_age=-60)  # already expired
        resp = await client.post("/tenants/invite/accept", json={"token": token})
        assert resp.status_code == 410
        mock_cognito.assert_not_called()

    async def test_token_for_group_with_empty_sanitized_schema_returns_400(self, client, monkeypatch, mock_cognito):
        """Forged or stale token naming a group that sanitizes to empty."""
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"])
        bad_token = self._make_token(group="---")
        resp = await client.post("/tenants/invite/accept", json={"token": bad_token})
        assert resp.status_code == 400
        mock_cognito.assert_not_called()

    async def test_cognito_admin_failure_returns_500(self, client, monkeypatch, mock_cognito):
        from lif.mdr_auth.cognito_admin import CognitoAdminError

        mock_cognito.side_effect = CognitoAdminError("throttled")
        _stub_cognito_principal(monkeypatch, "user@example.com", ["lif-team"], cognito_sub="acceptor-sub-1")
        resp = await client.post("/tenants/invite/accept", json={"token": self._make_token()})
        assert resp.status_code == 500

    async def test_accept_without_cognito_sub_returns_400(self, client, monkeypatch, mock_cognito):
        """HS256 legacy users have no Cognito sub — can't be invite acceptors
        even when the token itself is valid. Must short-circuit before any
        Cognito Admin API call."""
        _stub_cognito_principal(monkeypatch, "demo-user", ["lif-team"], cognito_sub=None)
        resp = await client.post("/tenants/invite/accept", json={"token": self._make_token()})
        assert resp.status_code == 400
        mock_cognito.assert_not_called()
