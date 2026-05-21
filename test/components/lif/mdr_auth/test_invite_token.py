"""Unit tests for invite_token helpers."""

import time

from lif.mdr_auth.invite_token import DEFAULT_MAX_AGE_SECONDS, decode_invite_token, encode_invite_token

SECRET = "test-secret"


class TestRoundTrip:
    def test_encode_then_decode_returns_payload(self):
        token = encode_invite_token("lif-team", "cognito-sub-abc", secret=SECRET)
        decoded = decode_invite_token(token, secret=SECRET)
        assert decoded is not None
        assert decoded.group == "lif-team"
        assert decoded.inviter_sub == "cognito-sub-abc"

    def test_handles_groups_with_unicode_and_spaces(self):
        # cspell:disable-next-line
        for group in ["Acme University", "eval-jsmith", "team@example.com", "Ácmé/Univ"]:
            token = encode_invite_token(group, "sub-1", secret=SECRET)
            decoded = decode_invite_token(token, secret=SECRET)
            assert decoded is not None and decoded.group == group, group

    def test_default_expiry_is_about_7_days(self):
        before = int(time.time())
        token = encode_invite_token("lif-team", "sub-1", secret=SECRET)
        decoded = decode_invite_token(token, secret=SECRET)
        assert decoded is not None
        assert abs(decoded.expires_at - (before + DEFAULT_MAX_AGE_SECONDS)) <= 2


class TestDecodeRejection:
    def test_none_returns_none(self):
        assert decode_invite_token(None, secret=SECRET) is None

    def test_empty_returns_none(self):
        assert decode_invite_token("", secret=SECRET) is None

    def test_malformed_returns_none(self):
        for bad in ["no-separator", "too.many.dots", "x.y.z.w"]:
            assert decode_invite_token(bad, secret=SECRET) is None, bad

    def test_tampered_payload_invalidates_signature(self):
        token = encode_invite_token("lif-team", "sub-1", secret=SECRET)
        encoded, sig = token.split(".")
        # Re-encode a forged payload with the old (now wrong) signature
        from base64 import urlsafe_b64encode

        forged_payload = urlsafe_b64encode(b'{"g":"acme","i":"attacker","e":9999999999}').decode().rstrip("=")
        forged = f"{forged_payload}.{sig}"
        assert decode_invite_token(forged, secret=SECRET) is None

    def test_wrong_secret_invalidates_signature(self):
        token = encode_invite_token("lif-team", "sub-1", secret=SECRET)
        assert decode_invite_token(token, secret="other-secret") is None

    def test_expired_token_returns_none(self):
        token = encode_invite_token("lif-team", "sub-1", secret=SECRET, max_age_seconds=10)
        assert decode_invite_token(token, secret=SECRET, now=int(time.time()) + 100) is None

    def test_payload_missing_required_field_returns_none(self):
        """Signature valid but payload missing a required key — refuse rather than
        index-error in the endpoint."""
        from base64 import urlsafe_b64encode
        from lif.mdr_auth.invite_token import _sign

        bad_payload = urlsafe_b64encode(b'{"g":"lif-team"}').decode().rstrip("=")
        sig = _sign(bad_payload, SECRET)
        token = f"{bad_payload}.{sig}"
        assert decode_invite_token(token, secret=SECRET) is None

    def test_payload_with_non_string_group_returns_none(self):
        from base64 import urlsafe_b64encode
        from lif.mdr_auth.invite_token import _sign

        bad_payload = urlsafe_b64encode(b'{"g":123,"i":"sub","e":9999999999}').decode().rstrip("=")
        sig = _sign(bad_payload, SECRET)
        token = f"{bad_payload}.{sig}"
        assert decode_invite_token(token, secret=SECRET) is None

    def test_validly_signed_non_object_payload_returns_none(self):
        """A signed payload that is valid JSON but not an object (list, string,
        number) must return None — indexing a non-dict would otherwise raise
        TypeError and 500 the endpoint."""
        from base64 import urlsafe_b64encode
        from lif.mdr_auth.invite_token import _sign

        for raw in (b'[1,2,3]', b'"just a string"', b'42', b'null'):
            encoded = urlsafe_b64encode(raw).decode().rstrip("=")
            sig = _sign(encoded, SECRET)
            token = f"{encoded}.{sig}"
            assert decode_invite_token(token, secret=SECRET) is None, f"non-object payload {raw!r} should decode to None"


class TestExpiryRecovery:
    def test_now_zero_reveals_expired_token_would_have_been_valid(self):
        """The endpoint uses now=0 to distinguish 'expired' from 'forged'.
        A token that expired today should decode successfully with now=0."""
        token = encode_invite_token("lif-team", "sub-1", secret=SECRET, max_age_seconds=10)
        # Real-time decode rejects (expired)
        assert decode_invite_token(token, secret=SECRET, now=int(time.time()) + 100) is None
        # Backdated decode accepts
        assert decode_invite_token(token, secret=SECRET, now=0) is not None
