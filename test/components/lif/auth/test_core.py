import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from lif.auth import core


def test_sample():
    assert core is not None


# ---- Current-behavior tests (#548): pin the HS256 contract before refactoring ----


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_access_token_expires_in_30_minutes():
    payload = core.decode_jwt(core.create_access_token({"sub": "alice"}))
    assert payload["sub"] == "alice"
    assert abs(payload["exp"] - (time.time() + 30 * 60)) < 5


def test_refresh_token_expires_in_7_days():
    payload = core.decode_jwt(core.create_refresh_token({"sub": "alice"}))
    assert abs(payload["exp"] - (time.time() + 7 * 24 * 60 * 60)) < 5


def test_create_does_not_mutate_input():
    data = {"sub": "alice"}
    core.create_access_token(data)
    core.create_refresh_token(data)
    assert data == {"sub": "alice"}


def test_decode_expired_token_401():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) - 60}, core.SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        core.decode_jwt(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has expired"
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_decode_wrong_secret_401():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) + 60}, "some-other-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        core.decode_jwt(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"


async def test_get_current_user_returns_sub():
    assert await core.get_current_user(_bearer(core.create_access_token({"sub": "alice"}))) == "alice"


async def test_get_current_user_without_sub_401():
    with pytest.raises(HTTPException) as exc:
        await core.get_current_user(_bearer(core.create_access_token({"name": "no-sub"})))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authentication credentials"


async def test_get_current_user_expired_401():
    token = jwt.encode({"sub": "alice", "exp": int(time.time()) - 60}, core.SECRET_KEY, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        await core.get_current_user(_bearer(token))
    assert exc.value.detail == "Token has expired"
