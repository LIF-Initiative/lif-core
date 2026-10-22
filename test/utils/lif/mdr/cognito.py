"""Real Cognito-style tokens for MDR endpoint tests that need AuthMiddleware's Cognito path to run.

`enable_cognito` turns the Cognito branch on and points the JWKS lookup at a test key pair, so
`make_cognito_id_token` tokens are verified by the real `decode_cognito_jwt`.
"""

import time
from unittest import mock

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

TEST_USER_POOL_ID = "us-east-1_TestPool"
TEST_REGION = "us-east-1"
TEST_CLIENT_ID = "test-spa-client-id"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_USER_POOL_ID}"


def make_cognito_id_token(sub: str, email: str = "user@example.com", groups: list[str] | None = None) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "aud": TEST_CLIENT_ID,
        "iss": TEST_ISSUER,
        "token_use": "id",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    if groups:
        payload["cognito:groups"] = groups
    return pyjwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-id"})


def enable_cognito(monkeypatch) -> None:
    import lif.auth.cognito as cognito_core
    import lif.mdr_auth.core as auth_module
    from lif.auth.cognito import CognitoAuthConfig

    monkeypatch.setattr(
        auth_module,
        "COGNITO_CONFIG",
        CognitoAuthConfig(user_pool_id=TEST_USER_POOL_ID, region=TEST_REGION, client_id=TEST_CLIENT_ID),
    )
    monkeypatch.setattr(auth_module, "COGNITO_ENABLED", True)

    mock_jwk_client = mock.MagicMock()
    mock_jwk_client.get_signing_key_from_jwt.return_value.key = _private_key.public_key()
    monkeypatch.setattr(cognito_core, "_get_jwk_client", lambda config: mock_jwk_client)
