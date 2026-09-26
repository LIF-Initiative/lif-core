"""Tests for configured MDR logins (MDR__AUTH__LOCAL_USERS, #1316)."""

# database_setup constructs a SQLAlchemy engine at import time from the
# POSTGRESQL_* env vars. /login never touches the engine, but the URL still has
# to parse.
import os

os.environ.setdefault("POSTGRESQL_USER", "test")
os.environ.setdefault("POSTGRESQL_PASSWORD", "test")
os.environ.setdefault("POSTGRESQL_HOST", "localhost")
os.environ.setdefault("POSTGRESQL_PORT", "5432")
os.environ.setdefault("POSTGRESQL_DB", "test")

import subprocess  # noqa: E402
import sys  # noqa: E402
from unittest import mock  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from lif.mdr_restapi import core  # noqa: E402
from lif.mdr_restapi.local_users import hash_password, parse_local_users, verify_password  # noqa: E402

ALICE_PASSWORD = "correct horse battery staple"
ALICE_HASH = hash_password(ALICE_PASSWORD)


def test_hash_verifies_only_the_original_password():
    assert verify_password(ALICE_PASSWORD, ALICE_HASH)
    assert not verify_password(ALICE_PASSWORD + "x", ALICE_HASH)


def test_hash_is_salted_and_safe_to_paste_into_env_files():
    other = hash_password(ALICE_PASSWORD)
    assert other != ALICE_HASH
    # `$` triggers Compose interpolation; `,` and `=` are the list delimiters.
    for ch in "$,=":
        assert ch not in ALICE_HASH


def test_parse_reads_several_users_and_ignores_blank_entries():
    bob_hash = hash_password("bob-pass")
    users = parse_local_users(f" alice@example.org = {ALICE_HASH} , ,bob={bob_hash},")
    assert users == {"alice@example.org": ALICE_HASH, "bob": bob_hash}
    assert parse_local_users("") == {}


@pytest.mark.parametrize(
    "raw, message",
    [
        ("alice", "not username=hash"),
        (f"={ALICE_HASH}", "not username=hash"),
        ("alice=plaintext-password", "scrypt:n:r:p:salt:key"),
        ("alice=scrypt:x:8:1:salt:key", "scrypt:n:r:p:salt:key"),
        (f"alice={ALICE_HASH},alice={ALICE_HASH}", "more than once"),
    ],
)
def test_parse_rejects_malformed_entries(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_local_users(raw)


@pytest.fixture
async def login_client():
    async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
        yield client


async def test_configured_user_can_log_in(login_client):
    with mock.patch.object(core, "LOCAL_USERS", {"alice@example.org": ALICE_HASH}):
        response = await login_client.post("/login", json={"username": "alice@example.org", "password": ALICE_PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["username"] == "alice@example.org"
    assert response.json()["access_token"]


async def test_configured_user_with_wrong_password_is_rejected(login_client):
    with mock.patch.object(core, "LOCAL_USERS", {"alice@example.org": ALICE_HASH}):
        response = await login_client.post("/login", json={"username": "alice@example.org", "password": "wrong"})
    assert response.status_code == 401


async def test_configured_users_replace_the_demo_personas(login_client):
    persona = {"username": core.users_db[0]["username"], "password": core.DEMO_USER_PASSWORD}
    # Control: the persona logs in when no users are configured...
    with mock.patch.object(core, "LOCAL_USERS", {}):
        assert (await login_client.post("/login", json=persona)).status_code == 200
    # ...and is locked out once any are.
    with mock.patch.object(core, "LOCAL_USERS", {"alice@example.org": ALICE_HASH}):
        assert (await login_client.post("/login", json=persona)).status_code == 401


def _import_core(**env_overrides: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("LIF_DEMO_USER_PASSWORD", "MDR__AUTH__LOCAL_USERS")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import lif.mdr_restapi.core"], env=env, capture_output=True, text=True
    )


def test_startup_needs_no_demo_password_when_users_are_configured():
    result = _import_core(MDR__AUTH__LOCAL_USERS=f"alice={ALICE_HASH}")
    assert result.returncode == 0, result.stderr


def test_startup_still_requires_a_demo_password_when_no_users_are_configured():
    result = _import_core()
    assert result.returncode != 0
    assert "LIF_DEMO_USER_PASSWORD is not set" in result.stderr
