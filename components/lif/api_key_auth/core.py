"""
Simple API Key authentication middleware for FastAPI services.

This component provides a lightweight API key authentication mechanism suitable
for protecting public-facing APIs. It validates API keys passed in the X-API-Key
header and allows configurable public paths that bypass authentication.

Usage:
    from lif.api_key_auth import ApiKeyAuthMiddleware, ApiKeyConfig

    # Option 1: Load from environment variables
    config = ApiKeyConfig.from_environment(prefix="GRAPHQL_AUTH")

    # Option 2: Configure directly
    config = ApiKeyConfig(
        api_keys={"secret-key-1": "client-name-1"},
        public_paths={"/health"},
    )

    app.add_middleware(ApiKeyAuthMiddleware, config=config)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Set

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"


@dataclass
class ApiKeyConfig:
    """Configuration for API key authentication."""

    # Map of API key -> client name (for logging/auditing)
    api_keys: Dict[str, str] = field(default_factory=dict)

    # Paths that don't require authentication (exact match)
    public_paths: Set[str] = field(default_factory=lambda: {"/health", "/health-check"})

    # Path prefixes that don't require authentication
    public_path_prefixes: Set[str] = field(default_factory=lambda: {"/docs", "/openapi.json"})

    # HTTP methods that require authentication (empty set = no auth required)
    methods_requiring_auth: Set[str] = field(
        default_factory=lambda: {"GET", "POST", "PUT", "DELETE", "PATCH"}
    )

    @classmethod
    def from_environment(cls, prefix: str = "API_AUTH") -> "ApiKeyConfig":
        """
        Load config from environment variables.

        Environment variables:
            {PREFIX}__API_KEYS: Comma-separated "key:name" pairs
                Example: "abc123:alice,def456:bob"
            {PREFIX}__PUBLIC_PATHS: Comma-separated exact paths (optional)
                Example: "/health,/health-check"
            {PREFIX}__PUBLIC_PATH_PREFIXES: Comma-separated path prefixes (optional)
                Example: "/docs,/openapi.json"

        Args:
            prefix: Environment variable prefix (default: "API_AUTH")

        Returns:
            ApiKeyConfig instance populated from environment
        """
        api_keys = {}
        keys_str = os.environ.get(f"{prefix}__API_KEYS", "")
        for pair in keys_str.split(","):
            pair = pair.strip()
            if ":" in pair:
                key, name = pair.split(":", 1)
                key = key.strip()
                name = name.strip()
                if key and name:
                    api_keys[key] = name

        public_paths = cls._parse_csv_set(
            os.environ.get(f"{prefix}__PUBLIC_PATHS", "/health,/health-check")
        )
        public_prefixes = cls._parse_csv_set(
            os.environ.get(f"{prefix}__PUBLIC_PATH_PREFIXES", "/docs,/openapi.json")
        )

        return cls(
            api_keys=api_keys,
            public_paths=public_paths,
            public_path_prefixes=public_prefixes,
        )

    @staticmethod
    def _parse_csv_set(value: str) -> Set[str]:
        """Parse comma-separated string into a set, trimming whitespace."""
        return {item.strip() for item in value.split(",") if item.strip()}

    @property
    def is_enabled(self) -> bool:
        """Check if authentication is enabled (has at least one API key)."""
        return bool(self.api_keys)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates API keys in X-API-Key header.

    When authentication succeeds, the client name is stored in request.state.api_client
    for use by downstream handlers.
    """

    def __init__(self, app, config: ApiKeyConfig):
        super().__init__(app)
        self.config = config
        if config.is_enabled:
            logger.info(
                "API key auth enabled with %d keys, public paths: %s",
                len(config.api_keys),
                config.public_paths | config.public_path_prefixes,
            )
        else:
            logger.warning("API key auth middleware added but no API keys configured")

    async def dispatch(self, request: Request, call_next):
        # Skip auth for excluded methods
        if request.method not in self.config.methods_requiring_auth:
            return await call_next(request)

        # Skip auth for public paths (exact match)
        path = request.url.path
        if path in self.config.public_paths:
            return await call_next(request)

        # Skip auth for public path prefixes
        if any(path.startswith(prefix) for prefix in self.config.public_path_prefixes):
            return await call_next(request)

        # If no API keys configured, allow all requests (auth disabled)
        if not self.config.is_enabled:
            return await call_next(request)

        # Validate API key
        api_key = request.headers.get(API_KEY_HEADER)
        if not api_key:
            logger.warning("Request to %s rejected: missing API key", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key. Provide X-API-Key header."},
                headers={"WWW-Authenticate": "X-API-Key"},
            )

        client_name = self.config.api_keys.get(api_key)
        if not client_name:
            logger.warning("Request to %s rejected: invalid API key", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key."},
                headers={"WWW-Authenticate": "X-API-Key"},
            )

        # Store client info for downstream use (logging, auditing, etc.)
        request.state.api_client = client_name
        logger.debug("Request to %s authenticated for client: %s", path, client_name)

        return await call_next(request)
