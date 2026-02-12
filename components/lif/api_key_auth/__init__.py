"""Simple API Key authentication middleware for FastAPI services."""

from lif.api_key_auth.core import ApiKeyAuthMiddleware, ApiKeyConfig

__all__ = ["ApiKeyAuthMiddleware", "ApiKeyConfig"]
