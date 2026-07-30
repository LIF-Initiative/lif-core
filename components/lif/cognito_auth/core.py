"""Reusable Cognito JWT authentication — a single-purpose *decoration* brick.

Per ADR 0004, this is bare capability: an MDR-/tenant-/LDE-independent validator
that answers only "is this a valid Cognito JWT from the configured user pool, and
who is it?" Any service can compose it. The Cognito-verification logic is ported
from `mdr_auth`, decoupled from MDR settings so it is configured per-service via
`CognitoAuthConfig.from_environment(prefix=...)` (mirroring `api_key_auth`). See #1034.

Public surface:
- ``CognitoAuthConfig`` — per-service config (from env).
- ``decode_cognito_jwt(token, config)`` — verify + decode (raises on invalid).
- ``authenticate_request(request, config)`` — extract Bearer + decode; returns
  the claims dict or ``None``. This is the composable *strategy* a composite
  middleware calls (e.g. the LDE "signed key OR Cognito JWT" dispatch).
- ``CognitoAuthMiddleware`` — optional standalone middleware for Cognito-only services.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_BEARER_PREFIX = "Bearer "

# Cache PyJWKClient per (region, pool) so JWKS keys are fetched once per process.
_jwk_clients: dict[tuple[str, str], jwt.PyJWKClient] = {}


@dataclass
class CognitoAuthConfig:
    """Cognito validation config for one service."""

    user_pool_id: str = ""
    region: str = "us-east-1"
    client_id: str = ""
    public_paths: set[str] = field(default_factory=lambda: {"/health", "/health-check"})
    public_path_prefixes: set[str] = field(default_factory=lambda: {"/docs", "/openapi.json"})

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
        ``api_key_auth`` "no keys → disabled" pattern), so a bare deployment
        runs without Cognito.
        """
        return cls(
            user_pool_id=os.environ.get(f"{prefix}__USER_POOL_ID", ""),
            region=os.environ.get(f"{prefix}__REGION", "us-east-1"),
            client_id=os.environ.get(f"{prefix}__CLIENT_ID", ""),
        )


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


def _extract_bearer(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if header.startswith(_BEARER_PREFIX):
        return header[len(_BEARER_PREFIX) :].strip() or None
    return None


def authenticate_request(request: Request, config: CognitoAuthConfig) -> Optional[dict[str, Any]]:
    """Composable strategy: return the Cognito claims for a valid Bearer JWT, else ``None``.

    Never raises — a composite (e.g. LDE's "signed key OR Cognito JWT" dispatch)
    calls this and falls through to the next strategy on ``None``.
    """
    token = _extract_bearer(request)
    if not token:
        return None
    try:
        return decode_cognito_jwt(token, config)
    except jwt.PyJWTError:
        return None


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Standalone Cognito-only middleware for services that want just Cognito.

    Services needing "Cognito JWT *or* something else" should compose
    ``authenticate_request`` in a composite instead (see the LDE base).
    """

    def __init__(self, app, config: CognitoAuthConfig) -> None:
        super().__init__(app)
        self.config = config

    def _is_public(self, path: str) -> bool:
        return path in self.config.public_paths or any(path.startswith(p) for p in self.config.public_path_prefixes)

    async def dispatch(self, request: Request, call_next):
        if self._is_public(request.url.path):
            return await call_next(request)
        claims = authenticate_request(request, self.config)
        if claims is None:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing Cognito token"})
        request.state.cognito_claims = claims
        request.state.cognito_sub = claims.get("sub")
        return await call_next(request)
