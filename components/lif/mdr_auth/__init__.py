"""
Authentication module for LIF Metadata Repository
"""

from .core import AuthMiddleware, create_access_token, create_refresh_token, decode_jwt
from .workspace_cookie import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE_SECONDS,
    WorkspaceCookie,
    decode_workspace_cookie,
    encode_workspace_cookie,
)

__all__ = [
    "AuthMiddleware",
    "COOKIE_NAME",
    "DEFAULT_MAX_AGE_SECONDS",
    "WorkspaceCookie",
    "create_access_token",
    "create_refresh_token",
    "decode_jwt",
    "decode_workspace_cookie",
    "encode_workspace_cookie",
]
