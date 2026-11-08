"""Postgres-backed tests for a tenant session's reads after commit (issue #1477).

`get_session` sets the tenant search_path on the connection the session first uses. A commit hands that
connection back to the pool, so the refresh that follows can run on another connection whose search_path
is `public` or another tenant's. A NullPool engine gives every checkout a new connection (search_path
`public`), which makes that case happen every time instead of only under concurrent traffic.
"""

# cspell:ignore agen

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from lif.mdr_dto.attribute_dto import UpdateAttributeDTO
from lif.mdr_dto.entity_dto import UpdateEntityDTO
from lif.mdr_services import attribute_service, entity_service
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool


@pytest.fixture
def tenant(pg_conn):
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture
async def tenant_session(postgres_server, monkeypatch):
    """Open a session through `get_session` for a tenant, on an engine that never reuses a connection."""
    from lif.mdr_utils import database_setup

    parsed = urlparse(postgres_server.url())
    url = f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    engine = create_async_engine(url, poolclass=NullPool)
    monkeypatch.setattr(
        database_setup, "async_session", sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    )

    @asynccontextmanager
    async def open_session(schema):
        agen = database_setup.get_session(SimpleNamespace(state=SimpleNamespace(tenant_schema=schema)))
        try:
            yield await agen.__anext__()
        finally:
            await agen.aclose()

    yield open_session
    await engine.dispose()


def _tenant_only_entity(pg_conn, schema):
    """Copy one of the tenant's entities under an Id that `public` doesn't have, like a tenant's own entity."""
    with pg_conn.cursor() as cur:
        cur.execute(
            f'CREATE TEMP TABLE entity_1477 AS SELECT * FROM "{schema}"."Entities" WHERE NOT "Deleted" ORDER BY "Id" LIMIT 1'
        )
        cur.execute(
            f"""UPDATE entity_1477 SET "UniqueName" = "UniqueName" || '_1477', "Id" = 1 + GREATEST(
                (SELECT max("Id") FROM public."Entities"), (SELECT max("Id") FROM "{schema}"."Entities"))"""
        )
        cur.execute(
            f'INSERT INTO "{schema}"."Entities" OVERRIDING SYSTEM VALUE SELECT * FROM entity_1477 RETURNING "Id"'
        )
        entity_id = cur.fetchone()[0]
        cur.execute("DROP TABLE entity_1477")
    return entity_id


async def test_update_entity_refreshes_a_tenant_only_entity(pg_conn, tenant, tenant_session):
    entity_id = _tenant_only_entity(pg_conn, tenant)

    async with tenant_session(tenant) as session:
        updated = await entity_service.update_entity(session, entity_id, UpdateEntityDTO(Description="tenant 1477"))

    assert updated.Description == "tenant 1477"


async def test_update_attribute_returns_the_tenant_row_not_public(pg_conn, tenant, tenant_session):
    with pg_conn.cursor() as cur:
        cur.execute(f'SELECT "Id" FROM "{tenant}"."Attributes" WHERE NOT "Deleted" ORDER BY "Id" LIMIT 1')
        attribute_id = cur.fetchone()[0]

    async with tenant_session(tenant) as session:
        updated = await attribute_service.update_attribute(
            session, attribute_id, UpdateAttributeDTO(Description="tenant 1477")
        )

    assert updated.Description == "tenant 1477"
