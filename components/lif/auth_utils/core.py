"""Request-level auth helpers shared by api_key_auth, cognito_auth, mdr_auth, and bases.

Pure functions and constants only: no environment reads and no ``jwt`` import,
so any service can package this module without extra dependencies.
"""

from collections.abc import Collection, Iterable
from typing import Optional

from starlette.requests import Request

API_KEY_HEADER = "X-API-Key"

# Default unauthenticated paths for services that don't configure their own allowlist.
DEFAULT_PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/health-check"})
DEFAULT_PUBLIC_PATH_PREFIXES: frozenset[str] = frozenset({"/docs", "/openapi.json"})


def is_public_path(path: str, exact: Collection[str], prefixes: Iterable[str]) -> bool:
    """True when ``path`` is in ``exact`` or starts with any of ``prefixes``."""
    return path in exact or any(path.startswith(prefix) for prefix in prefixes)


def extract_bearer_token(request: Request) -> Optional[str]:
    """Return the token from ``Authorization: Bearer <token>``, else ``None``.

    The scheme is matched case-insensitively (RFC 7235); the header must be
    exactly two whitespace-separated parts.
    """
    parts = request.headers.get("Authorization", "").split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
