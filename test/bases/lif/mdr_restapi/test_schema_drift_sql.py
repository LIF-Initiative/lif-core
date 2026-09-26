"""Postgres-backed tests for the schema-drift queries (issue #1226).

The four tests in ``test_admin_endpoints.py`` mock both service functions, so they
cover the response model and the auth dependency and nothing about the SQL. The SQL
is the only part of this change that can actually be wrong -- a typo in a
``pg_catalog`` join ships green through a mocked suite and then reports every tenant
schema as clean, which is the exact false negative #1226 exists to prevent.

So exercise it end-to-end against a real Postgres, following the pattern
``test_clone_lif_schema_sql.py`` established: reuse the session-scoped
``postgres_server`` fixture and skip cleanly where Postgres is not installed.
"""

from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lif.mdr_services.schema_drift_service import applied_migrations, tenant_schema_drift


@pytest_asyncio.fixture
async def drift_session(postgres_server):
    """An async session against a scratch database shaped like a drifted MDR.

    ``public`` gets a table; one tenant schema is a faithful clone, a second is
    missing a column that was added to ``public`` afterwards -- the shape a
    ``ALTER TABLE public.…`` migration leaves behind (#1265).
    """
    parsed = urlparse(postgres_server.url())
    url = f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    engine = create_async_engine(url)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        for stmt in (
            "DROP SCHEMA IF EXISTS tenant_clean CASCADE",
            "DROP SCHEMA IF EXISTS tenant_drifted CASCADE",
            "DROP TABLE IF EXISTS public.drift_probe CASCADE",
            "CREATE TABLE public.drift_probe (id int primary key, name text)",
            "CREATE SCHEMA tenant_clean",
            "CREATE TABLE tenant_clean.drift_probe (id int primary key, name text)",
            "CREATE SCHEMA tenant_drifted",
            "CREATE TABLE tenant_drifted.drift_probe (id int primary key, name text)",
            # The migration that only ever reached `public`:
            "ALTER TABLE public.drift_probe ADD COLUMN target_entity_id text",
        ):
            await _exec(session, stmt)
        await session.commit()
        yield session
        for stmt in (
            "DROP SCHEMA IF EXISTS tenant_clean CASCADE",
            "DROP SCHEMA IF EXISTS tenant_drifted CASCADE",
            "DROP TABLE IF EXISTS public.drift_probe CASCADE",
        ):
            await _exec(session, stmt)
        await session.commit()
    await engine.dispose()


async def _exec(session, stmt: str) -> None:
    await session.execute(text(stmt))


@pytest.mark.asyncio
async def test_drift_reports_the_column_a_public_only_migration_left_behind(drift_session):
    """The #1265 shape: ALTER TABLE public.… never reaches the tenant clones."""
    result = {row["schema"]: row["missing"] for row in await tenant_schema_drift(drift_session)}

    assert "drift_probe.target_entity_id" in result["tenant_drifted"]
    assert "drift_probe.target_entity_id" in result["tenant_clean"]


@pytest.mark.asyncio
async def test_a_schema_matching_public_reports_no_missing_columns(drift_session):
    """Guards the other direction: a faithful clone must not be reported as drifted."""
    await _exec(drift_session, "ALTER TABLE tenant_clean.drift_probe ADD COLUMN target_entity_id text")
    await drift_session.commit()

    result = {row["schema"]: row["missing"] for row in await tenant_schema_drift(drift_session)}

    assert result["tenant_clean"] == []
    assert result["tenant_drifted"] == ["drift_probe.target_entity_id"]


@pytest.mark.asyncio
async def test_every_tenant_schema_is_listed_even_when_clean(drift_session):
    """The denominator has to be real: a clean schema is reported with an empty list,
    not omitted. An omitted schema is indistinguishable from one that does not exist."""
    schemas = {row["schema"] for row in await tenant_schema_drift(drift_session)}

    assert {"tenant_clean", "tenant_drifted"} <= schemas
    assert not any(s == "public" for s in schemas)


@pytest.mark.asyncio
async def test_applied_migrations_is_empty_when_flyway_never_ran(drift_session):
    """The table's absence is itself the answer, and must not raise."""
    assert await applied_migrations(drift_session) == []


@pytest.mark.asyncio
async def test_a_column_dropped_from_public_is_not_reported_as_tenant_drift(drift_session):
    """Postgres keeps the `pg_attribute` row for a dropped column, renaming it to
    `........pg.dropped.N........` with `attisdropped = true`. Without the
    `NOT a.attisdropped` guard that pseudo-column joins as a real column of
    `public`, and since no tenant has a column by that name it is reported as
    missing from every one of them -- a false positive that buries the real drift."""
    await _exec(drift_session, "ALTER TABLE public.drift_probe DROP COLUMN name")
    await drift_session.commit()

    result = {row["schema"]: row["missing"] for row in await tenant_schema_drift(drift_session)}

    assert not any("pg.dropped" in col for cols in result.values() for col in cols), result
    # and the column that really is missing is still reported
    assert "drift_probe.target_entity_id" in result["tenant_drifted"]
