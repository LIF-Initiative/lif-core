"""HMAC-signed workspace selection cookie (issue #884 Phase 3 PR 1).

Persists the user's selected workspace across requests so the auth
middleware can route to the chosen tenant schema instead of always
falling back to ``cognito_groups[0]``. The cookie value is opaque to
the browser and is validated server-side on every request.

Security model
--------------
The cookie carries a Cognito group name plus an expiry, signed with an
HMAC over the same secret used for HS256 JWTs (settings.mdr__auth__jwt_secret_key).
The middleware *additionally* re-checks that the group is in the user's
``cognito:groups`` claim before honoring the selection — so a stolen or
forged cookie naming a group the user doesn't belong to is silently
ignored, falling back to the default. The cookie alone never grants new
access; it only narrows membership the JWT already proves.

Why a forged cookie is treated differently from a forged JWT:
an attacker who can forge the JWT has already won and we have bigger
problems. The cookie, by contrast, is *just a workspace selection* — its
authority is bounded by the JWT's ``cognito:groups`` claim, which the
middleware re-verifies on every request. So the threat model for a bad
cookie is narrow: at worst the attacker selects one of the user's *own*
groups, which they could have selected anyway. We fall back rather than
hard-reject because the common cause of a bad cookie is innocuous —
secret rotation, an evicted group, or a stale 30-day cookie — and
locking those users out would create support tickets without preventing
any attack the JWT check doesn't already cover.

Format
------
``{base64url(group_name)}.{exp_unix}.{hmac_sha256_hex}``

- ``group_name`` is the raw Cognito group, base64url-encoded so unusual
  characters don't collide with the dot separator.
- ``exp_unix`` is an integer-seconds POSIX timestamp.
- The HMAC covers the literal ``{base64url}.{exp}`` payload (so any
  tampering with either field invalidates the signature).
"""

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from lif.mdr_utils.logger_config import get_logger

logger = get_logger(__name__)

COOKIE_NAME = "lif_workspace"
DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days
_SEPARATOR = "."


@dataclass(frozen=True)
class WorkspaceCookie:
    """Decoded workspace cookie payload."""

    group: str
    expires_at: int


def _b64url_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8")


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_workspace_cookie(group: str, secret: str, *, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> str:
    """Build the cookie value for a workspace selection."""
    expires_at = int(time.time()) + max_age_seconds
    payload = f"{_b64url_encode(group)}{_SEPARATOR}{expires_at}"
    sig = _sign(payload, secret)
    return f"{payload}{_SEPARATOR}{sig}"


def decode_workspace_cookie(value: str | None, secret: str, *, now: int | None = None) -> WorkspaceCookie | None:
    """Verify signature and expiry; return the decoded cookie or None.

    Returns None for any failure mode — malformed value, bad signature,
    expired cookie, decoding error. Callers should treat None as "no
    selection" and fall back to defaults rather than 401-ing the request:
    a stale cookie shouldn't lock anyone out.
    """
    if not value:
        return None
    parts = value.split(_SEPARATOR)
    if len(parts) != 3:
        # DEBUG, not WARNING: this branch runs on every request that carries a
        # malformed cookie until it expires (30 days). The middleware can't
        # currently clear the cookie from here, so a single bad cookie would
        # spam the logs at WARNING.
        logger.debug("Workspace cookie malformed: expected 3 dot-separated parts, got %d", len(parts))
        return None
    encoded_group, exp_str, sig = parts
    payload = f"{encoded_group}{_SEPARATOR}{exp_str}"
    expected_sig = _sign(payload, secret)
    if not hmac.compare_digest(sig, expected_sig):
        # DEBUG, not WARNING: the common cause is a rotated JWT secret or a
        # stale cookie predating a format change, both benign. Same per-request
        # log-spam concern as the malformed branch above. Don't log the
        # signature itself.
        logger.debug("Workspace cookie signature mismatch (tampering, rotated secret, or stale cookie)")
        return None
    try:
        expires_at = int(exp_str)
        group = _b64url_decode(encoded_group)
    except (ValueError, UnicodeDecodeError) as e:
        logger.debug("Workspace cookie payload decode failed: %s", e)
        return None
    current = now if now is not None else int(time.time())
    if expires_at <= current:
        logger.debug("Workspace cookie expired (exp=%d, now=%d)", expires_at, current)
        return None
    return WorkspaceCookie(group=group, expires_at=expires_at)
