# cspell:disable
import jwt
import pytest
from starlette.requests import Request

import lif.cognito_auth.core as core
from lif.cognito_auth import CognitoAuthConfig, authenticate_request


def _req(authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request({"type": "http", "method": "GET", "path": "/exports", "headers": headers})


def test_from_environment_reads_prefixed_vars(monkeypatch):
    monkeypatch.setenv("LDE_AUTH__USER_POOL_ID", "us-east-1_ABC123")
    monkeypatch.setenv("LDE_AUTH__REGION", "us-east-1")
    monkeypatch.setenv("LDE_AUTH__CLIENT_ID", "client-xyz")
    cfg = CognitoAuthConfig.from_environment(prefix="LDE_AUTH")
    assert cfg.is_enabled
    assert cfg.user_pool_id == "us-east-1_ABC123"
    assert cfg.issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ABC123"
    assert cfg.jwks_url.endswith("/.well-known/jwks.json")


def test_disabled_when_no_pool(monkeypatch):
    monkeypatch.delenv("LDE_AUTH__USER_POOL_ID", raising=False)
    assert not CognitoAuthConfig.from_environment(prefix="LDE_AUTH").is_enabled


def test_authenticate_returns_none_without_bearer():
    cfg = CognitoAuthConfig(user_pool_id="us-east-1_ABC")
    assert authenticate_request(_req(), cfg) is None
    assert authenticate_request(_req("Basic zzz"), cfg) is None


def test_authenticate_returns_claims_for_valid_token(monkeypatch):
    cfg = CognitoAuthConfig(user_pool_id="us-east-1_ABC")
    monkeypatch.setattr(core, "decode_cognito_jwt", lambda token, config: {"sub": "user-1", "token_use": "access"})
    assert authenticate_request(_req("Bearer good.token"), cfg) == {"sub": "user-1", "token_use": "access"}


def test_authenticate_returns_none_for_invalid_token(monkeypatch):
    cfg = CognitoAuthConfig(user_pool_id="us-east-1_ABC")

    def boom(token, config):
        raise jwt.InvalidTokenError("bad")

    monkeypatch.setattr(core, "decode_cognito_jwt", boom)
    assert authenticate_request(_req("Bearer bad.token"), cfg) is None


def test_enabled_config_requires_crypto(monkeypatch):
    # A service enabling Cognito without pyjwt[crypto] must fail LOUDLY at startup,
    # not silently 401 every token (the #1093 footgun).
    monkeypatch.setenv("LDE_AUTH__USER_POOL_ID", "us-east-1_ABC123")
    monkeypatch.setattr(jwt.algorithms, "has_crypto", False)
    with pytest.raises(RuntimeError, match=r"pyjwt\[crypto\]"):
        CognitoAuthConfig.from_environment(prefix="LDE_AUTH")


def test_crypto_not_required_when_disabled(monkeypatch):
    # A bare deployment (no pool) never verifies a Cognito token, so the guard must not fire.
    monkeypatch.delenv("LDE_AUTH__USER_POOL_ID", raising=False)
    monkeypatch.setattr(jwt.algorithms, "has_crypto", False)
    assert not CognitoAuthConfig.from_environment(prefix="LDE_AUTH").is_enabled
