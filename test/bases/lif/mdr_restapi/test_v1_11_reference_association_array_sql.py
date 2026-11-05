"""Postgres-backed tests for the V1.11 Reference association Array reset (issue #1471).

V1.7 copied each child entity's Array onto every association, Reference ones included, so a
reference to an entity whose Array is Yes was stored as a list. #1471 decided a Reference
association is single unless it is set otherwise. V1.11 resets the copies V1.7 made and leaves
every other value. backup.sql already holds V1.11's result (test_association_name_seed.py checks
it), so each test clones a tenant and puts V1.7's copies back first; on public the migration
changes nothing.
"""

import uuid

import pytest

V1_11 = "V1.11__reference_association_array.sql"


@pytest.fixture
def tenant(pg_conn):
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _arrays(cur, schema):
    cur.execute(f'SELECT "Id", "Array" FROM "{schema}"."EntityAssociation" ORDER BY "Id"')
    return dict(cur.fetchall())


def _v1_7_copies(cur, schema):
    """Put back what V1.7 stored on every Reference association whose child's Array is Yes."""
    cur.execute(
        f'UPDATE "{schema}"."EntityAssociation" ea SET "Array" = true FROM "{schema}"."Entities" c '
        """WHERE c."Id" = ea."ChildEntityId" AND ea."Placement" = 'Reference' AND c."Array" = 'Yes' """
        'RETURNING ea."Id"'
    )
    return sorted(row[0] for row in cur.fetchall())


def test_v1_7_copies_on_references_are_reset(apply_migration, pg_conn, tenant):
    with pg_conn.cursor() as cur:
        copies = _v1_7_copies(cur, tenant)
    # The seed's LIF, StateU LIF and model 25 references, deleted rows included.
    assert len(copies) >= 77
    apply_migration(V1_11)
    with pg_conn.cursor() as cur:
        arrays = _arrays(cur, tenant)
    assert [i for i in copies if arrays[i] is not False] == []


def test_only_those_copies_change(apply_migration, pg_conn, tenant):
    with pg_conn.cursor() as cur:
        _v1_7_copies(cur, tenant)
        # A reference whose Array was set some other way (its child is not a list), as CTDL's are.
        cur.execute(
            f'UPDATE "{tenant}"."EntityAssociation" ea SET "Array" = true FROM "{tenant}"."Entities" c '
            """WHERE c."Id" = ea."ChildEntityId" AND ea."Placement" = 'Reference' """
            """AND c."Array" IS DISTINCT FROM 'Yes' """
            'AND ea."Id" = (SELECT min(x."Id") FROM "' + tenant + '"."EntityAssociation" x '
            'JOIN "' + tenant + """"."Entities" y ON y."Id" = x."ChildEntityId" """
            """WHERE x."Placement" = 'Reference' AND y."Array" IS DISTINCT FROM 'Yes') RETURNING ea."Id\""""
        )
        kept_reference = cur.fetchone()[0]
        before = _arrays(cur, tenant)
        cur.execute(
            f'SELECT ea."Id" FROM "{tenant}"."EntityAssociation" ea JOIN "{tenant}"."Entities" c '
            """ON c."Id" = ea."ChildEntityId" WHERE ea."Placement" = 'Reference' AND c."Array" = 'Yes'"""
        )
        reset = {row[0] for row in cur.fetchall()}
        # Embedded lists the migration must keep. The migration runs on every schema, public included,
        # and this tenant is cloned from public: if an earlier test's run had cleared them there,
        # this check would see nothing to keep, so it fails instead.
        cur.execute(
            f'SELECT count(*) FROM "{tenant}"."EntityAssociation" ea JOIN "{tenant}"."Entities" c '
            """ON c."Id" = ea."ChildEntityId" WHERE ea."Placement" IS DISTINCT FROM 'Reference' """
            """AND c."Array" = 'Yes' AND ea."Array" """
        )
        assert cur.fetchone()[0] >= 30
    apply_migration(V1_11)
    with pg_conn.cursor() as cur:
        after = _arrays(cur, tenant)
    assert after[kept_reference] is True
    # Embedded lists, references to non-lists, and NULLs are all as they were.
    assert {i: v for i, v in after.items() if i not in reset} == {i: v for i, v in before.items() if i not in reset}


def test_replay_changes_nothing(apply_migration, pg_conn, tenant):
    with pg_conn.cursor() as cur:
        _v1_7_copies(cur, tenant)
    apply_migration(V1_11)
    with pg_conn.cursor() as cur:
        once = _arrays(cur, tenant)
    apply_migration(V1_11)
    with pg_conn.cursor() as cur:
        assert _arrays(cur, tenant) == once
