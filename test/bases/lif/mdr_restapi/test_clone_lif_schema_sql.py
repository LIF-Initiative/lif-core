"""Postgres-backed tests for the clone_lif_schema PL/pgSQL function (issue #883).

The function is the load-bearing piece of MDR self-serve tenant provisioning:
the post-confirmation Lambda calls POST /tenants/provision after a new user
registers, and the endpoint delegates to clone_lif_schema to create their
isolated workspace. A typo or PG-version regression would silently break
self-serve onboarding, so we exercise it end-to-end against a real Postgres.

Reuses the session-scoped postgres_server fixture from conftest.py and
applies V1.2 + V1.4 (the bugfix migration) on top of the V1.1 baseline.
"""

import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest

# SQLSTATE codes — the function raises P0001 from RAISE EXCEPTION (no USING
# ERRCODE for validation errors) and 42P06 from the duplicate-schema branch.
# Match by pgcode rather than the dynamically-generated psycopg2.errors.*
# classes since the static type checker can't resolve those.
SQLSTATE_RAISE_EXCEPTION = "P0001"
SQLSTATE_DUPLICATE_SCHEMA = "42P06"

_FLYWAY_DIR = Path(__file__).parent.parent.parent.parent.parent / "sam/mdr-database/flyway/flyway-files/flyway/sql/mdr"
TENANT_ROUTING_MIGRATIONS = ["V1.2__clone_lif_schema_function.sql", "V1.4__clone_lif_schema_overriding_identity.sql"]


@pytest.fixture(scope="session")
def postgres_with_clone_function(postgres_server):
    """postgres_server + V1.2/V1.4 migrations applied.

    Mirrors deploy order: V1.2 installs the function, V1.4 fixes its data
    INSERT to handle GENERATED ALWAYS identity columns. We apply both even
    though V1.4 fully replaces V1.2 — running them in sequence proves the
    real migration chain stays valid.
    """
    parsed = urlparse(postgres_server.url())
    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""

    for migration in TENANT_ROUTING_MIGRATIONS:
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
                str(_FLYWAY_DIR / migration),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to apply {migration}: {result.stderr}")
    return postgres_server


@pytest.fixture
def pg_conn(postgres_with_clone_function):
    """Autocommit psycopg2 connection. Caller is responsible for cleaning up any schema it creates."""
    parsed = urlparse(postgres_with_clone_function.url())
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


@pytest.fixture
def tenant_schema(pg_conn):
    """A unique tenant_<hex> schema name, dropped on teardown."""
    name = f"tenant_t{uuid.uuid4().hex[:12]}"
    yield name
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def _public_table_names(cur) -> list[str]:
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    return [row[0] for row in cur.fetchall()]


def _schema_table_names(cur, schema: str) -> list[str]:
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename", (schema,))
    return [row[0] for row in cur.fetchall()]


def _row_count(cur, schema: str, table: str) -> int:
    cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
    return cur.fetchone()[0]


class TestCloneSchemaStructure:
    def test_clone_creates_every_public_table(self, pg_conn, tenant_schema):
        """DDL parity: every table in public exists in the clone, no extras.

        The function iterates pg_tables dynamically, so this passes by
        construction today. The test guards against regressions that break
        that contract — e.g. filtering tables by name pattern, switching to
        a hardcoded list, or narrowing the pg_tables query."""
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s)", (tenant_schema,))
            assert _schema_table_names(cur, tenant_schema) == _public_table_names(cur)

    def test_clone_preserves_foreign_keys_targeting_tenant_schema(self, pg_conn, tenant_schema):
        """FKs are copied via pg_get_constraintdef + regex rewrite. Confirm:
        (a) the clone has the same number of FK constraints as public, and
        (b) every FK in the clone references a table in the clone (not public)."""
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s)", (tenant_schema,))

            cur.execute(
                """
                SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON c.connamespace = n.oid
                WHERE n.nspname = %s AND c.contype = 'f'
                """,
                ("public",),
            )
            public_fk_count = cur.fetchone()[0]

            cur.execute(
                """
                SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON c.connamespace = n.oid
                WHERE n.nspname = %s AND c.contype = 'f'
                """,
                (tenant_schema,),
            )
            tenant_fk_count = cur.fetchone()[0]

            assert tenant_fk_count == public_fk_count > 0, "expected >0 FKs and parity with public"

            # Every FK target table in the clone must live in the clone schema.
            cur.execute(
                """
                SELECT target_ns.nspname
                FROM pg_constraint c
                JOIN pg_namespace src_ns ON c.connamespace = src_ns.oid
                JOIN pg_class target ON c.confrelid = target.oid
                JOIN pg_namespace target_ns ON target.relnamespace = target_ns.oid
                WHERE src_ns.nspname = %s AND c.contype = 'f'
                """,
                (tenant_schema,),
            )
            target_namespaces = {row[0] for row in cur.fetchall()}
            assert target_namespaces == {tenant_schema}, f"FK rewrite leaked to non-tenant schemas: {target_namespaces}"


