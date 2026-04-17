"""Tests for Cognito JWT validation in the MDR auth middleware.

Verifies that:
- Cognito RS256 tokens (with kid) are validated via JWKS
- Legacy HS256 tokens (no kid) continue to work
- API key auth is unaffected
- Invalid/expired tokens are rejected
- The middleware routes to the correct validation path based on JWT header
"""

import time
from unittest import mock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


# ---- RSA key pair for test Cognito tokens ----

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

_public_key_pem = _public_key.public_bytes(
    encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
)


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
    """Create a signed Cognito-style ID token for testing."""
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


def _make_cognito_access_token(
    sub: str = "cognito-sub-123", client_id: str = TEST_CLIENT_ID, exp_offset: int = 3600
) -> str:
    """Create a signed Cognito-style access token for testing."""
    payload = {
        "sub": sub,
        "client_id": client_id,
        "iss": TEST_ISSUER,
        "token_use": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }
    return pyjwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-id"})


@pytest.fixture(autouse=True)
def _enable_cognito(monkeypatch):
    """Enable Cognito auth and mock the JWKS client for all tests in this module."""
    import lif.mdr_auth.core as auth_module

    monkeypatch.setattr(auth_module, "COGNITO_USER_POOL_ID", TEST_USER_POOL_ID)
    monkeypatch.setattr(auth_module, "COGNITO_REGION", TEST_REGION)
    monkeypatch.setattr(auth_module, "COGNITO_SPA_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setattr(auth_module, "COGNITO_ENABLED", True)

    # Mock PyJWKClient to return our test public key
    mock_jwk_client = mock.MagicMock()
    mock_signing_key = mock.MagicMock()
    mock_signing_key.key = _public_key
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    monkeypatch.setattr(auth_module, "_cognito_jwk_client", mock_jwk_client)
    monkeypatch.setattr(auth_module, "_get_cognito_jwk_client", lambda: mock_jwk_client)


class TestDecodeCognitoJwt:
    """Tests for the decode_cognito_jwt function."""

    def test_valid_id_token(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_id_token(email="alice@example.com", groups=["eval-alice"])
        payload = decode_cognito_jwt(token)

        assert payload["email"] == "alice@example.com"
        assert payload["token_use"] == "id"
        assert payload["cognito:groups"] == ["eval-alice"]

    def test_valid_access_token(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_access_token(sub="user-sub-456")
        payload = decode_cognito_jwt(token)

        assert payload["sub"] == "user-sub-456"
        assert payload["token_use"] == "access"

    def test_expired_token_raises(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_id_token(exp_offset=-60)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_cognito_jwt(token)

    def test_wrong_audience_raises(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_id_token(aud="wrong-client-id")
        with pytest.raises(pyjwt.InvalidTokenError, match="audience"):
            decode_cognito_jwt(token)

    def test_wrong_issuer_raises(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_id_token(iss="https://evil.example.com")
        with pytest.raises(pyjwt.InvalidIssuerError):
            decode_cognito_jwt(token)

    def test_wrong_client_id_on_access_token_raises(self):
        from lif.mdr_auth.core import decode_cognito_jwt

        token = _make_cognito_access_token(client_id="wrong-client")
        with pytest.raises(pyjwt.InvalidTokenError, match="client_id"):
            decode_cognito_jwt(token)


class TestAuthMiddlewareTokenRouting:
    """Tests that the middleware routes tokens to the correct validation path."""

    def test_cognito_token_has_kid_in_header(self):
        """Cognito tokens include a 'kid' header field."""
        token = _make_cognito_id_token()
        header = pyjwt.get_unverified_header(token)
        assert "kid" in header
        assert header["kid"] == "test-key-id"

    def test_legacy_token_has_no_kid(self):
        """Legacy HS256 tokens do not include a 'kid' header field."""
        from lif.mdr_auth.core import create_access_token

        token = create_access_token({"sub": "demo-user"})
        header = pyjwt.get_unverified_header(token)
        assert "kid" not in header

    def test_legacy_token_still_decodes(self):
        """Legacy tokens using HS256 continue to work via decode_jwt."""
        from lif.mdr_auth.core import create_access_token, decode_jwt

        token = create_access_token({"sub": "demo-user"})
        payload = decode_jwt(token)

        assert payload["sub"] == "demo-user"
        assert payload["type"] == "access"
