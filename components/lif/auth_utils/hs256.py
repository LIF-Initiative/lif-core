"""HS256 JWT minting and verification, with the secret supplied by the caller.

Deliberately reads no environment: each consuming brick owns its secret
(``auth`` requires ``SECRET_KEY`` at import, #1191; ``mdr_auth`` uses MDR
settings) and its claim policy (``type``/``jti``, expiry). Not re-exported from
``lif.auth_utils`` because it imports ``jwt``.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


def encode_hs256(claims: Dict[str, Any], secret: str, expires_delta: timedelta) -> str:
    """Sign a copy of ``claims`` with an ``exp`` of now + ``expires_delta``."""
    to_encode = claims.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + expires_delta})
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_hs256(token: str, secret: str) -> Dict[str, Any]:
    """Verify and decode ``token``; raise a 401 ``HTTPException`` on any failure."""
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        logger.warning("Auth Bearer token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"}
        ) from error
    except jwt.InvalidTokenError as error:
        logger.warning("Auth Bearer token is invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
