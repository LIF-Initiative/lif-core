"""Developer API key service (#1033).

Keys are created with the raw value returned once and stored hashed; listing/revocation are
scoped to the owning Cognito `sub`. Drives the real service against a live Postgres
(``test_db_session``). The fixture DB is only the V1.1 baseline (backup.sql) and does not replay
the V1.5 migration, so the ``dev_keys_table`` fixture creates the table. Owners are keyed off the
test name (``request.node.name``) since the DB is shared across tests.
"""

import hashlib

import pytest
from fastapi import HTTPException
from sqlmodel import select

from lif.datatypes.mdr_sql_model import DeveloperApiKey
from lif.mdr_dto.developer_api_key_dto import CreateDeveloperApiKeyDTO
from lif.mdr_services.developer_api_key_service import (
    create_developer_api_key,
    list_developer_api_keys,
    revoke_developer_api_key,
)


@pytest.fixture
async def dev_keys_table(test_db_session):
    engine = test_db_session.bind
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: DeveloperApiKey.__table__.create(c, checkfirst=True))
    yield


async def test_create_stores_hash_and_returns_raw_key_once(test_db_session, dev_keys_table, request):
    session = test_db_session
    owner = request.node.name

    created = await create_developer_api_key(session, owner, CreateDeveloperApiKeyDTO(Label="my app"))

    assert created.Key.startswith("lifk_")
    assert created.KeyPrefix == created.Key[:12]
    # Stored hashed — the raw key is never persisted.
    row = (await session.execute(select(DeveloperApiKey).where(DeveloperApiKey.Id == created.Id))).scalars().one()
    assert row.KeyHash == hashlib.sha256(created.Key.encode()).hexdigest()
    assert row.KeyHash != created.Key


async def test_list_is_scoped_to_owner_and_omits_raw_key(test_db_session, dev_keys_table, request):
    session = test_db_session
    owner_a, owner_b = f"{request.node.name}-a", f"{request.node.name}-b"

    a1 = await create_developer_api_key(session, owner_a, CreateDeveloperApiKeyDTO(Label="a1"))
    await create_developer_api_key(session, owner_b, CreateDeveloperApiKeyDTO(Label="b1"))

    keys = await list_developer_api_keys(session, owner_a)
    assert [k.Id for k in keys] == [a1.Id]  # only owner_a's key
    assert not hasattr(keys[0], "Key")  # listing never exposes the raw key


async def test_revoke_sets_revoked_date_and_enforces_ownership(test_db_session, dev_keys_table, request):
    session = test_db_session
    owner, other = f"{request.node.name}-owner", f"{request.node.name}-other"

    created = await create_developer_api_key(session, owner, CreateDeveloperApiKeyDTO(Label="k"))

    # A different user cannot revoke it — 404 (not 403), so other users' key ids aren't revealed.
    with pytest.raises(HTTPException) as exc:
        await revoke_developer_api_key(session, other, created.Id)
    assert exc.value.status_code == 404

    await revoke_developer_api_key(session, owner, created.Id)
    row = (await session.execute(select(DeveloperApiKey).where(DeveloperApiKey.Id == created.Id))).scalars().one()
    assert row.RevokedDate is not None
