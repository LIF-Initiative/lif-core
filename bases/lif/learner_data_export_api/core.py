import os
from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from lif.api_key_auth import ApiKeyAuthMiddleware, ApiKeyConfig
from lif.cognito_auth import CognitoAuthConfig, authenticate_request
from lif.learner_data_export_api import learner_data_export_endpoints
from lif.logging import get_logger
from lif.mdr_utils.config import get_settings

logger = get_logger(__name__)
settings = get_settings()
app = FastAPI(title="LIF Learner Data Export API", description="API for the LIF Learner Data Export", version="1.0.0")


# --- Inbound authentication -------------------------------------------------
# LDE is bare on `api_key_auth` by default. Per ADR 0004, richer auth is a
# *decoration* composed here at the base, not baked into the LDE component.
#
# #1034 target: accept a signed developer key OR a Cognito JWT. Opt in with
# LDE_AUTH__MODE=composite; the default ("api_key") keeps current behavior, so
# this scaffold changes nothing at runtime until explicitly enabled.
AuthStrategy = Callable[[Request], Optional[dict[str, Any]]]


def _developer_key_strategy(request: Request) -> Optional[dict[str, Any]]:
    """Validate a signed developer key (from the #1033/#1038 keys store).

    TODO(#1034): implement HMAC signed-token offline verification (ADR 0002) —
    parse the `X-API-Key` / bearer developer key, verify signature + expiry +
    revocation, return {owner, workspace, key_id}. Stub returns None until the
    signed-token format lands with #1038, so composite mode currently
    authenticates via Cognito only.
    """
    return None


class CompositeAuthMiddleware(BaseHTTPMiddleware):
    """Try each auth strategy in order; first to return a principal wins, else 401.

    Composition glue (a base concern), not a reusable component — it wires
    together single-purpose auth bricks (`cognito_auth`, and later the developer
    signed-key validator).
    """

    def __init__(
        self, app, strategies: list[tuple[str, AuthStrategy]], public_paths=None, public_prefixes=None
    ) -> None:
        super().__init__(app)
        self.strategies = strategies
        self.public_paths = public_paths or {"/health", "/health-check"}
        self.public_prefixes = public_prefixes or {"/docs", "/openapi.json"}

    def _is_public(self, path: str) -> bool:
        return path in self.public_paths or any(path.startswith(p) for p in self.public_prefixes)

    async def dispatch(self, request: Request, call_next):
        if self._is_public(request.url.path):
            return await call_next(request)
        for name, strategy in self.strategies:
            principal = strategy(request)
            if principal is not None:
                request.state.auth_method = name
                request.state.principal = principal
                return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid credentials"})


_auth_mode = os.environ.get("LDE_AUTH__MODE", "api_key")
if _auth_mode == "composite":
    # #1034 scaffold: signed developer key OR Cognito JWT, composed from bricks.
    cognito_config = CognitoAuthConfig.from_environment(prefix="LDE_AUTH")
    strategies: list[tuple[str, AuthStrategy]] = [
        ("developer_key", _developer_key_strategy),
        ("cognito", lambda r: authenticate_request(r, cognito_config)),
    ]
    app.add_middleware(CompositeAuthMiddleware, strategies=strategies)
    logger.info(
        "LDE composite auth enabled (developer-key [TODO #1034] or Cognito JWT; cognito pool configured=%s)",
        cognito_config.is_enabled,
    )
else:
    # Default / bare: API-key auth for downstream applications. Keys are
    # provisioned out-of-band into LDE_AUTH__API_KEYS (SSM-backed) as "key:label"
    # pairs; auth self-disables when no keys are configured (matching GraphQL).
    # This is the inbound credential only — LDE's outbound call to MDR uses the
    # separate LIF_MDR_API_AUTH_TOKEN.
    auth_config = ApiKeyConfig.from_environment(prefix="LDE_AUTH")
    if auth_config.is_enabled:
        app.add_middleware(ApiKeyAuthMiddleware, config=auth_config)
        logger.info("API key authentication enabled for Learner Data Export (%d keys)", len(auth_config.api_keys))
    else:
        logger.warning(
            "API key authentication NOT configured (LDE_AUTH__API_KEYS unset) — endpoints are unauthenticated"
        )
# Configure CORS middleware
cors_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
cors_methods = [method.strip() for method in settings.cors_allow_methods.split(",") if method.strip()]
cors_headers = (
    [header.strip() for header in settings.cors_allow_headers.split(",") if header.strip()]
    if settings.cors_allow_headers != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)


# --- API Endpoints ---


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify the API is running
    """
    return {"status": "ok"}


app.include_router(learner_data_export_endpoints.router, prefix="")
