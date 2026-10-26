"""Tests for the control-plane API base (#1182): health, fail-closed auth, required config.

`create_app` is exercised directly with a stubbed engine, so no database is needed. The module-level
app still builds an engine at import, which only needs the URL to parse.
"""

import os

os.environ.setdefault("CONTROL_PLANE__DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import lif.auth.cognito as cognito_core  # noqa: E402
from lif.auth.cognito import CognitoAuthConfig  # noqa: E402
from lif.control_plane_restapi import core  # noqa: E402


def _engine(*, reachable: bool = True) -> mock.MagicMock:
    engine = mock.MagicMock()
    if reachable:
        engine.connect.return_value.__aenter__.return_value.execute = mock.AsyncMock()
    else:
        engine.connect.side_effect = OSError("connection refused")
    return engine


async def _client(engine, cognito_config) -> AsyncClient:
    app = core.create_app(engine, cognito_config)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def cognito_on(monkeypatch):
    monkeypatch.setattr(cognito_core, "decode_cognito_jwt", lambda token, config: {"sub": "user-1"})
    return CognitoAuthConfig(user_pool_id="us-east-1_ABC")


async def test_health_check_is_public_and_ok_when_the_database_answers(cognito_on):
    async with await _client(_engine(), cognito_on) as client:
        resp = await client.get("/health-check")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_check_returns_503_when_the_database_is_unreachable(cognito_on):
    async with await _client(_engine(reachable=False), cognito_on) as client:
        resp = await client.get("/health-check")
    assert resp.status_code == 503


async def test_cognito_configured_requires_a_token(cognito_on):
    async with await _client(_engine(), cognito_on) as client:
        missing = await client.get("/anything")
        with_token = await client.get("/anything", headers={"Authorization": "Bearer good.token"})
    assert missing.status_code == 401
    assert with_token.status_code == 404  # past the middleware; no such route yet


async def test_without_a_cognito_pool_fails_closed_without_contacting_cognito(monkeypatch):
    decode = mock.Mock(side_effect=AssertionError("must not try to verify against an empty pool"))
    monkeypatch.setattr(cognito_core, "decode_cognito_jwt", decode)

    async with await _client(_engine(), CognitoAuthConfig()) as client:
        protected = await client.get("/anything", headers={"Authorization": "Bearer some.token"})
        health = await client.get("/health-check")

    assert protected.status_code == 401
    assert health.status_code == 200
    decode.assert_not_called()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_require_env_names_the_missing_variable(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("X_TEST_REQUIRED", raising=False)
    else:
        monkeypatch.setenv("X_TEST_REQUIRED", value)
    with pytest.raises(RuntimeError, match="X_TEST_REQUIRED"):
        core.require_env("X_TEST_REQUIRED")
