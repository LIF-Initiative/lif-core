import time
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from lif.auth.jwt import JwtConfig, decode_hs256, encode_hs256, jwt_strategy, mint_access, mint_refresh, verify
from lif.auth.principal import AuthError

SECRET = "test-only-hs256-secret"


def test_round_trip_sets_exp():
    payload = decode_hs256(encode_hs256({"sub": "alice"}, SECRET, timedelta(minutes=5)), SECRET)
    assert payload["sub"] == "alice"
    assert abs(payload["exp"] - (time.time() + 5 * 60)) < 5


def test_encode_does_not_mutate_claims():
    claims = {"sub": "alice"}
    encode_hs256(claims, SECRET, timedelta(minutes=5))
    assert claims == {"sub": "alice"}


@pytest.mark.parametrize(
    ("token", "detail"),
    [
        (jwt.encode({"sub": "a", "exp": int(time.time()) - 60}, SECRET, algorithm="HS256"), "Token has expired"),
        (
            jwt.encode({"sub": "a", "exp": int(time.time()) + 60}, "other", algorithm="HS256"),
            "Could not validate credentials",
        ),
        ("not-a-jwt", "Could not validate credentials"),
    ],
)
def test_decode_failures_raise_401_with_bearer_challenge(token, detail):
    with pytest.raises(HTTPException) as exc:
        decode_hs256(token, SECRET)
    assert exc.value.status_code == 401
    assert exc.value.detail == detail
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


# ---- JwtConfig, mint/verify, and the strategy ----


CONFIG = JwtConfig(secret=SECRET)


def _req(authorization=None):
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_config_from_environment_requires_a_real_secret(monkeypatch):
    monkeypatch.setenv("MY_JWT_SECRET", "a-strong-secret")
    assert JwtConfig.from_environment("MY_JWT_SECRET").secret == "a-strong-secret"
    monkeypatch.setenv("MY_JWT_SECRET", "changeme4")
    with pytest.raises(RuntimeError, match="MY_JWT_SECRET"):
        JwtConfig.from_environment("MY_JWT_SECRET")


def test_mint_uses_configured_lifetimes():
    config = JwtConfig(
        secret=SECRET, access_token_expires=timedelta(minutes=2), refresh_token_expires=timedelta(hours=1)
    )
    assert abs(verify(config, mint_access(config, {"sub": "a"}))["exp"] - (time.time() + 120)) < 5
    assert abs(verify(config, mint_refresh(config, {"sub": "a"}))["exp"] - (time.time() + 3600)) < 5


def test_verify_enforces_expected_type():
    token = mint_access(CONFIG, {"sub": "a", "type": "refresh"})
    assert verify(CONFIG, token)["type"] == "refresh"
    with pytest.raises(AuthError, match="Invalid token type"):
        verify(CONFIG, token, expected_type="access")


def test_decode_failures_are_auth_errors():
    with pytest.raises(AuthError):
        decode_hs256("not-a-jwt", SECRET)


def test_jwt_strategy():
    strategy = jwt_strategy(CONFIG)
    assert strategy(_req()) is None
    principal = strategy(_req(f"Bearer {mint_access(CONFIG, {'sub': 'alice'})}"))
    assert principal is not None
    assert (principal.id, principal.method, principal.claims["sub"]) == ("alice", "jwt", "alice")
    with pytest.raises(AuthError, match="Invalid authentication credentials"):
        strategy(_req(f"Bearer {mint_access(CONFIG, {'name': 'no-sub'})}"))
    with pytest.raises(AuthError, match="Could not validate credentials"):
        strategy(_req("Bearer not-a-jwt"))
