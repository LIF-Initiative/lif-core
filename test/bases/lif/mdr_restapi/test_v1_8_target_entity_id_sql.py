"""Postgres-backed tests for the V1.8 migration: V1.6's Attributes.TargetEntityId in every tenant schema.

V1.6 added the column, its FK and its index to public only, so a tenant schema that already existed
(locally, tenant_lif_team in backup.sql) never got them. Tenants cloned later do, because
clone_lif_schema copies public's columns, indexes and FKs. V1.8 adds whatever is missing per schema.

backup.sql (loaded by conftest's postgres_server) already contains V1.8's result, so each test clones
a tenant, takes away what V1.6 would have left out, and re-runs V1.8.
"""
# cspell:ignore confdeltype

import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest

_V1_8 = (
    Path(__file__).parent.parent.parent.parent.parent
    / "sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.8__tenant_attributes_target_entity_id.sql"
)


def apply_v1_8(postgres_server):
    parsed = urlparse(postgres_server.url())
    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""
    result = subprocess.run(
        [
            "psql",
            "-h",
            parsed.hostname,
            "-p",
            str(parsed.port),
            "-U",
            parsed.username,
            "-d",
            parsed.path.lstrip("/"),
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(_V1_8),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to apply V1.8: {result.stderr}")


@pytest.fixture
def pg_conn(postgres_server):
    parsed = urlparse(postgres_server.url())
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password or "",
        dbname=parsed.path.lstrip("/"),
    )
    conn.autocommit = True
    yield conn
    conn.close()


def _clone_tenant(pg_conn):
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
    return schema


@pytest.fixture
def tenant_without_column(pg_conn):
    """A tenant as V1.6 left tenant_lif_team: no column, so no FK or index either."""
    schema = _clone_tenant(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute(f'ALTER TABLE "{schema}"."Attributes" DROP COLUMN "TargetEntityId"')
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture
def tenant_without_fk(pg_conn):
    """A tenant with the column but no FK, while public keeps its FK of the same name.

    A guard that looks the constraint up by name across the whole database finds public's and skips
    this tenant's FK.
    """
    schema = _clone_tenant(pg_conn)
    with pg_conn.cursor() as cur:
        cur.execute(f'ALTER TABLE "{schema}"."Attributes" DROP CONSTRAINT "Fk_Attributes_TargetEntityId"')
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _target_entity_state(cur, schema):
    """(has column, FK targets, FK on-delete actions, has index) for schema."Attributes"."""
    table = f'"{schema}"."Attributes"'
    cur.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = 'Attributes' AND column_name = 'TargetEntityId'",
        (schema,),
    )
    has_column = cur.fetchone()[0] == 1
    cur.execute(
        "SELECT confrelid::regclass::text, confdeltype FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND contype = 'f' AND conname = 'Fk_Attributes_TargetEntityId'",
        (table,),
    )
    fks = cur.fetchall()
    cur.execute(
        "SELECT count(*) FROM pg_indexes WHERE schemaname = %s AND indexname = 'ix_Attributes_TargetEntityId'",
        (schema,),
    )
    has_index = cur.fetchone()[0] == 1
    return has_column, [fk[0] for fk in fks], [fk[1] for fk in fks], has_index


def _assert_complete(cur, schema):
    has_column, fk_targets, fk_actions, has_index = _target_entity_state(cur, schema)
    assert has_column, schema
    # The tenant's own Entities, not public's: a tenant's attribute must not point into another schema.
    cur.execute("SELECT %s::regclass::text", (f'"{schema}"."Entities"',))
    assert fk_targets == [cur.fetchone()[0]], schema
    assert fk_actions == ["n"], schema  # ON DELETE SET NULL, as in V1.6
    assert has_index, schema


class TestV18:
    def test_adds_column_fk_and_index_to_a_tenant_without_the_column(
        self, postgres_server, pg_conn, tenant_without_column
    ):
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            _assert_complete(cur, tenant_without_column)
            cur.execute(
                f'SELECT count(*) FROM "{tenant_without_column}"."Attributes" WHERE "TargetEntityId" IS NOT NULL'
            )
            assert cur.fetchone()[0] == 0  # Not backfilled: the target was never recorded for this tenant.

    def test_adds_the_fk_when_only_public_has_one_of_that_name(self, postgres_server, pg_conn, tenant_without_fk):
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            _assert_complete(cur, tenant_without_fk)

    def test_leaves_public_and_its_targets_unchanged(self, postgres_server, pg_conn, tenant_without_column):
        with pg_conn.cursor() as cur:
            cur.execute('SELECT "Id", "TargetEntityId" FROM public."Attributes" WHERE "TargetEntityId" IS NOT NULL')
            before = sorted(cur.fetchall())
        assert before  # The seed records Open Badges v3 targets (V1.6).
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            _assert_complete(cur, "public")
            cur.execute('SELECT "Id", "TargetEntityId" FROM public."Attributes" WHERE "TargetEntityId" IS NOT NULL')
            assert sorted(cur.fetchall()) == before

    def test_replay_changes_nothing(self, postgres_server, pg_conn, tenant_without_column):
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            first = _target_entity_state(cur, tenant_without_column)
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            assert _target_entity_state(cur, tenant_without_column) == first

    def test_every_schema_is_complete(self, postgres_server, pg_conn, tenant_without_column):
        apply_v1_8(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_'")
            schemas = [row[0] for row in cur.fetchall()]
            assert tenant_without_column in schemas
            for schema in schemas:
                _assert_complete(cur, schema)
