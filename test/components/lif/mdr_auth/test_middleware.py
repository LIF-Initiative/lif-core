"""Integration tests for AuthMiddleware with Cognito, legacy JWT, and API key auth.

Uses a minimal FastAPI app (no database) to test the full middleware dispatch:
request → AuthMiddleware → endpoint that echoes back the authenticated principal.
"""

import time
from unittest import mock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from lif.mdr_auth.core import AuthMiddleware, create_access_token

# ---- RSA key pair for test Cognito tokens ----

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

TEST_USER_POOL_ID = "us-east-1_TestPool"
TEST_REGION = "us-east-1"
TEST_CLIENT_ID = "test-spa-client-id"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"


def _make_cognito_id_token(
    email: str = "user@example.com",
    sub: str = "cognito-sub-123",
    groups: list[str] | None = None,
    exp_offset: int = 3600,
    aud: str = TEST_CLIENT_ID,
    iss: str = TEST_ISSUER,
) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "aud": aud,
        "iss": iss,
        "token_use": "id",
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }
    if groups:
        payload["cognito:groups"] = groups
    return pyjwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-id"})


# ---- Minimal FastAPI app with AuthMiddleware ----


def _create_test_app() -> FastAPI:
    """Create a minimal app with AuthMiddleware and an echo endpoint."""
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        return JSONResponse(
            {
                "principal": request.state.principal,
                "cognito_groups": getattr(request.state, "cognito_groups", None),
                "tenant_schema": getattr(request.state, "tenant_schema", None),
            }
        )

    @app.get("/health-check")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture(autouse=True)
