"""HS256 token minting/decoding in mdr_auth — pinned before the #548 auth_utils refactor."""

import time
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException
from lif.mdr_auth.core import SECRET_KEY, create_access_token, create_refresh_token, decode_jwt


def test_access_token_has_access_type_and_custom_expiry():
    payload = decode_jwt(create_access_token({"sub": "alice"}, expires_delta=timedelta(minutes=5)))
    assert payload["sub"] == "alice"
    assert payload["type"] == "access"
    assert abs(payload["exp"] - (time.time() + 5 * 60)) < 5


def test_access_token_type_overrides_caller_type():
    assert decode_jwt(create_access_token({"sub": "alice", "type": "refresh"}))["type"] == "access"


def test_refresh_token_has_refresh_type_and_unique_jti():
    first = decode_jwt(create_refresh_token({"sub": "alice"}))
    second = decode_jwt(create_refresh_token({"sub": "alice"}))
    assert first["type"] == "refresh"
    assert first["jti"] and second["jti"] and first["jti"] != second["jti"]


def test_create_does_not_mutate_input():
    data = {"sub": "alice"}
    create_access_token(data)
    create_refresh_token(data)
    assert data == {"sub": "alice"}


def test_decode_expired_token_401_with_bearer_challenge():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) - 60}, SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has expired"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_decode_wrong_secret_401_with_bearer_challenge():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) + 60}, "some-other-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)
    assert exc.value.detail == "Could not validate credentials"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
