"""Postgres-backed tests for the V1.10 element flag re-sync migration (issue #1395).

V1.10 copies LevelOfAccess, Queryable and Modifiable from each model's live inclusion row on its own
element, as V1.7 did, so inclusion edits made after V1.7 reach the element flags the generator now
reads. Each test clones a tenant and edits it, so public is left as loaded.
"""

import uuid

import pytest

V1_10 = "V1.10__element_flags_resync.sql"
TABLES = {"Entities": "Entity", "Attributes": "Attribute"}


@pytest.fixture
def tenant(pg_conn):
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _flags(cur, schema, table):
    cur.execute(f'SELECT "Id", "LevelOfAccess", "Queryable", "Modifiable" FROM "{schema}"."{table}" ORDER BY "Id"')
    return cur.fetchall()


def _included_element(cur, schema, table):
    """An element whose own model holds a live inclusion row on it, and that row's flags."""
    cur.execute(
        f'SELECT x."Id", i."LevelOfAccess", i."Queryable", i."Modifiable" FROM "{schema}"."{table}" x '
        f'JOIN "{schema}"."ExtInclusionsFromBaseDM" i ON i."IncludedElementId" = x."Id" '
        'AND i."ExtDataModelId" = x."DataModelId" '
        'WHERE i."ElementType" = %s AND NOT coalesce(i."Deleted", false) ORDER BY i."Id" DESC LIMIT 1',
        (TABLES[table],),
    )
    return cur.fetchone()


@pytest.mark.parametrize("table", TABLES)
def test_drifted_flags_are_copied_from_the_inclusion_row(apply_migration, pg_conn, tenant, table):
    with pg_conn.cursor() as cur:
        element_id, *inclusion_flags = _included_element(cur, tenant, table)
        # The opposite of every inclusion flag, as an inclusion edit after V1.7 would leave it.
        cur.execute(
            f'UPDATE "{tenant}"."{table}" SET "LevelOfAccess" = %s, "Queryable" = %s, "Modifiable" = %s WHERE "Id" = %s',
            (
                "Restricted" if inclusion_flags[0] != "Restricted" else "Public",
                not inclusion_flags[1],
                not inclusion_flags[2],
                element_id,
            ),
        )
    apply_migration(V1_10)
    with pg_conn.cursor() as cur:
        cur.execute(
            f'SELECT "LevelOfAccess", "Queryable", "Modifiable" FROM "{tenant}"."{table}" WHERE "Id" = %s',
            (element_id,),
        )
        assert list(cur.fetchone()) == inclusion_flags


@pytest.mark.parametrize("table", TABLES)
def test_an_element_without_an_inclusion_row_is_left_alone(apply_migration, pg_conn, tenant, table):
    with pg_conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{tenant}"."{table}" x SET "LevelOfAccess" = %s, "Queryable" = true, "Modifiable" = true '
            f'WHERE "Id" = (SELECT min("Id") FROM "{tenant}"."{table}" y WHERE NOT EXISTS ('
            f'SELECT 1 FROM "{tenant}"."ExtInclusionsFromBaseDM" i '
            'WHERE i."IncludedElementId" = y."Id" AND i."ExtDataModelId" = y."DataModelId" AND i."ElementType" = %s)) '
            'RETURNING "Id"',
            ("Internal", TABLES[table]),
        )
        element_id = cur.fetchone()[0]
    apply_migration(V1_10)
    with pg_conn.cursor() as cur:
        cur.execute(
            f'SELECT "LevelOfAccess", "Queryable", "Modifiable" FROM "{tenant}"."{table}" WHERE "Id" = %s',
            (element_id,),
        )
        assert cur.fetchone() == ("Internal", True, True)


def test_the_seed_is_already_in_sync_and_replay_changes_nothing(apply_migration, pg_conn, tenant):
    with pg_conn.cursor() as cur:
        before = {table: _flags(cur, tenant, table) for table in TABLES}
    apply_migration(V1_10)
    apply_migration(V1_10)
    with pg_conn.cursor() as cur:
        after = {table: _flags(cur, tenant, table) for table in TABLES}
    assert after == before
