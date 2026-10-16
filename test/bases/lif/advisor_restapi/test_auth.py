"""Advisor inbound auth: lif.auth.AuthMiddleware + jwt_strategy (ADR 0007).

Carries over the token-policy checks from the deleted lif.auth.core module.
"""

import os
import subprocess
import sys
import time

import jwt
from httpx import ASGITransport, AsyncClient
from lif.advisor_restapi import core
from lif.auth.jwt import mint_access, mint_refresh, verify


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test")


def test_access_token_lasts_30_minutes_and_refresh_7_days():
    access = verify(core.JWT_CONFIG, mint_access(core.JWT_CONFIG, {"sub": "alice"}))
    refresh = verify(core.JWT_CONFIG, mint_refresh(core.JWT_CONFIG, {"sub": "alice"}))
    assert abs(access["exp"] - (time.time() + 30 * 60)) < 5
    assert abs(refresh["exp"] - (time.time() + 7 * 24 * 60 * 60)) < 5


async def test_valid_token_reaches_the_route_as_its_sub():
    token = mint_access(core.JWT_CONFIG, {"sub": "someone@example.org"})
    async with _client() as client:
        resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    # Authenticated: the route ran (404 because this user isn't a demo persona).
    assert resp.status_code == 404
    assert resp.json() == {"detail": "User not found"}


async def test_expired_token_is_401():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) - 60}, core.JWT_CONFIG.secret, algorithm="HS256")
    async with _client() as client:
        resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Token has expired"}


async def test_token_without_sub_is_401():
    async with _client() as client:
        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {mint_access(core.JWT_CONFIG, {'name': 'x'})}"}
        )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid authentication credentials"}


async def test_public_routes_and_cors_preflight_skip_auth():
    async with _client() as client:
        assert (await client.get("/health")).status_code == 200
        preflight = await client.options(
            "/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
        )
    assert preflight.status_code == 200


def test_missing_secret_key_fails_at_startup():
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    result = subprocess.run(
        [sys.executable, "-c", "import lif.advisor_restapi.core"], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "SECRET_KEY is not set" in result.stderr
