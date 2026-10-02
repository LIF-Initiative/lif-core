# cspell:disable
import time
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
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


# ---- decode_cognito_jwt against real RS256 tokens (JWKS client mocked) ----

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_POOL = "us-east-1_TestPool"
_CLIENT_ID = "test-spa-client-id"
_CFG = CognitoAuthConfig(user_pool_id=_POOL, region="us-east-1", client_id=_CLIENT_ID)


@pytest.fixture
def _jwks(monkeypatch):
    signing_key = mock.MagicMock()
    signing_key.key = _private_key.public_key()
    jwk_client = mock.MagicMock()
    jwk_client.get_signing_key_from_jwt.return_value = signing_key
    monkeypatch.setattr(core, "_get_jwk_client", lambda config: jwk_client)


def _token(token_use="id", exp_offset=3600, iss=_CFG.issuer, **claims):
    now = int(time.time())
    payload = {"sub": "cognito-sub-123", "iss": iss, "token_use": token_use, "iat": now, "exp": now + exp_offset}
    if token_use == "id":
        payload["aud"] = _CLIENT_ID
    elif token_use == "access":
        payload["client_id"] = _CLIENT_ID
    payload.update(claims)
    return jwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-id"})


def test_decode_valid_id_token(_jwks):
    payload = core.decode_cognito_jwt(_token(email="alice@example.com", **{"cognito:groups": ["eval-alice"]}), _CFG)
    assert payload["email"] == "alice@example.com"
    assert payload["cognito:groups"] == ["eval-alice"]


def test_decode_valid_access_token(_jwks):
    assert core.decode_cognito_jwt(_token("access", sub="user-sub-456"), _CFG)["sub"] == "user-sub-456"


def test_decode_expired_token_raises(_jwks):
    with pytest.raises(jwt.ExpiredSignatureError):
        core.decode_cognito_jwt(_token(exp_offset=-60), _CFG)


def test_decode_wrong_issuer_raises(_jwks):
    with pytest.raises(jwt.InvalidIssuerError):
        core.decode_cognito_jwt(_token(iss="https://evil.example.com"), _CFG)


def test_decode_wrong_audience_on_id_token_raises(_jwks):
    with pytest.raises(jwt.InvalidTokenError, match="audience"):
        core.decode_cognito_jwt(_token(aud="wrong-client-id"), _CFG)


def test_decode_wrong_client_id_on_access_token_raises(_jwks):
    with pytest.raises(jwt.InvalidTokenError, match="client_id"):
        core.decode_cognito_jwt(_token("access", client_id="wrong-client"), _CFG)


def test_decode_unexpected_token_use_raises(_jwks):
    with pytest.raises(jwt.InvalidTokenError, match="token_use"):
        core.decode_cognito_jwt(_token("refresh"), _CFG)
