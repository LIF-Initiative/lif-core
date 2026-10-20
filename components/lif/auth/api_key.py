"""API-key identity provider: config plus a strategy for ``lif.auth.middleware.AuthMiddleware`` (ADR 0007).

A single shared-secret token (e.g. the Example Data Source's ``x-key``) is a
one-key config with a custom header.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from starlette.requests import Request

from lif.auth.principal import AuthError, Principal, Strategy
from lif.auth.request import API_KEY_HEADER, DEFAULT_PUBLIC_PATH_PREFIXES, DEFAULT_PUBLIC_PATHS


@dataclass
class ApiKeyConfig:
    """Configuration for API key authentication."""

    # Map of API key -> client name (for logging/auditing)
    api_keys: Dict[str, str] = field(default_factory=dict)

    # Paths that don't require authentication (exact match)
    public_paths: Set[str] = field(default_factory=lambda: set(DEFAULT_PUBLIC_PATHS))

    # Path prefixes that don't require authentication
    public_path_prefixes: Set[str] = field(default_factory=lambda: set(DEFAULT_PUBLIC_PATH_PREFIXES))

    # HTTP methods that require authentication (empty set = no auth required)
    methods_requiring_auth: Set[str] = field(default_factory=lambda: {"GET", "POST", "PUT", "DELETE", "PATCH"})

    # Request header carrying the key
    header: str = API_KEY_HEADER

    @classmethod
    def from_environment(cls, prefix: str = "API_AUTH", header: str = API_KEY_HEADER) -> "ApiKeyConfig":
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
            header: Request header carrying the key (default: "X-API-Key")

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

        public_paths = cls._parse_csv_set(os.environ.get(f"{prefix}__PUBLIC_PATHS", ",".join(DEFAULT_PUBLIC_PATHS)))
        public_prefixes = cls._parse_csv_set(
            os.environ.get(f"{prefix}__PUBLIC_PATH_PREFIXES", ",".join(DEFAULT_PUBLIC_PATH_PREFIXES))
        )

        return cls(api_keys=api_keys, public_paths=public_paths, public_path_prefixes=public_prefixes, header=header)

    @staticmethod
    def _parse_csv_set(value: str) -> Set[str]:
        """Parse comma-separated string into a set, trimming whitespace."""
        return {item.strip() for item in value.split(",") if item.strip()}

    @property
    def is_enabled(self) -> bool:
        """Check if authentication is enabled (has at least one API key)."""
        return bool(self.api_keys)


def api_key_strategy(config: ApiKeyConfig) -> Strategy:
    """Authenticate by the key in ``config.header``; the principal id is the key's client name.

    No header → ``None`` (not this strategy's credential). An unknown key → ``AuthError``.
    """

    def authenticate(request: Request) -> Optional[Principal]:
        key = request.headers.get(config.header)
        if not key:
            return None
        client_name = config.api_keys.get(key)
        if client_name is None:
            raise AuthError("Invalid API key.", challenge=config.header)
        return Principal(id=client_name, method="api_key")

    return authenticate
