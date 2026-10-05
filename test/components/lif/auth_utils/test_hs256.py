import time
from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException

from lif.auth_utils.hs256 import decode_hs256, encode_hs256

SECRET = "test-only-hs256-secret"


def test_round_trip_sets_exp():
    payload = decode_hs256(encode_hs256({"sub": "alice"}, SECRET, timedelta(minutes=5)), SECRET)
    assert payload["sub"] == "alice"
    assert abs(payload["exp"] - (time.time() + 5 * 60)) < 5


def test_encode_does_not_mutate_claims():
    claims = {"sub": "alice"}
    encode_hs256(claims, SECRET, timedelta(minutes=5))
    assert claims == {"sub": "alice"}


@pytest.mark.parametrize(
    ("token", "detail"),
    [
        (jwt.encode({"sub": "a", "exp": int(time.time()) - 60}, SECRET, algorithm="HS256"), "Token has expired"),
        (
            jwt.encode({"sub": "a", "exp": int(time.time()) + 60}, "other", algorithm="HS256"),
            "Could not validate credentials",
        ),
        ("not-a-jwt", "Could not validate credentials"),
    ],
)
def test_decode_failures_raise_401_with_bearer_challenge(token, detail):
    with pytest.raises(HTTPException) as exc:
        decode_hs256(token, SECRET)
    assert exc.value.status_code == 401
    assert exc.value.detail == detail
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}
