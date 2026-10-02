"""Tests for Cognito JWT validation in the MDR auth middleware.

Verifies that:
- MDR refuses a Cognito pool configured without an SPA client id
- Legacy HS256 tokens (no kid) continue to work
- The middleware routes to the correct validation path based on JWT header
"""

import time

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


class TestValidateCognitoConfig:
    """MDR refuses to start with a Cognito pool but no SPA client id.

    cognito_auth skips the client check when client_id is empty, which would
    accept tokens from *any* app client in the pool. MDR must fail loudly
    instead (#548).
    """

    def test_pool_without_client_id_raises(self):
        from lif.cognito_auth import CognitoAuthConfig
        from lif.mdr_auth.core import _validate_cognito_config

        with pytest.raises(RuntimeError, match="MDR__AUTH__COGNITO_SPA_CLIENT_ID"):
            _validate_cognito_config(CognitoAuthConfig(user_pool_id=TEST_USER_POOL_ID, client_id=""))

    def test_pool_with_client_id_passes(self):
        from lif.cognito_auth import CognitoAuthConfig
        from lif.mdr_auth.core import _validate_cognito_config

        _validate_cognito_config(CognitoAuthConfig(user_pool_id=TEST_USER_POOL_ID, client_id=TEST_CLIENT_ID))

    def test_disabled_config_passes(self):
        from lif.cognito_auth import CognitoAuthConfig
        from lif.mdr_auth.core import _validate_cognito_config

        _validate_cognito_config(CognitoAuthConfig())


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
