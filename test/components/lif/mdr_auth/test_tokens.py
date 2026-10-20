"""MDR's HS256 config and error contract, now provided by lif.auth.jwt (ADR 0007)."""

import time
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from lif.auth.jwt import verify
from lif.mdr_auth.core import JWT_CONFIG, SECRET_KEY, settings


def test_jwt_config_uses_mdr_secret_and_lifetimes():
    assert JWT_CONFIG.secret == SECRET_KEY
    assert JWT_CONFIG.access_token_expires == timedelta(minutes=settings.mdr__auth__access_token_expire_minutes)
    assert JWT_CONFIG.refresh_token_expires == timedelta(days=settings.mdr__auth__refresh_token_expire_days)


def test_verify_expired_token_401_with_bearer_challenge():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) - 60}, SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify(JWT_CONFIG, token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has expired"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_verify_wrong_secret_401_with_bearer_challenge():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) + 60}, "some-other-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify(JWT_CONFIG, token)
    assert exc.value.detail == "Could not validate credentials"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
