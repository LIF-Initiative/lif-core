"""
Core authentication module with JWT token handling, API key support, and Cognito JWT validation
"""

import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from lif.auth_utils.hs256 import decode_hs256, encode_hs256
from lif.cognito_auth import CognitoAuthConfig, decode_cognito_jwt
from lif.cognito_auth.core import _require_crypto
from lif.mdr_auth.workspace_cookie import COOKIE_NAME, decode_workspace_cookie
from lif.mdr_services.workspace_service import find_workspace
from lif.mdr_utils.collection_utils import convert_csv_to_set
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.logger_config import get_logger
from lif.tenant_routing import resolve_tenant_schema, sanitize_group_name
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger(__name__)

settings = get_settings()

# JWT configuration
SECRET_KEY = settings.mdr__auth__jwt_secret_key

API_KEY_HEADER_NAME = "X-API-Key"
# Recommended to use hard-to-guess names for the API keys.
API_KEYS = {
    settings.mdr__auth__service_api_key__graphql: "graphql-service",
    settings.mdr__auth__service_api_key__semantic_search: "semantic-search-service",
    settings.mdr__auth__service_api_key__translator: "translator-service",
    settings.mdr__auth__service_api_key__post_confirm: "post-confirm-service",
    settings.mdr__auth__service_api_key__learner_data_export: "learner-data-export-service",
}

# Cognito configuration — validation itself is delegated to the cognito_auth brick.
COGNITO_CONFIG = CognitoAuthConfig(
    user_pool_id=settings.mdr__auth__cognito_user_pool_id,
    region=settings.mdr__auth__cognito_region,
    client_id=settings.mdr__auth__cognito_spa_client_id,
)
COGNITO_ENABLED = COGNITO_CONFIG.is_enabled

# Tenant routing (issue #883) — read at request time via _tenant_routing_config
# so tests can monkeypatch the settings object without re-importing this module.
TENANT_ROUTING_ENABLED = settings.mdr__tenant_routing__enabled
TENANT_SERVICE_SCHEMA = settings.mdr__tenant_routing__service_schema


def _validate_cognito_config(config: CognitoAuthConfig) -> None:
    """Fail loudly at startup if Cognito is enabled without an SPA client id.

    cognito_auth skips the client check when ``client_id`` is empty, which would
    accept tokens minted for *any* app client in the pool. MDR must only accept
    its own SPA's tokens, so a pool without a client id is a misconfiguration.
    """
    if not config.is_enabled:
        return
    if not config.client_id:
        raise RuntimeError(
            "MDR__AUTH__COGNITO_USER_POOL_ID is set but MDR__AUTH__COGNITO_SPA_CLIENT_ID is empty. "
            "Set the SPA client id, or unset the user pool id to disable Cognito auth."
        )
    _require_crypto()


_validate_cognito_config(COGNITO_CONFIG)


METHODS_TO_REQUIRE_AUTH = convert_csv_to_set(settings.mdr__auth__methods_to_require_auth)

PUBLIC_ALLOWLIST_EXACT: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_exact)

PUBLIC_ALLOWLIST_STARTS_WITH: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_starts_with)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    expires_delta = expires_delta or timedelta(minutes=settings.mdr__auth__access_token_expire_minutes)
    return encode_hs256({**data, "type": "access"}, SECRET_KEY, expires_delta)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token"""
    return encode_hs256(
        {**data, "type": "refresh", "jti": str(uuid.uuid4())},  # jti: JWT ID for token tracking
        SECRET_KEY,
        timedelta(days=settings.mdr__auth__refresh_token_expire_days),
    )


def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token"""
    return decode_hs256(token, SECRET_KEY)


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
        request.state.cognito_groups = []
        request.state.cognito_sub = None
        request.state.tenant_schema = None

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
                # Fall back to Bearer token authentication
                credentials = _extract_bearer_token(request)
                if not credentials:
                    logger.warning("Auth blocked due to no credentials provided")
                    return _build_unauthorized(detail="Authentication required: Provide either Bearer token or API key")

                # Determine token type by inspecting the JWT header
                try:
                    header = jwt.get_unverified_header(credentials)
                except jwt.DecodeError:
                    return _build_unauthorized(detail="Could not validate credentials")

                if COGNITO_ENABLED and header.get("kid"):
                    # RS256 token with key ID — try Cognito validation
                    try:
                        payload = decode_cognito_jwt(credentials, COGNITO_CONFIG)
                    except jwt.ExpiredSignatureError:
                        logger.warning("Cognito token has expired")
                        return _build_unauthorized(detail="Token has expired")
                    except (jwt.InvalidTokenError, Exception) as e:
                        logger.warning("Cognito token validation failed: %s", e)
                        return _build_unauthorized(detail="Could not validate credentials")

                    # Extract principal from Cognito claims. We surface the
                    # raw sub separately so endpoints that need a stable
                    # identity (e.g. Cognito Admin API calls) don't have to
                    # guess whether principal is an email or a sub.
                    request.state.principal = payload.get("email") or payload.get("sub")
                    request.state.cognito_groups = payload.get("cognito:groups", [])
                    request.state.cognito_sub = payload.get("sub")
                else:
                    # Legacy HS256 token (no kid) — existing local JWT validation
                    payload = decode_jwt(credentials)

                    if payload.get("type") != "access":
                        logger.warning("Auth Bearer token 'type' is not 'access'")
                        return _build_unauthorized(detail="Invalid token type")

                    request.state.principal = payload.get("sub")

                if request.state.principal is None:
                    logger.warning("Auth token 'sub'/'email' is missing")
                    return _build_unauthorized(detail="Could not validate credentials")

            # Default tenant from JWT groups (or service-schema fallback for
            # API-key callers and group-less Cognito users).
            is_service_principal = isinstance(request.state.principal, str) and request.state.principal.startswith(
                "service:"
            )
            service_schema_override = None
            if is_service_principal:
                raw_override = request.headers.get("X-API-Tenant-Schema")
                if raw_override is not None:
                    if sanitize_group_name(raw_override) != raw_override:
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={"detail": "Invalid X-API-Tenant-Schema value"},
                        )
                    service_schema_override = raw_override
            request.state.tenant_schema = resolve_tenant_schema(
                enabled=TENANT_ROUTING_ENABLED,
                is_service_principal=is_service_principal,
                cognito_groups=getattr(request.state, "cognito_groups", None),
                service_schema=TENANT_SERVICE_SCHEMA,
                service_schema_override=service_schema_override,
            )

            # If the user picked a specific workspace via POST /tenants/select,
            # honor it — but only if the cookie's group is actually one of
            # theirs. The Cognito JWT remains the ground truth for membership;
            # a stale or stolen cookie can't grant access to a group the user
            # no longer belongs to.
            cognito_groups = getattr(request.state, "cognito_groups", None)

            # Early exit for callers who can never match a workspace cookie:
            # service principals (API-key auth) and HS256 legacy users both
            # have empty cognito_groups, so find_workspace would always return
            # None below. Skip the cookie read, HMAC verification, and any
            # decode-failure logging entirely — keeps service-to-service
            # traffic free of log noise from a stray lif_workspace cookie a
            # browser might forward through a proxy.
            if TENANT_ROUTING_ENABLED and cognito_groups:
                cookie_value = request.cookies.get(COOKIE_NAME)
                if cookie_value:
                    cookie = decode_workspace_cookie(cookie_value, secret=SECRET_KEY)
                    if cookie is not None:
                        selected = find_workspace(cognito_groups, cookie.group)
                        if selected is not None:
                            request.state.tenant_schema = selected.tenant_schema
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
