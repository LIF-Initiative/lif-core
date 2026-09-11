import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


# --- JWT Settings ---
def _require_env(name: str) -> str:
    """Read a required secret from the environment, or fail loudly at import.

    Deliberately has no fallback. A default here would be a convenience for
    developers that makes insecurity the default: a missing or misnamed variable
    would stop being a loud startup failure and become a service running happily
    on a publicly-known value. See #1191.

    Checked at import rather than on first use so a misconfigured service fails
    to start instead of failing at a user's first login. That is only reasonable
    because this brick is JWT-only -- the static ``API_TOKEN`` check that used to
    live here moved to ``api_token_auth`` so a service needing only that check is
    not forced to supply a signing key it never uses.
    """
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"{name} is not set. It signs and verifies JWTs, so there is no safe default. "
            f"Set {name} to a strong secret (in AWS it is supplied from SSM via the "
            f"service's taskdef-includes; locally, export it or set it in your .env)."
        )
    return value.strip()


SECRET_KEY: str = _require_env("SECRET_KEY")
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
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode a JWT token and return the payload."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Decode JWT and return the username (subject) if valid."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
