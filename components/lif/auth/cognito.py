"""Cognito identity provider: RS256/JWKS validation plus a strategy (ADR 0007).

Answers only "is this a valid Cognito JWT from the configured user pool, and who
is it?" with no MDR, tenant, or LDE concerns (ADR 0004). Configured per service
via ``CognitoAuthConfig.from_environment(prefix=...)``. See #1034.

Public surface:
- ``CognitoAuthConfig`` — per-service config (from env).
- ``decode_cognito_jwt(token, config)`` — verify + decode (raises on invalid).
- ``authenticate_request(request, config)`` — extract Bearer + decode; returns
  the claims dict or ``None``, never raises.
- ``cognito_strategy(config)`` — the same check as a strategy for
  ``lif.auth.middleware.AuthMiddleware``; the principal id is the token's ``sub``.

Not re-exported from ``lif.auth`` because it imports ``jwt``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import jwt
import jwt.algorithms  # ensure the submodule is imported for `jwt.algorithms.has_crypto`
from starlette.requests import Request

from lif.auth.principal import Principal, Strategy
from lif.auth.request import extract_bearer_token

logger = logging.getLogger(__name__)

# Cache PyJWKClient per (region, pool) so JWKS keys are fetched once per process.
_jwk_clients: dict[tuple[str, str], jwt.PyJWKClient] = {}


def require_crypto() -> None:
    """Fail loudly at startup if pyjwt lacks the crypto backend for RS256 (see #1093).

    Cognito tokens are RS256; without `cryptography` (the ``pyjwt[crypto]`` extra) every
    ``jwt.decode`` raises ``PyJWTError``, which ``authenticate_request`` swallows → every
    token silently 401s. Any service composing this brick MUST depend on ``pyjwt[crypto]``;
    this converts that footgun into an obvious boot-time error instead of a silent reject.
    """
    if not jwt.algorithms.has_crypto:
        raise RuntimeError(
            "lif.auth.cognito requires the 'cryptography' package for RS256 JWT verification. "
            "Depend on `pyjwt[crypto]` (plain `pyjwt` ships without it and silently rejects "
            "every Cognito token). See #1093."
        )


@dataclass
class CognitoAuthConfig:
    """Cognito validation config for one service."""

    user_pool_id: str = ""
    region: str = "us-east-1"
    client_id: str = ""

    @property
    def is_enabled(self) -> bool:
        """Cognito auth is active only when a user pool is configured."""
        return bool(self.user_pool_id)

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    @classmethod
    def from_environment(cls, prefix: str = "COGNITO_AUTH") -> "CognitoAuthConfig":
        """Load config from ``{PREFIX}__USER_POOL_ID`` / ``__REGION`` / ``__CLIENT_ID``.

        Auth self-disables when ``USER_POOL_ID`` is unset (matching the
        ``lif.auth.api_key`` "no keys → disabled" pattern), so a bare deployment
        runs without Cognito.
        """
        config = cls(
            user_pool_id=os.environ.get(f"{prefix}__USER_POOL_ID", ""),
            region=os.environ.get(f"{prefix}__REGION", "us-east-1"),
            client_id=os.environ.get(f"{prefix}__CLIENT_ID", ""),
        )
        if config.is_enabled:
            require_crypto()
        return config


def _get_jwk_client(config: CognitoAuthConfig) -> jwt.PyJWKClient:
    key = (config.region, config.user_pool_id)
    if key not in _jwk_clients:
        _jwk_clients[key] = jwt.PyJWKClient(config.jwks_url, cache_keys=True, lifespan=3600)
    return _jwk_clients[key]


def decode_cognito_jwt(token: str, config: CognitoAuthConfig) -> dict[str, Any]:
    """Verify + decode a Cognito JWT (RS256/JWKS). Raises ``jwt.PyJWTError`` on invalid.

    Validates signature, issuer, and that the token belongs to the configured
    client (``aud`` for ID tokens, ``client_id`` for access tokens).
    """
    signing_key = _get_jwk_client(config).get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=config.issuer,
        options={"verify_aud": False},  # Cognito access tokens carry client_id, not aud
    )
    token_use = payload.get("token_use")
    if token_use == "id":
        if config.client_id and payload.get("aud") != config.client_id:
            raise jwt.InvalidTokenError("ID token audience does not match client ID")
    elif token_use == "access":
        if config.client_id and payload.get("client_id") != config.client_id:
            raise jwt.InvalidTokenError("Access token client_id does not match client ID")
    else:
        raise jwt.InvalidTokenError(f"Unexpected token_use: {token_use}")
    return payload


def authenticate_request(request: Request, config: CognitoAuthConfig) -> Optional[dict[str, Any]]:
    """Composable strategy: return the Cognito claims for a valid Bearer JWT, else ``None``.

    Never raises — a composite (e.g. LDE's "signed key OR Cognito JWT" dispatch)
    calls this and falls through to the next strategy on ``None``.
    """
    token = extract_bearer_token(request)
    if not token:
        return None
    try:
        return decode_cognito_jwt(token, config)
    except jwt.PyJWTError as exc:
        logger.warning("Cognito JWT rejected: %s", exc)
        return None


def cognito_strategy(config: CognitoAuthConfig) -> Strategy:
    """Authenticate a Cognito bearer token; the principal id is its ``sub``.

    Returns ``None`` (rather than raising) for a missing or invalid token, because a
    bearer token may belong to another strategy in the same middleware, e.g. an
    HS256 token alongside Cognito.
    """

    def authenticate(request: Request) -> Optional[Principal]:
        claims = authenticate_request(request, config)
        if claims is None or not claims.get("sub"):
            return None
        return Principal(id=claims["sub"], method="cognito", claims=claims)

    return authenticate
