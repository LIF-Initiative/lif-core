"""Shared, environment-free helpers for the LIF auth bricks.

Only the jwt-free ``core`` module is re-exported here. HS256 helpers live in
``lif.auth_utils.hs256`` and must be imported explicitly: some services that
package this brick (e.g. GraphQL, via ``api_key_auth``) do not ship ``pyjwt``.
"""

from lif.auth_utils.core import (
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
    "extract_bearer_token",
    "is_public_path",
]
