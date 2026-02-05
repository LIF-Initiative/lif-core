"""
Core authentication module with JWT token handling and API key support
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from lif.mdr_utils.collection_utils import convert_csv_to_set
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.logger_config import get_logger
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger(__name__)

settings = get_settings()

# JWT configuration
SECRET_KEY = settings.mdr__auth__jwt_secret_key
ALGORITHM = "HS256"

API_KEY_HEADER_NAME = "X-API-Key"
# Recommended to use hard-to-guess names for the API keys.
API_KEYS = {
    settings.mdr__auth__service_api_key__graphql: "graphql-service",
    settings.mdr__auth__service_api_key__semantic_search: "semantic-search-service",
    settings.mdr__auth__service_api_key__translator: "translator-service",
}

METHODS_TO_REQUIRE_AUTH = convert_csv_to_set(settings.mdr__auth__methods_to_require_auth)

PUBLIC_ALLOWLIST_EXACT: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_exact)

PUBLIC_ALLOWLIST_STARTS_WITH: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_starts_with)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.mdr__auth__access_token_expire_minutes)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.mdr__auth__refresh_token_expire_days)
    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
            "jti": str(uuid.uuid4()),  # JWT ID for token tracking
        }
    )
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_ALLOWLIST_EXACT or any(path.startswith(prefix) for prefix in PUBLIC_ALLOWLIST_STARTS_WITH)


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _extract_api_key(request: Request) -> Optional[str]:
    return request.headers.get(API_KEY_HEADER_NAME)


def _verify_api_key(api_key: Optional[str]) -> Optional[str]:
    """Verify API key and return service name if valid"""

    if api_key in API_KEYS:
        service_name = API_KEYS[api_key]
        logger.info("API key authenticated for service: %s", service_name)
        return service_name

    return None


def _build_unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer, X-API-Key"},
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Get current user from JWT token OR authenticate via API key
        Returns username for JWT or service name for API key
        """
        request.state.principal = None

        if request.method not in METHODS_TO_REQUIRE_AUTH or _is_public_path(request.url.path):
            return await call_next(request)

        try:
            # Try API key authentication first
            api_key = _extract_api_key(request)
            if api_key:
                service_name = _verify_api_key(api_key)
                if service_name:
                    logger.info("Auth API key verified for service: %s", service_name)
                    request.state.principal = f"service:{service_name}"
                else:
                    logger.warning("Auth API key unknown or invalid. Trying Bearer token...")

            if getattr(request.state, "principal", None) is None:
                # Fall back to JWT authentication
                credentials = _extract_bearer_token(request)
                if not credentials:
                    logger.warning("Auth blocked due to no credentials provided")
                    return _build_unauthorized(detail="Authentication required: Provide either Bearer token or API key")

                payload = decode_jwt(credentials)

                # Validate token type
                if payload.get("type") != "access":
                    logger.warning("Auth Bearer token 'type' is not 'access'")
                    return _build_unauthorized(detail="Invalid token type")

                # Check username
                request.state.principal = payload.get("sub")
                if request.state.principal is None:
                    logger.warning("Auth Bearer token 'sub' is missing")
                    return _build_unauthorized(detail="Could not validate credentials")
        except HTTPException as e:
            logger.exception("Auth middleware HTTPException")
            body = {"detail": str(e.detail)}
            # Include WWW-Authenticate header if present
            headers = dict(e.headers) if e.headers else {}
            return JSONResponse(status_code=e.status_code, content=body, headers=headers)
        except Exception:
            logger.exception("Unhandled auth middleware error")
            return JSONResponse(status_code=500, content={"detail": "Internal authentication error"})

        return await call_next(request)
