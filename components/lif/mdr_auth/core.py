"""
MDR's inbound auth, composed from lif.auth (ADR 0007): service API key, Cognito and
HS256 strategies in lif.auth's AuthMiddleware, then MDR's tenant step.
"""

from datetime import timedelta
from typing import Dict, Optional

import jwt
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from lif.auth import ApiKeyConfig, AuthError, AuthMiddleware, Principal, api_key_strategy
from lif.auth.config import resolve_secret
from lif.auth.cognito import CognitoAuthConfig, decode_cognito_jwt, require_crypto
from lif.auth.jwt import JwtConfig, jwt_strategy
from lif.auth.request import API_KEY_HEADER, extract_bearer_token
from lif.mdr_auth.workspace_cookie import COOKIE_NAME, decode_workspace_cookie
from lif.mdr_services.workspace_service import find_workspace
from lif.mdr_utils.collection_utils import convert_csv_to_set
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.logger_config import get_logger
from lif.tenant_routing import resolve_tenant_schema, sanitize_group_name
from starlette.middleware.base import BaseHTTPMiddleware

logger = get_logger(__name__)

settings = get_settings()

# HS256 configuration. The secret also signs the workspace cookie and invite tokens.
JWT_CONFIG = JwtConfig(
    secret=resolve_secret(settings.mdr__auth__jwt_secret_key, "MDR__AUTH__JWT_SECRET_KEY"),
    access_token_expires=timedelta(minutes=settings.mdr__auth__access_token_expire_minutes),
    refresh_token_expires=timedelta(days=settings.mdr__auth__refresh_token_expire_days),
)
SECRET_KEY = JWT_CONFIG.secret


def _build_api_keys(configured: Dict[str, tuple[Optional[str], str]]) -> Dict[str, str]:
    """Map each configured service API key to its service name, skipping unset ones.

    There are no default keys: an unset key is simply not accepted, and the
    variable is named in a startup warning so the gap is visible (ADR 0007).
    """
    api_keys: Dict[str, str] = {}
    for env_name, (key, service_name) in configured.items():
        if key and key.strip():
            api_keys[key] = service_name
        else:
            logger.warning("%s is not set; API-key requests from %s will be rejected", env_name, service_name)
    return api_keys


# Recommended to use hard-to-guess names for the API keys.
API_KEYS = _build_api_keys(
    {
        "MDR__AUTH__SERVICE_API_KEY__GRAPHQL": (settings.mdr__auth__service_api_key__graphql, "graphql-service"),
        "MDR__AUTH__SERVICE_API_KEY__SEMANTIC_SEARCH": (
            settings.mdr__auth__service_api_key__semantic_search,
            "semantic-search-service",
        ),
        "MDR__AUTH__SERVICE_API_KEY__TRANSLATOR": (
            settings.mdr__auth__service_api_key__translator,
            "translator-service",
        ),
        "MDR__AUTH__SERVICE_API_KEY__POST_CONFIRM": (
            settings.mdr__auth__service_api_key__post_confirm,
            "post-confirm-service",
        ),
        "MDR__AUTH__SERVICE_API_KEY__LEARNER_DATA_EXPORT": (
            settings.mdr__auth__service_api_key__learner_data_export,
            "learner-data-export-service",
        ),
    }
)
# Service callers authenticate as "service:<name>"; endpoints and the tenant step key on that prefix.
API_KEY_CONFIG = ApiKeyConfig(
    api_keys={key: f"service:{name}" for key, name in API_KEYS.items()}, header=API_KEY_HEADER
)

# Cognito configuration — validation itself is delegated to lif.auth.cognito.
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

    ``lif.auth.cognito`` skips the client check when ``client_id`` is empty, which would
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
    require_crypto()


_validate_cognito_config(COGNITO_CONFIG)


METHODS_TO_REQUIRE_AUTH = convert_csv_to_set(settings.mdr__auth__methods_to_require_auth)

PUBLIC_ALLOWLIST_EXACT: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_exact)

PUBLIC_ALLOWLIST_STARTS_WITH: set[str] = convert_csv_to_set(settings.mdr__auth__public_allowlist_starts_with)


def _cognito_strategy(request: Request) -> Optional[Principal]:
    """Authenticate a Cognito RS256 bearer token (one whose header has a ``kid``).

    MDR's adapter over ``lif.auth.cognito``: the principal is the email (falling
    back to sub), and an invalid Cognito token is rejected with a specific message
    rather than handed to the HS256 strategy. Reads ``COGNITO_ENABLED`` and
    ``COGNITO_CONFIG`` per request so tests can patch them.
    """
    if not COGNITO_ENABLED:
        return None
    token = extract_bearer_token(request)
    if not token:
        return None
    try:
        if not jwt.get_unverified_header(token).get("kid"):
            return None
    except jwt.DecodeError:
        return None
    try:
        payload = decode_cognito_jwt(token, COGNITO_CONFIG)
    except jwt.ExpiredSignatureError as error:
        logger.warning("Cognito token has expired")
        raise AuthError("Token has expired") from error
    except Exception as error:
        logger.warning("Cognito token validation failed: %s", error)
        raise AuthError("Could not validate credentials") from error
    principal = payload.get("email") or payload.get("sub")
    if not principal:
        logger.warning("Auth token 'sub'/'email' is missing")
        raise AuthError("Could not validate credentials")
    return Principal(id=principal, method="cognito", claims=payload)


class TenantMiddleware(BaseHTTPMiddleware):
    """MDR's step after authentication: Cognito fields, tenant schema and workspace cookie.

    Runs inside lif.auth's ``AuthMiddleware`` (see ``add_mdr_auth``), so a principal
    is set only for authenticated requests. Every request gets the ``request.state``
    defaults MDR's endpoints read.
    """

    async def dispatch(self, request: Request, call_next):
        if not hasattr(request.state, "principal"):
            request.state.principal = None
        claims = getattr(request.state, "claims", None) or {}
        is_cognito = getattr(request.state, "auth_method", None) == "cognito"
        request.state.cognito_groups = claims.get("cognito:groups", []) if is_cognito else []
        request.state.cognito_sub = claims.get("sub") if is_cognito else None
        request.state.tenant_schema = None

        if request.state.principal is None:
            return await call_next(request)

        try:
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
                cognito_groups=request.state.cognito_groups,
                service_schema=TENANT_SERVICE_SCHEMA,
                service_schema_override=service_schema_override,
            )

            # If the user picked a specific workspace via POST /tenants/select,
            # honor it — but only if the cookie's group is actually one of
            # theirs. The Cognito JWT remains the ground truth for membership;
            # a stale or stolen cookie can't grant access to a group the user
            # no longer belongs to.
            cognito_groups = request.state.cognito_groups

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


def add_mdr_auth(app: FastAPI) -> None:
    """Wire MDR's inbound auth: lif.auth's ``AuthMiddleware`` with MDR's strategies, then the tenant step.

    Starlette runs the last-added middleware first, so ``TenantMiddleware`` is added
    before ``AuthMiddleware`` to run after it.
    """
    app.add_middleware(TenantMiddleware)
    app.add_middleware(
        AuthMiddleware,
        strategies=[
            api_key_strategy(API_KEY_CONFIG),
            _cognito_strategy,
            jwt_strategy(JWT_CONFIG, expected_type="access"),
        ],
        public_paths=PUBLIC_ALLOWLIST_EXACT,
        public_prefixes=PUBLIC_ALLOWLIST_STARTS_WITH,
        methods=METHODS_TO_REQUIRE_AUTH,
        challenge=f"Bearer, {API_KEY_HEADER}",
    )
