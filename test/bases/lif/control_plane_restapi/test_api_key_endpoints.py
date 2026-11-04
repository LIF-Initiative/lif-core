"""The control plane's developer-key endpoints (#1182, ADR 0008).

Tokens are stubbed: each test token maps to a `sub` and its `cognito:groups`. The membership and
input checks run with no database. The issue → list → revoke flow runs against a throwaway
PostgreSQL with the real migration applied, and skips when PostgreSQL isn't installed (CI has it).
"""

import os

os.environ.setdefault("CONTROL_PLANE__DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import pytest  # noqa: E402
import testing.postgresql  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

import lif.auth.cognito as cognito_core  # noqa: E402
from lif.auth.cognito import CognitoAuthConfig  # noqa: E402
from lif.auth.principal import Principal  # noqa: E402
from lif.control_plane_restapi import core  # noqa: E402

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "projects"
    / "lif_control_plane_database"
    / "migrations"
    / "V1.0__developer_api_keys.sql"
)

# token -> claims. Group "Team-A" maps to workspace tenant_team_a.
TOKENS = {
    "alice": {"sub": "alice", "cognito:groups": ["Other", "Team-A"]},
    "alice-left": {"sub": "alice"},  # alice after leaving every group
    "bob": {"sub": "bob", "cognito:groups": ["Team-A"]},
    "carol": {"sub": "carol", "cognito:groups": ["Team-B"]},
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def stub_tokens(monkeypatch):
    monkeypatch.setattr(cognito_core, "decode_cognito_jwt", lambda token, config: TOKENS[token])


def _client(engine) -> AsyncClient:
    app = core.create_app(engine, CognitoAuthConfig(user_pool_id="us-east-1_ABC", client_id="client-1"))
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def no_db():
    """An engine that fails the test if a request reaches the database."""
    engine = mock.MagicMock()
    engine.connect.side_effect = AssertionError("must not reach the database")
    return engine


@pytest.mark.parametrize("method", ["post", "get"])
async def test_a_non_member_gets_403_before_the_database(no_db, method):
    async with _client(no_db) as client:
        kwargs = {"json": {"Label": "x"}} if method == "post" else {}
        resp = await getattr(client, method)("/api-keys/?workspace=tenant_team_a", headers=_auth("carol"), **kwargs)
    assert resp.status_code == 403


async def test_a_caller_with_no_groups_is_not_a_member(no_db):
    async with _client(no_db) as client:
        resp = await client.get("/api-keys/?workspace=tenant_team_a", headers=_auth("alice-left"))
    assert resp.status_code == 403


@pytest.mark.parametrize("query", ["", "?workspace="])
async def test_the_workspace_is_required(no_db, query):
    async with _client(no_db) as client:
        resp = await client.get(f"/api-keys/{query}", headers=_auth("alice"))
    assert resp.status_code == 422


async def test_the_workspace_is_compared_whole_not_built_from_the_group(no_db):
    # "Team-A" maps to tenant_team_a. A bare group name, or a different spelling of the schema, is no match.
    async with _client(no_db) as client:
        for workspace in ("Team-A", "team_a", "TENANT_TEAM_A"):
            resp = await client.get(f"/api-keys/?workspace={workspace}", headers=_auth("alice"))
            assert resp.status_code == 403, workspace


async def test_without_a_token_every_key_path_is_401(no_db):
    async with _client(no_db) as client:
        assert (await client.get("/api-keys/?workspace=tenant_team_a")).status_code == 401
        assert (await client.delete("/api-keys/1")).status_code == 401


@pytest.fixture(scope="module")
def postgres_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    parsed = urlparse(postgresql.url())
    yield f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    postgresql.stop()


@pytest.fixture
async def engine(postgres_url):
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS "DeveloperApiKeys"'))
        raw = (await conn.get_raw_connection()).driver_connection
        await raw.execute(MIGRATION.read_text())  # a multi-statement script, as initdb runs it
    yield engine
    await engine.dispose()


async def test_issue_list_and_revoke(engine):
    async with _client(engine) as client:
        created = await client.post("/api-keys/?workspace=tenant_team_a", json={"Label": "ci"}, headers=_auth("alice"))
        assert created.status_code == 201
        key = created.json()
        assert key["Key"].startswith("lifk_")

        await client.post("/api-keys/?workspace=tenant_team_a", json={"Label": "bob's"}, headers=_auth("bob"))

        listed = await client.get("/api-keys/?workspace=tenant_team_a", headers=_auth("alice"))
        assert listed.status_code == 200
        assert [(k["Id"], k["Label"]) for k in listed.json()] == [(key["Id"], "ci")]
        assert "Key" not in listed.json()[0]

        # Another user's key is a 404, not a 403, so key ids aren't revealed.
        assert (await client.delete(f"/api-keys/{key['Id']}", headers=_auth("bob"))).status_code == 404

        # Alice can revoke after leaving every group: revoking needs ownership only.
        assert (await client.delete(f"/api-keys/{key['Id']}", headers=_auth("alice-left"))).status_code == 204

        listed = await client.get("/api-keys/?workspace=tenant_team_a", headers=_auth("alice"))
        assert listed.json()[0]["RevokedDate"] is not None


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api-keys/?workspace=tenant_team_a"),
        ("get", "/api-keys/?workspace=tenant_team_a"),
        ("delete", "/api-keys/1"),
    ],
)
async def test_only_a_cognito_user_owns_keys(no_db, monkeypatch, method, path):
    # Cognito is the only strategy today. This swaps in one that authenticates a non-Cognito caller
    # (as an API-key or local-login strategy would) to pin ADR 0008 decision 1 at the endpoints: the
    # caller is refused before the database, even though its claims would pass the membership check.
    def service_strategy(request):
        return Principal(id="service:x", method="api_key", claims={"cognito:groups": ["Team-A"]})

    monkeypatch.setattr(core, "cognito_strategy", lambda config: service_strategy)
    async with _client(no_db) as client:
        kwargs = {"json": {"Label": "x"}} if method == "post" else {}
        resp = await client.request(method.upper(), path, headers=_auth("anything"), **kwargs)
    assert resp.status_code == 400
