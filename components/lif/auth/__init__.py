"""LIF auth brick (ADR 0007): one middleware, identity providers as strategies.

Re-exports only modules that don't import ``jwt``. Import ``lif.auth.jwt`` and
``lif.auth.cognito`` explicitly: they import ``jwt``, which GraphQL (it packages
this brick for API-key auth) does not ship. No module here reads a secret at
import; each service resolves its own (e.g. ``JwtConfig.from_environment``).
"""

from lif.auth.api_key import ApiKeyConfig, api_key_strategy
from lif.auth.config import require_env, resolve_secret
from lif.auth.middleware import AuthMiddleware
from lif.auth.principal import AuthError, Principal, Strategy
from lif.auth.request import (
    API_KEY_HEADER,
    DEFAULT_PUBLIC_PATH_PREFIXES,
    DEFAULT_PUBLIC_PATHS,
    extract_bearer_token,
    is_public_path,
)

__all__ = [
    "API_KEY_HEADER",
    "DEFAULT_PUBLIC_PATH_PREFIXES",
    "DEFAULT_PUBLIC_PATHS",
    "ApiKeyConfig",
    "AuthError",
    "AuthMiddleware",
    "Principal",
    "Strategy",
    "api_key_strategy",
    "extract_bearer_token",
    "is_public_path",
    "require_env",
    "resolve_secret",
]
