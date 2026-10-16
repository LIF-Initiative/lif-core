import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from lif.auth import ApiKeyConfig, AuthMiddleware, Principal, api_key_strategy
from lif.auth.cognito import CognitoAuthConfig, cognito_strategy
from lif.learner_data_export_api import learner_data_export_endpoints
from lif.logging import get_logger
from lif.mdr_utils.config import get_settings

logger = get_logger(__name__)
settings = get_settings()
app = FastAPI(title="LIF Learner Data Export API", description="API for the LIF Learner Data Export", version="1.0.0")


# --- Inbound authentication -------------------------------------------------
# LDE is bare on API-key auth by default. Per ADR 0004, richer auth is a
# *decoration* composed here at the base, not baked into the LDE component, and per
# ADR 0007 both modes compose lif.auth's one middleware with provider strategies.
#
# #1034 target: accept a signed developer key OR a Cognito JWT. Opt in with
# LDE_AUTH__MODE=composite; the default ("api_key") uses LDE_AUTH__API_KEYS.


def _developer_key_strategy(request: Request) -> Optional[Principal]:
    """Validate a signed developer key (from the #1033/#1038 keys store).

    TODO(#1034): implement HMAC signed-token offline verification (ADR 0002) —
    parse the `X-API-Key` / bearer developer key, verify signature + expiry +
    revocation, return a Principal for {owner, workspace, key_id}. Stub returns
    None until the signed-token format lands with #1038, so composite mode
    currently authenticates via Cognito only.
    """
    return None


def add_inbound_auth(app: FastAPI, mode: str, api_key_config: ApiKeyConfig, cognito_config: CognitoAuthConfig) -> None:
    """Add lif.auth's middleware for ``mode``; both modes honour LDE_AUTH__PUBLIC_PATHS*."""
    if mode == "composite":
        app.add_middleware(
            AuthMiddleware,
            strategies=[_developer_key_strategy, cognito_strategy(cognito_config)],
            public_paths=api_key_config.public_paths,
            public_prefixes=api_key_config.public_path_prefixes,
        )
        logger.info(
            "LDE composite auth enabled (developer-key [TODO #1034] or Cognito JWT; cognito pool configured=%s)",
            cognito_config.is_enabled,
        )
        return

    # Default / bare: API-key auth for downstream applications. Keys are
    # provisioned out-of-band into LDE_AUTH__API_KEYS (SSM-backed) as "key:label"
    # pairs; auth self-disables when no keys are configured (matching GraphQL).
    # This is the inbound credential only — LDE's outbound call to MDR uses the
    # separate LIF_MDR_API_AUTH_TOKEN.
    if not api_key_config.is_enabled:
        logger.warning(
            "API key authentication NOT configured (LDE_AUTH__API_KEYS unset) — endpoints are unauthenticated"
        )
        return
    app.add_middleware(
        AuthMiddleware,
        strategies=[api_key_strategy(api_key_config)],
        public_paths=api_key_config.public_paths,
        public_prefixes=api_key_config.public_path_prefixes,
        methods=api_key_config.methods_requiring_auth,
        challenge=api_key_config.header,
    )
    logger.info("API key authentication enabled for Learner Data Export (%d keys)", len(api_key_config.api_keys))


_auth_mode = os.environ.get("LDE_AUTH__MODE", "api_key")
add_inbound_auth(
    app,
    _auth_mode,
    ApiKeyConfig.from_environment(prefix="LDE_AUTH"),
    # Read Cognito config (and check for pyjwt[crypto]) only when composite mode uses it.
    CognitoAuthConfig.from_environment(prefix="LDE_AUTH") if _auth_mode == "composite" else CognitoAuthConfig(),
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
