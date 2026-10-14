"""Key generation in the developer_keys brick (#1033)."""

import hashlib

from lif.developer_keys.core import KEY_PREFIX, _generate_key


def test_generated_key_carries_32_bytes_of_entropy():
    raw, key_prefix, key_hash = _generate_key()

    # token_urlsafe(32) is 43 base64url characters. The plain SHA-256 at rest is only safe because
    # the key is high-entropy, so a shorter token would be a security regression, not a style change.
    assert raw.startswith(KEY_PREFIX)
    assert len(raw) == len(KEY_PREFIX) + 43
    assert key_prefix == raw[:12]
    assert key_hash == hashlib.sha256(raw.encode()).hexdigest()
