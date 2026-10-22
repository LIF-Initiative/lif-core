"""Endpoint tests for /api-keys (#1033).

Uses a minimal FastAPI app with just AuthMiddleware and the API-key router. The developer_keys
functions are mocked, so these run without a live Postgres; the DB-backed behavior is covered in
test_developer_api_key_service.py. What's under test here is the router's own job: only a
signed-in Cognito user gets through, and their `sub` is what the brick is called with.
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

from datetime import datetime, timezone  # noqa: E402
from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from lif import developer_keys  # noqa: E402
from lif.developer_keys import CreatedDeveloperApiKeyDTO, DeveloperApiKeyDTO  # noqa: E402
from lif.auth.jwt import mint_access  # noqa: E402
from lif.mdr_auth.core import JWT_CONFIG, add_mdr_auth  # noqa: E402
from lif.mdr_restapi import developer_api_key_endpoints  # noqa: E402
from test.utils.lif.mdr.cognito import enable_cognito, make_cognito_id_token  # noqa: E402

pytestmark = pytest.mark.asyncio

VALID_SERVICE_KEY = "changeme1"  # matches settings.mdr__auth__service_api_key__graphql in defaults
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)

# (method, path, json body) for each route
ROUTES = [("GET", "/api-keys/", None), ("POST", "/api-keys/", {"Label": "my app"}), ("DELETE", "/api-keys/7", None)]


@pytest.fixture
def brick(monkeypatch):
    """Replace the three developer_keys functions the router calls."""
    fakes = {
        "create_developer_api_key": mock.AsyncMock(
            return_value=CreatedDeveloperApiKeyDTO(
                Id=7, Label="my app", KeyPrefix="lifk_abcdefg", CreationDate=NOW, Key="lifk_raw"
            )
        ),
        "list_developer_api_keys": mock.AsyncMock(
            return_value=[DeveloperApiKeyDTO(Id=7, Label="my app", KeyPrefix="lifk_abcdefg", CreationDate=NOW)]
        ),
        "revoke_developer_api_key": mock.AsyncMock(return_value=None),
    }
    for name, fake in fakes.items():
        monkeypatch.setattr(developer_keys, name, fake)
    return fakes


@pytest.fixture
async def client(brick):
    app = FastAPI()
    add_mdr_auth(app)

    async def fake_session():
        yield mock.MagicMock()  # handed to the mocked brick functions, never used

    app.dependency_overrides[developer_api_key_endpoints.get_session] = fake_session
    app.include_router(developer_api_key_endpoints.router, prefix="/api-keys")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _stub_cognito_user(monkeypatch, cognito_sub: str):
    """Make every request arrive as a signed-in Cognito user, without a real Cognito JWT.

    The JWT plumbing has its own tests in test_middleware.py."""
    from lif.auth import middleware as auth_middleware
    from lif.mdr_auth import core as auth_core

    async def pass_through(self, request, call_next):
        return await call_next(request)

    async def fake_dispatch(self, request, call_next):
        request.state.principal = "user@example.com"
        request.state.cognito_groups = []
        request.state.cognito_sub = cognito_sub
        request.state.tenant_schema = None
        return await call_next(request)

    monkeypatch.setattr(auth_middleware.AuthMiddleware, "dispatch", pass_through)
    monkeypatch.setattr(auth_core.TenantMiddleware, "dispatch", fake_dispatch)


@pytest.mark.parametrize("method, path, body", ROUTES)
async def test_no_auth_returns_401(client, method, path, body):
    resp = await client.request(method, path, json=body)
    assert resp.status_code == 401


@pytest.mark.parametrize("method, path, body", ROUTES)
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(
            {"Authorization": f"Bearer {mint_access(JWT_CONFIG, {'sub': 'alice@example.com', 'type': 'access'})}"},
            id="legacy-jwt",
        ),
        pytest.param({"X-API-Key": VALID_SERVICE_KEY}, id="service-key"),
    ],
)
async def test_caller_without_cognito_sub_returns_400(client, brick, method, path, body, headers):
    # A legacy password login and a service principal are both authenticated, but neither has a
    # Cognito `sub` to own a key.
    resp = await client.request(method, path, json=body, headers=headers)

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Requires a signed-in Cognito user"}
    for fake in brick.values():
        fake.assert_not_awaited()


async def test_list_is_called_with_the_callers_sub(client, brick, monkeypatch):
    _stub_cognito_user(monkeypatch, "sub-123")

    resp = await client.get("/api-keys/")

    assert resp.status_code == 200
    assert [key["Id"] for key in resp.json()] == [7]
    assert "Key" not in resp.json()[0]
    assert brick["list_developer_api_keys"].await_args.args[1] == "sub-123"


async def test_create_is_called_with_the_callers_sub_and_returns_the_raw_key(client, brick, monkeypatch):
    _stub_cognito_user(monkeypatch, "sub-123")

    resp = await client.post("/api-keys/", json={"Label": "my app"})

    assert resp.status_code == 201
    assert resp.json()["Key"] == "lifk_raw"
    _, owner_sub, data = brick["create_developer_api_key"].await_args.args
    assert owner_sub == "sub-123"
    assert data.Label == "my app"


async def test_revoke_is_called_with_the_callers_sub_and_key_id(client, brick, monkeypatch):
    _stub_cognito_user(monkeypatch, "sub-123")

    resp = await client.delete("/api-keys/7")

    assert resp.status_code == 204
    assert brick["revoke_developer_api_key"].await_args.args[1:] == ("sub-123", 7)


async def test_real_cognito_token_scopes_keys_to_its_sub(client, brick, monkeypatch):
    # No stub: the real middleware decodes the token and sets cognito_sub (#1380).
    enable_cognito(monkeypatch)
    token = make_cognito_id_token(sub="token-sub-1")

    resp = await client.get("/api-keys/", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert brick["list_developer_api_keys"].await_args.args[1] == "token-sub-1"
