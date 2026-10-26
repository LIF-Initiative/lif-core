"""MDR's HS256 claim policy at /login and /refresh-token (type, jti), on lif.auth.jwt (ADR 0007)."""

# database_setup constructs a SQLAlchemy engine at import time from the
# POSTGRESQL_* env vars. These endpoints never touch the engine, but the URL
# still has to parse.
import os

os.environ.setdefault("POSTGRESQL_USER", "test")
os.environ.setdefault("POSTGRESQL_PASSWORD", "test")
os.environ.setdefault("POSTGRESQL_HOST", "localhost")
os.environ.setdefault("POSTGRESQL_PORT", "5432")
os.environ.setdefault("POSTGRESQL_DB", "test")

from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from lif.auth.jwt import verify  # noqa: E402
from lif.mdr_auth.core import JWT_CONFIG  # noqa: E402
from lif.mdr_restapi import core  # noqa: E402
from lif.mdr_restapi.local_users import hash_password  # noqa: E402

USERNAME = "alice@example.org"
PASSWORD = "correct horse battery staple"


@pytest.fixture
async def client():
    with mock.patch.object(core, "LOCAL_USERS", {USERNAME: hash_password(PASSWORD)}):
        async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as c:
            yield c


async def _login(client) -> dict:
    response = await client.post("/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


async def test_login_mints_typed_access_and_refresh_tokens(client):
    body = await _login(client)
    access = verify(JWT_CONFIG, body["access_token"], expected_type="access")
    refresh = verify(JWT_CONFIG, body["refresh_token"], expected_type="refresh")
    assert access["sub"] == refresh["sub"] == USERNAME
    assert "jti" not in access
    assert refresh["jti"]


async def test_each_login_gets_a_distinct_refresh_jti(client):
    first = verify(JWT_CONFIG, (await _login(client))["refresh_token"])
    second = verify(JWT_CONFIG, (await _login(client))["refresh_token"])
    assert first["jti"] != second["jti"]


async def test_refresh_token_returns_a_new_access_token(client):
    body = await _login(client)
    response = await client.post("/refresh-token", json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 200, response.text
    assert verify(JWT_CONFIG, response.json()["access_token"], expected_type="access")["sub"] == USERNAME


async def test_refresh_with_an_access_token_is_rejected(client):
    body = await _login(client)
    response = await client.post("/refresh-token", json={"refresh_token": body["access_token"]})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type"
