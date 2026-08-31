import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


# --- JWT Settings ---
_secret_key: str | None = None


def require_secret_key() -> str:
    """Return the JWT signing key, or fail loudly if it is not configured.

    Deliberately has no fallback. A default here would be a convenience for
    developers that makes insecurity the default: a missing or misnamed variable
    would stop being a loud failure and become a service running happily on a
    publicly-known value. See #1191.

    Resolved on first use rather than at import, so consumers of this brick that
    never issue or verify JWTs are not forced to configure a secret they do not
    use -- `example_data_source_rest_api` imports only `verify_token`, which
    checks a static `API_TOKEN` and never touches this key.

    Services that DO mint or verify JWTs should call this once at startup so the
    failure lands at boot rather than at a user's first login; see
    `bases/lif/advisor_restapi`.
    """
    global _secret_key
    if _secret_key is None:
        value = os.environ.get("SECRET_KEY")
        if value is None or not value.strip():
            raise RuntimeError(
                "SECRET_KEY is not set. It signs and verifies JWTs, so there is no safe "
                "default. Set SECRET_KEY to a strong secret (in AWS it is supplied from "
                "SSM via the service's taskdef-includes; locally, export it or set it in "
                "your .env)."
            )
        _secret_key = value.strip()
    return _secret_key


ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
REFRESH_TOKEN_EXPIRE_DAYS: int = 7

security = HTTPBearer()


# --- Token Utilities ---
def create_access_token(data: dict) -> str:
    """Create a JWT access token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, require_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, require_secret_key(), algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode a JWT token and return the payload."""
    try:
        return jwt.decode(token, require_secret_key(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


def verify_token(token: str) -> None:
    """Verify if the token matches the environment variable API_TOKEN."""
    if token != os.getenv("API_TOKEN"):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Decode JWT and return the username (subject) if valid."""
    try:
        payload = jwt.decode(credentials.credentials, require_secret_key(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
