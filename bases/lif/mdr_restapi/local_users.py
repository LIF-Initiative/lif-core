"""Configured MDR logins for deployments without Cognito (#1316).

``MDR__AUTH__LOCAL_USERS`` holds comma-separated ``username=hash`` pairs. Generate
each hash with ``python3 scripts/hash-mdr-password.py``. When the variable is set,
these users replace the built-in demo personas, and ``LIF_DEMO_USER_PASSWORD`` is
no longer needed.

Hashes are scrypt, stored as ``scrypt:<n>:<r>:<p>:<salt>:<key>``, with salt and key in
URL-safe base64 without padding. That alphabet has no ``$``, ``,`` or ``=``, so a value pastes into
a ``.env`` file without quoting or Compose interpolation surprises.

Standard library only: ``scripts/hash-mdr-password.py`` loads this file by path so
it runs without the MDR's dependencies or configuration.
"""

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1  # 16 MiB per hash, inside OpenSSL's default 32 MiB memory limit
_KEY_LEN = 32


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_LEN)
    return f"scrypt:{_N}:{_R}:{_P}:{_b64encode(salt)}:{_b64encode(key)}"


def verify_password(password: str, stored: str) -> bool:
    _, n, r, p, salt, key = stored.split(":")
    expected = _b64decode(key)
    actual = hashlib.scrypt(password.encode(), salt=_b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    return hmac.compare_digest(actual, expected)


def parse_local_users(raw: str) -> dict[str, str]:
    """Parse ``username=hash,...`` into ``{username: hash}``.

    Raises ValueError on a malformed entry, so a typo stops MDR at startup instead
    of silently locking a user out.
    """
    users: dict[str, str] = {}
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        username, sep, stored = (part.strip() for part in entry.partition("="))
        if not sep or not username:
            raise ValueError(f"MDR__AUTH__LOCAL_USERS entry {entry!r} is not username=hash")
        fields = stored.split(":")
        if len(fields) != 6 or fields[0] != "scrypt" or not all(f.isdigit() for f in fields[1:4]):
            raise ValueError(
                f"MDR__AUTH__LOCAL_USERS hash for {username!r} is not in the scrypt:n:r:p:salt:key "
                "format; generate one with scripts/hash-mdr-password.py"
            )
        if username in users:
            raise ValueError(f"MDR__AUTH__LOCAL_USERS lists {username!r} more than once")
        users[username] = stored
    return users
