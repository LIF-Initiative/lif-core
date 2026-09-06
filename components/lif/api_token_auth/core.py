import os

from fastapi import HTTPException


def verify_token(token: str) -> None:
    """Verify a caller-supplied token against the static ``API_TOKEN`` value.

    This is a shared-secret check, not a JWT: there is no signing, no claims and
    no expiry. It lives in its own brick rather than alongside the JWT helpers so
    that a service needing only this check does not have to configure a JWT
    signing key it never uses (see #1191).
    """
    expected = os.getenv("API_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
