"""The control plane's workspace-scoped key store (#1182, ADR 0006, ADR 0008).

Runs against a throwaway PostgreSQL with the control plane's real migration applied, so the model
and the SQL are checked against each other. Skips when PostgreSQL isn't installed locally (CI has it).
"""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest
import testing.postgresql
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from lif.developer_keys import (
    CreateDeveloperApiKeyDTO,
    WorkspaceDeveloperApiKey,
    create_workspace_developer_api_key,
    list_workspace_developer_api_keys,
    revoke_workspace_developer_api_key,
)

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "projects"
    / "lif_control_plane_database"
    / "migrations"
    / "V1.0__developer_api_keys.sql"
)


@pytest.fixture(scope="module")
def postgres_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    parsed = urlparse(postgresql.url())
    yield f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    postgresql.stop()


@pytest.fixture
async def sessions(postgres_url):
    engine = create_async_engine(postgres_url)
    sql = MIGRATION.read_text()
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS "DeveloperApiKeys"'))
        raw = (await conn.get_raw_connection()).driver_connection
        for _ in range(2):  # applied twice: the migration must be idempotent
            await raw.execute(sql)  # asyncpg's simple protocol runs a multi-statement script, as initdb does
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_list_returns_only_the_callers_keys_in_that_workspace(sessions):
    async with sessions() as session:
        mine = await create_workspace_developer_api_key(
            session, "tenant_a", "alice", CreateDeveloperApiKeyDTO(Label="1")
        )
        await create_workspace_developer_api_key(session, "tenant_b", "alice", CreateDeveloperApiKeyDTO(Label="2"))
        await create_workspace_developer_api_key(session, "tenant_a", "bob", CreateDeveloperApiKeyDTO(Label="3"))

    async with sessions() as session:
        listed = await list_workspace_developer_api_keys(session, "tenant_a", "alice")

    assert [(k.Id, k.Label) for k in listed] == [(mine.Id, "1")]
    assert listed[0].KeyPrefix == mine.Key[:12]
    assert listed[0].RevokedDate is None


async def test_the_raw_key_is_not_stored(sessions):
    async with sessions() as session:
        created = await create_workspace_developer_api_key(
            session, "tenant_a", "alice", CreateDeveloperApiKeyDTO(Label="x")
        )
        row = await session.get(WorkspaceDeveloperApiKey, created.Id)

    assert row is not None
    assert row.Workspace == "tenant_a"
    assert created.Key not in (row.KeyHash, row.KeyPrefix)


async def test_key_hash_is_unique_in_the_database(sessions):
    async with sessions() as session:
        created = await create_workspace_developer_api_key(
            session, "tenant_a", "alice", CreateDeveloperApiKeyDTO(Label="x")
        )
        row = await session.get(WorkspaceDeveloperApiKey, created.Id)
        assert row is not None
        session.add(
            WorkspaceDeveloperApiKey(
                Workspace="tenant_b", OwnerSub="bob", Label="dup", KeyPrefix=row.KeyPrefix, KeyHash=row.KeyHash
            )
        )
        with pytest.raises(IntegrityError, match="ux_DeveloperApiKeys_KeyHash"):
            await session.commit()


async def test_revoke_needs_ownership_only_and_keeps_the_first_revocation(sessions):
    async with sessions() as session:
        created = await create_workspace_developer_api_key(
            session, "tenant_b", "alice", CreateDeveloperApiKeyDTO(Label="x")
        )

    async with sessions() as session:
        with pytest.raises(HTTPException) as exc:
            await revoke_workspace_developer_api_key(session, "bob", created.Id)
        assert exc.value.status_code == 404

    async with sessions() as session:
        with pytest.raises(HTTPException) as exc:
            await revoke_workspace_developer_api_key(session, "alice", created.Id + 1000)
        assert exc.value.status_code == 404

    # No workspace is given: the owner can revoke a key in a workspace they may have left.
    async with sessions() as session:
        await revoke_workspace_developer_api_key(session, "alice", created.Id)
    async with sessions() as session:
        first = (await session.get(WorkspaceDeveloperApiKey, created.Id)).RevokedDate
        await revoke_workspace_developer_api_key(session, "alice", created.Id)
    async with sessions() as session:
        again = (await session.get(WorkspaceDeveloperApiKey, created.Id)).RevokedDate

    assert first is not None and first <= datetime.now(timezone.utc)
    assert again == first


def test_the_store_stays_off_the_mdr_models_metadata():
    # MDR's DeveloperApiKey maps "DeveloperApiKeys" on SQLModel.metadata without a Workspace column.
    # Sharing that metadata would clash on the table name, or leak this table into MDR's.
    assert WorkspaceDeveloperApiKey.metadata is not SQLModel.metadata
    mdr_table = SQLModel.metadata.tables.get("DeveloperApiKeys")
    assert mdr_table is not None and "Workspace" not in mdr_table.c
