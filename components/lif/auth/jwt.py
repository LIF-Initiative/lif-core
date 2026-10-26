"""HS256 JWT identity provider: the one implementation of mint/verify (ADR 0007).

The signing secret is read only through ``JwtConfig.from_environment``, which
fails loudly when it is unset or a published placeholder (``lif.auth.config``).
Each service keeps its own claim policy (e.g. MDR's ``type``/``jti``) by passing
claims in and an ``expected_type`` to ``verify``.

Not re-exported from ``lif.auth`` because it imports ``jwt``: GraphQL packages
this brick but does not ship ``pyjwt``.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from starlette.requests import Request

from lif.auth.config import require_env
from lif.auth.principal import AuthError, Principal, Strategy
from lif.auth.request import extract_bearer_token

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


@dataclass(frozen=True)
class JwtConfig:
    """Signing secret and token lifetimes for one service."""

    secret: str
    access_token_expires: timedelta = timedelta(minutes=30)
    refresh_token_expires: timedelta = timedelta(days=7)

    @classmethod
    def from_environment(cls, secret_var: str, **lifetimes: timedelta) -> "JwtConfig":
        """Read the secret from ``secret_var``; raises naming it when unset or a placeholder."""
        return cls(secret=require_env(secret_var), **lifetimes)


def encode_hs256(claims: Dict[str, Any], secret: str, expires_delta: timedelta) -> str:
    """Sign a copy of ``claims`` with an ``exp`` of now + ``expires_delta``."""
    to_encode = claims.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + expires_delta})
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_hs256(token: str, secret: str) -> Dict[str, Any]:
    """Verify and decode ``token``; raise ``AuthError`` (a 401) on any failure."""
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        logger.warning("Auth Bearer token has expired")
        raise AuthError("Token has expired") from error
    except jwt.InvalidTokenError as error:
        logger.warning("Auth Bearer token is invalid")
        raise AuthError("Could not validate credentials") from error


def mint_access(config: JwtConfig, claims: Dict[str, Any]) -> str:
    """Sign an access token with the config's access lifetime."""
    return encode_hs256(claims, config.secret, config.access_token_expires)


def mint_refresh(config: JwtConfig, claims: Dict[str, Any]) -> str:
    """Sign a refresh token with the config's refresh lifetime."""
    return encode_hs256(claims, config.secret, config.refresh_token_expires)


def verify(config: JwtConfig, token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """Decode ``token``; when ``expected_type`` is given, also require ``type == expected_type``."""
    payload = decode_hs256(token, config.secret)
    if expected_type is not None and payload.get("type") != expected_type:
        logger.warning("Auth Bearer token 'type' is not '%s'", expected_type)
        raise AuthError("Invalid token type")
    return payload


def jwt_strategy(config: JwtConfig, expected_type: Optional[str] = None) -> Strategy:
    """Authenticate an HS256 bearer token; the principal id is its ``sub``.

    No bearer token → ``None``. An invalid, expired, wrong-type, or sub-less token → ``AuthError``.
    """

    def authenticate(request: Request) -> Optional[Principal]:
        token = extract_bearer_token(request)
        if token is None:
            return None
        payload = verify(config, token, expected_type)
        subject = payload.get("sub")
        if not subject:
            raise AuthError("Invalid authentication credentials")
        return Principal(id=subject, method="jwt", claims=payload)

    return authenticate
