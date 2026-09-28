"""Postgres-backed tests for the schema-drift queries (#1226).

The SQL is the only part of this change that can be wrong, so it runs against a real
server rather than a mock. `testing.postgresql` needs a local PostgreSQL; the tests
skip without one, the same way `test_clone_lif_schema_sql.py` does.

The privilege case is the point. `information_schema` is filtered by the connecting
role, so a schema the role lacks USAGE on disappears from the result and reads as
clean -- the exact false negative this check exists to prevent. `pg_catalog` is not
filtered. These pin that difference.
"""

import pytest

pytest.importorskip("testing.postgresql")
pytest.importorskip("psycopg2")

import testing.postgresql  # noqa: E402
import psycopg2  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from lif.mdr_services import schema_drift_service  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest.fixture
def server():
    try:
        pg = testing.postgresql.Postgresql()
    except RuntimeError as exc:  # pragma: no cover - environment-specific
        pytest.skip(f"PostgreSQL not available locally: {exc}")
    with pg:
        yield pg


def _seed(pg, *, hide_from_mdr: bool) -> None:
    """public has TargetEntityId; two tenant schemas do not. One is unreadable by mdr."""
    conn = psycopg2.connect(**pg.dsn())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE ROLE mdr LOGIN PASSWORD 'x'")
    cur.execute('CREATE TABLE public."Attributes" (id int, "TargetEntityId" bigint)')
    cur.execute("GRANT USAGE ON SCHEMA public TO mdr")
    cur.execute('GRANT SELECT ON public."Attributes" TO mdr')
    for schema in ("tenant_visible", "tenant_hidden"):
        cur.execute(f"CREATE SCHEMA {schema}")
        cur.execute(f'CREATE TABLE {schema}."Attributes" (id int)')  # drifted: no TargetEntityId
    cur.execute("GRANT USAGE ON SCHEMA tenant_visible TO mdr")
    if not hide_from_mdr:
        cur.execute("GRANT USAGE ON SCHEMA tenant_hidden TO mdr")
    conn.close()


async def _drift_as(pg, user: str) -> list[dict]:
    dsn = pg.dsn()
    password = "x" if user == "mdr" else ""
    url = f"postgresql+asyncpg://{user}:{password}@{dsn['host']}:{dsn['port']}/{dsn['database']}"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            return await schema_drift_service.tenant_schema_drift(session)
    finally:
        await engine.dispose()


async def test_reports_a_schema_the_connecting_role_cannot_read(server):
    """The regression this exists for: a drifted schema must not vanish with the role."""
    _seed(server, hide_from_mdr=True)
    result = await _drift_as(server, "mdr")

    by_schema = {row["schema"]: row["missing"] for row in result}
    assert "tenant_hidden" in by_schema, (
        "a schema the role lacks USAGE on disappeared from the report -- this is the information_schema false negative"
    )
    assert by_schema["tenant_hidden"] == ["Attributes.TargetEntityId"]
    assert by_schema["tenant_visible"] == ["Attributes.TargetEntityId"]


async def test_a_current_tenant_reports_no_drift(server):
    _seed(server, hide_from_mdr=False)
    conn = psycopg2.connect(**server.dsn())
    conn.autocommit = True
    conn.cursor().execute('ALTER TABLE tenant_visible."Attributes" ADD COLUMN "TargetEntityId" bigint')
    conn.close()

    by_schema = {row["schema"]: row["missing"] for row in await _drift_as(server, "mdr")}
    assert by_schema["tenant_visible"] == []
    assert by_schema["tenant_hidden"] == ["Attributes.TargetEntityId"]


async def test_only_tenant_prefixed_schemas_are_counted(server):
    """An extension or tooling schema must not inflate the 'all N match' denominator."""
    _seed(server, hide_from_mdr=False)
    conn = psycopg2.connect(**server.dsn())
    conn.autocommit = True
    conn.cursor().execute("CREATE SCHEMA some_extension")
    conn.close()

    names = {row["schema"] for row in await _drift_as(server, "mdr")}
    assert names == {"tenant_visible", "tenant_hidden"}
    assert "some_extension" not in names


async def test_no_flyway_history_means_flyway_never_ran(server):
    _seed(server, hide_from_mdr=False)
    dsn = server.dsn()
    url = f"postgresql+asyncpg://mdr:x@{dsn['host']}:{dsn['port']}/{dsn['database']}"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            assert await schema_drift_service.applied_migrations(session) == []
    finally:
        await engine.dispose()
