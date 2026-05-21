"""Unit tests for the workspace selection cookie helpers."""

import time

from lif.mdr_auth.workspace_cookie import (
    COOKIE_NAME,
    DEFAULT_MAX_AGE_SECONDS,
    decode_workspace_cookie,
    encode_workspace_cookie,
)

SECRET = "test-secret"


class TestRoundTrip:
    def test_encode_then_decode_returns_group(self):
        cookie = encode_workspace_cookie("lif-team", secret=SECRET)
        decoded = decode_workspace_cookie(cookie, secret=SECRET)
        assert decoded is not None
        assert decoded.group == "lif-team"

    def test_handles_groups_with_unusual_characters(self):
        """Cognito group names allow Unicode, spaces, punctuation. The
        base64url payload encoding has to round-trip them all."""
        # cspell:disable-next-line
        for group in ["Acme University", "eval-jsmith", "team@example.com", "Ácmé/Univ"]:
            cookie = encode_workspace_cookie(group, secret=SECRET)
            decoded = decode_workspace_cookie(cookie, secret=SECRET)
            assert decoded is not None and decoded.group == group, group

    def test_default_expiry_is_about_30_days(self):
        before = int(time.time())
        cookie = encode_workspace_cookie("lif-team", secret=SECRET)
        decoded = decode_workspace_cookie(cookie, secret=SECRET)
        assert decoded is not None
        # ±2s tolerance for clock drift between encode/decode and `time.time()` calls
        assert abs(decoded.expires_at - (before + DEFAULT_MAX_AGE_SECONDS)) <= 2


class TestDecodeRejection:
    def test_none_value_returns_none(self):
        assert decode_workspace_cookie(None, secret=SECRET) is None

    def test_empty_value_returns_none(self):
        assert decode_workspace_cookie("", secret=SECRET) is None

    def test_malformed_value_returns_none(self):
        for bad in ["no-dots", "only.two", "way.too.many.dots.here"]:
            assert decode_workspace_cookie(bad, secret=SECRET) is None, bad

    def test_tampered_group_invalidates_signature(self):
        cookie = encode_workspace_cookie("lif-team", secret=SECRET)
        encoded_group, exp, sig = cookie.split(".")
        # Re-encode a different group with the original (now wrong) signature
        from base64 import urlsafe_b64encode

        forged_group = urlsafe_b64encode(b"acme-univ").decode().rstrip("=")
        forged = f"{forged_group}.{exp}.{sig}"
        assert decode_workspace_cookie(forged, secret=SECRET) is None

    def test_tampered_expiry_invalidates_signature(self):
        cookie = encode_workspace_cookie("lif-team", secret=SECRET)
        encoded_group, exp, sig = cookie.split(".")
        forged = f"{encoded_group}.{int(exp) + 999999999}.{sig}"
        assert decode_workspace_cookie(forged, secret=SECRET) is None

    def test_wrong_secret_invalidates_signature(self):
        cookie = encode_workspace_cookie("lif-team", secret=SECRET)
        assert decode_workspace_cookie(cookie, secret="other-secret") is None

    def test_expired_cookie_returns_none(self):
        """Use the now-injection seam to simulate the cookie aging out."""
        cookie = encode_workspace_cookie("lif-team", secret=SECRET, max_age_seconds=10)
        decoded = decode_workspace_cookie(cookie, secret=SECRET, now=int(time.time()) + 100)
        assert decoded is None


class TestCookieName:
    def test_name_is_stable(self):
        # Frontend reads the cookie set by /tenants/select; if this name
        # changes the frontend has to change too. Lock it down so a typo
        # doesn't silently break the round-trip.
        assert COOKIE_NAME == "lif_workspace"
