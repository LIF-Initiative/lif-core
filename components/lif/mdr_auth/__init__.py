"""
Authentication module for LIF Metadata Repository
"""

from .core import JWT_CONFIG, TenantMiddleware, add_mdr_auth
from .workspace_cookie import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE_SECONDS,
    WorkspaceCookie,
    decode_workspace_cookie,
    encode_workspace_cookie,
)

__all__ = [
    "COOKIE_NAME",
    "DEFAULT_MAX_AGE_SECONDS",
    "JWT_CONFIG",
    "TenantMiddleware",
    "WorkspaceCookie",
    "add_mdr_auth",
    "decode_workspace_cookie",
    "encode_workspace_cookie",
]