def _enable_cognito(monkeypatch):
    """Enable Cognito auth and mock the JWKS client for all tests."""
    import lif.mdr_auth.core as auth_module

    monkeypatch.setattr(auth_module, "COGNITO_USER_POOL_ID", TEST_USER_POOL_ID)
    monkeypatch.setattr(auth_module, "COGNITO_REGION", TEST_REGION)
    monkeypatch.setattr(auth_module, "COGNITO_SPA_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setattr(auth_module, "COGNITO_ENABLED", True)

    mock_jwk_client = mock.MagicMock()
    mock_signing_key = mock.MagicMock()
    mock_signing_key.key = _public_key
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    monkeypatch.setattr(auth_module, "_cognito_jwk_client", mock_jwk_client)
    monkeypatch.setattr(auth_module, "_get_cognito_jwk_client", lambda: mock_jwk_client)


@pytest.fixture
async def client():
    app = _create_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestMiddlewareCognitoPath:
    """Cognito RS256 tokens flowing through the full middleware."""

    async def test_valid_cognito_id_token_sets_principal_to_email(self, client):
        token = _make_cognito_id_token(email="alice@example.com", groups=["eval-alice"])
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["principal"] == "alice@example.com"
        assert body["cognito_groups"] == ["eval-alice"]

    async def test_cognito_token_without_email_falls_back_to_sub(self, client):
        """If the ID token has no email claim, principal falls back to sub."""
        payload = {
            "sub": "cognito-sub-no-email",
            "aud": TEST_CLIENT_ID,
            "iss": TEST_ISSUER,
            "token_use": "id",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = pyjwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-id"})
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["principal"] == "cognito-sub-no-email"

    async def test_expired_cognito_token_returns_401(self, client):
        token = _make_cognito_id_token(exp_offset=-60)
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    async def test_cognito_token_wrong_audience_returns_401(self, client):
        token = _make_cognito_id_token(aud="wrong-client")
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    async def test_cognito_token_wrong_issuer_returns_401(self, client):
        token = _make_cognito_id_token(iss="https://evil.example.com")
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


class TestMiddlewareLegacyPath:
    """Legacy HS256 tokens flowing through the full middleware."""

    async def test_valid_legacy_token_sets_principal(self, client):
        token = create_access_token({"sub": "demo-user@example.com"})
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["principal"] == "demo-user@example.com"

    async def test_legacy_refresh_token_rejected(self, client):
        """Refresh tokens (type != 'access') must not be accepted."""
        from lif.mdr_auth.core import create_refresh_token

        token = create_refresh_token({"sub": "demo-user"})
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "token type" in resp.json()["detail"].lower()


class TestMiddlewareApiKeyPath:
    """API key auth through the middleware — must be unaffected by Cognito changes."""

    async def test_valid_api_key_sets_service_principal(self, client):
        resp = await client.get("/protected", headers={"X-API-Key": "changeme1"})
        assert resp.status_code == 200
        assert resp.json()["principal"] == "service:graphql-service"

    async def test_invalid_api_key_without_bearer_returns_401(self, client):
        resp = await client.get("/protected", headers={"X-API-Key": "bogus-key"})
        assert resp.status_code == 401


class TestMiddlewareEdgeCases:
    """Edge cases and error handling."""

    async def test_no_credentials_returns_401(self, client):
        resp = await client.get("/protected")
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]

    async def test_garbage_bearer_token_returns_401(self, client):
        resp = await client.get("/protected", headers={"Authorization": "Bearer not-a-jwt"})
        assert resp.status_code == 401

    async def test_public_path_bypasses_auth(self, client):
        resp = await client.get("/health-check")
        assert resp.status_code == 200

    async def test_cognito_disabled_falls_through_to_legacy(self, monkeypatch, client):
        """When COGNITO_ENABLED is False, RS256 tokens with kid are rejected (not validated)."""
        import lif.mdr_auth.core as auth_module

        monkeypatch.setattr(auth_module, "COGNITO_ENABLED", False)

        token = _make_cognito_id_token()
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        # Should fail because the legacy HS256 decoder can't handle an RS256 token
        assert resp.status_code == 401


class TestMiddlewareTenantRouting:
    """Tenant-schema resolution (issue #883) integration with the middleware.

    These tests verify that `request.state.tenant_schema` is set to the right
    value for each auth path, based on the TENANT_ROUTING_ENABLED flag and
    the TENANT_SERVICE_SCHEMA config. The sanitize/resolve logic itself is
    unit-tested in test_tenant.py; here we confirm the wiring.
    """

    @pytest.fixture
    def routing_on(self, monkeypatch):
        import lif.mdr_auth.core as auth_module

        monkeypatch.setattr(auth_module, "TENANT_ROUTING_ENABLED", True)
        monkeypatch.setattr(auth_module, "TENANT_SERVICE_SCHEMA", "tenant_lif_team")

    async def test_flag_off_leaves_tenant_schema_none(self, client):
        """PR 2 merges with the flag off; this is the shipped-default behavior."""
        token = _make_cognito_id_token(groups=["eval-jsmith"])
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_schema"] is None

    async def test_cognito_with_group_routes_to_tenant_schema(self, routing_on, client):
        token = _make_cognito_id_token(groups=["eval-jsmith"])
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_schema"] == "tenant_eval_jsmith"

    async def test_api_key_routes_to_service_schema(self, routing_on, client):
        resp = await client.get("/protected", headers={"X-API-Key": "changeme1"})
        assert resp.status_code == 200
        assert resp.json()["tenant_schema"] == "tenant_lif_team"

    async def test_cognito_without_group_falls_back_to_service_schema(self, routing_on, client):
        """Users with no Cognito group shouldn't 500 — route like an API-key caller."""
        token = _make_cognito_id_token(groups=None)
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_schema"] == "tenant_lif_team"

    async def test_legacy_hs256_user_routes_to_service_schema(self, routing_on, client):
        """Legacy demo users (pre-Cognito) share the service schema until they migrate."""
        token = create_access_token({"sub": "demo-user@example.com"})
        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_schema"] == "tenant_lif_team"

    async def test_public_path_does_not_set_tenant_schema(self, routing_on, client):
        """Unauthenticated endpoints skip the auth block; tenant_schema stays None."""
        resp = await client.get("/health-check")
        assert resp.status_code == 200
        # /health-check doesn't echo request.state, so nothing to assert here beyond 200.