class TestCloneSchemaData:
    def test_clone_copies_data_when_include_data_true(self, pg_conn, tenant_schema):
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s, TRUE)", (tenant_schema,))
            for table in _public_table_names(cur):
                assert _row_count(cur, tenant_schema, table) == _row_count(cur, "public", table), (
                    f"row count mismatch for {table}"
                )

    def test_clone_skips_data_when_include_data_false(self, pg_conn, tenant_schema):
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s, FALSE)", (tenant_schema,))
            tables = _public_table_names(cur)
            assert tables, "sanity: backup.sql should have populated public with tables"
            for table in tables:
                assert _row_count(cur, tenant_schema, table) == 0, f"{table} should be empty when include_data=false"

    def test_clone_advances_sequences_past_copied_max(self, pg_conn, tenant_schema):
        """If sequences weren't synced, the next insert into the clone would
        try to reuse a PK that came over with the data and violate the PK
        constraint. Inserting a row with default Id is the cheapest proof."""
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s, TRUE)", (tenant_schema,))
            # DataModels has the simplest required-column footprint of the cloned tables.
            cur.execute(
                f'INSERT INTO "{tenant_schema}"."DataModels" ("Name", "Type") VALUES (%s, %s) RETURNING "Id"',
                ("seq-sync-probe", "OrgLIF"),
            )
            new_id = cur.fetchone()[0]
            cur.execute('SELECT max("Id") FROM public."DataModels"')
            public_max = cur.fetchone()[0]
            assert new_id > public_max, f"clone sequence not synced: new id {new_id} not > public max {public_max}"


class TestCloneIsolation:
    def test_clone_does_not_modify_public(self, pg_conn, tenant_schema):
        """Defensive: cloning is read-only against public. If a future change
        accidentally introduces a write, this catches it."""
        with pg_conn.cursor() as cur:
            before = {t: _row_count(cur, "public", t) for t in _public_table_names(cur)}
            cur.execute("SELECT public.clone_lif_schema(%s)", (tenant_schema,))
            after = {t: _row_count(cur, "public", t) for t in _public_table_names(cur)}
        assert before == after

    def test_inserts_in_clone_invisible_in_public(self, pg_conn, tenant_schema):
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s, FALSE)", (tenant_schema,))
            cur.execute(
                f'INSERT INTO "{tenant_schema}"."DataModels" ("Name", "Type") VALUES (%s, %s)',
                ("isolation-probe", "OrgLIF"),
            )
            cur.execute('SELECT count(*) FROM public."DataModels" WHERE "Name" = %s', ("isolation-probe",))
            assert cur.fetchone()[0] == 0


class TestCloneValidation:
    @pytest.mark.parametrize(
        "bad_target",
        [
            "public_foo",  # doesn't start with tenant_
            "tenant_",  # empty suffix
            "tenant_1abc",  # suffix starts with digit, not letter
            "tenant_Foo",  # uppercase rejected
            "tenant_foo-bar",  # hyphen rejected
            "tenant_foo bar",  # space rejected
        ],
    )
    def test_rejects_non_conforming_target(self, pg_conn, bad_target):
        """The function's regex is stricter than a generic PG identifier check —
        it enforces the same shape as tenant_schema_for_group's output so
        callers can't bypass sanitization by hitting the SQL layer directly."""
        with pg_conn.cursor() as cur, pytest.raises(psycopg2.Error) as exc_info:
            cur.execute("SELECT public.clone_lif_schema(%s)", (bad_target,))
        assert exc_info.value.pgcode == SQLSTATE_RAISE_EXCEPTION

    def test_rejects_target_exceeding_pg_identifier_limit(self, pg_conn):
        # Postgres truncates identifiers >63 chars at parse time, which would
        # break the existence check; the function rejects up front instead.
        oversized = "tenant_" + ("a" * 60)  # 67 chars total
        with pg_conn.cursor() as cur, pytest.raises(psycopg2.Error) as exc_info:
            cur.execute("SELECT public.clone_lif_schema(%s)", (oversized,))
        assert exc_info.value.pgcode == SQLSTATE_RAISE_EXCEPTION


class TestCloneIdempotency:
    def test_second_clone_raises_duplicate_schema(self, pg_conn, tenant_schema):
        """The endpoint relies on this errcode to translate to its own
        TenantAlreadyExistsError → HTTP 200. If the SQL stops emitting
        duplicate_schema, the post-confirm Lambda would get a 500 instead
        of a benign 200 on retry."""
        with pg_conn.cursor() as cur:
            cur.execute("SELECT public.clone_lif_schema(%s)", (tenant_schema,))
            with pytest.raises(psycopg2.Error) as exc_info:
                cur.execute("SELECT public.clone_lif_schema(%s)", (tenant_schema,))
            assert exc_info.value.pgcode == SQLSTATE_DUPLICATE_SCHEMA
