"""HMAC-signed invite tokens for tenant group sharing (issue #884 Phase 3 PR 2).

A schema owner generates an invite token via POST /tenants/invite; the
recipient accepts it via POST /tenants/invite/accept, which calls
Cognito's AdminAddUserToGroup to add them to the group.

Security model
--------------
The token is self-contained — signature + expiry are the only validation.
There is no server-side store of issued/spent tokens, so a token is
effectively reusable until expiry. That's acceptable for v1: tokens
expire after 7 days by default, and the recipient must already have a
Cognito account (which Cognito itself rate-limits). Single-use
enforcement would require a DB table; deferred until we see actual reuse
abuse.

Format
------
``{base64url(json_payload)}.{hmac_sha256_hex}``

Payload JSON: ``{"g": "<group>", "i": "<inviter_sub>", "e": <exp_unix>}``.
Short keys keep the token compact for URL-friendliness (typical length
~140-180 chars).
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 days
_SEPARATOR = "."


@dataclass(frozen=True)
class InviteToken:
    """Decoded invite-token payload."""

    group: str
    inviter_sub: str
    expires_at: int


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def encode_invite_token(
    group: str, inviter_sub: str, secret: str, *, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
) -> str:
    """Build a signed invite token for a group + inviter pair."""
    expires_at = int(time.time()) + max_age_seconds
    payload_json = json.dumps({"g": group, "i": inviter_sub, "e": expires_at}, separators=(",", ":"), sort_keys=True)
    encoded = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(encoded, secret)
    return f"{encoded}{_SEPARATOR}{sig}"


def decode_invite_token(value: str | None, secret: str, *, now: int | None = None) -> InviteToken | None:
    """Verify signature and expiry; return the decoded token or None.

    Returns None on any failure mode (malformed value, bad signature,
    expired token, decoding error, missing required fields). Endpoint
    callers should translate None into an appropriate 4xx — typically 400
    for malformed, 410 Gone for expired. This helper deliberately does
    not distinguish: a forged token that *happens* to have a valid-looking
    expiry shouldn't leak information about whether the signature was
    actually checked first.
    """
    if not value:
        return None
    parts = value.split(_SEPARATOR)
    if len(parts) != 2:
        return None
    encoded, sig = parts
    expected_sig = _sign(encoded, secret)
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        group = payload["g"]
        inviter_sub = payload["i"]
        expires_at = int(payload["e"])
    except (ValueError, KeyError, UnicodeDecodeError):
        return None
    if not isinstance(group, str) or not isinstance(inviter_sub, str):
        return None
    current = now if now is not None else int(time.time())
    if expires_at <= current:
        return None
    return InviteToken(group=group, inviter_sub=inviter_sub, expires_at=expires_at)
