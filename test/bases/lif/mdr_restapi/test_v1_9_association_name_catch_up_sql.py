"""Postgres-backed tests for the V1.9 association Name/Array catch-up migration (issue #1386).

V1.9 fills the association Name/Array that an MDR image without PR B left NULL, using V1.7's rules.
The oracle is the Python rule the create paths use (lif.mdr_services.association_name), so the SQL
and the Python can't drift apart unnoticed.

Each test clones a tenant with data and NULLs every association's Name and Array there, the state a
tenant's new rows are in when the old image created them.
"""

import uuid

import pytest
from lif.mdr_services.association_name import association_array, entity_association_name

V1_9 = "V1.9__association_name_catch_up.sql"


@pytest.fixture
def nulled_tenant(pg_conn):
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
        for table in ("EntityAssociation", "EntityAttributeAssociation"):
            cur.execute(f'UPDATE "{schema}"."{table}" SET "Name" = NULL, "Array" = NULL')
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _entity_associations(cur, schema):
    cur.execute(
        f'SELECT ea."Id", ea."Relationship", ea."Placement", c."Name", c."Array", ea."Name", ea."Array" '
        f'FROM "{schema}"."EntityAssociation" ea JOIN "{schema}"."Entities" c ON c."Id" = ea."ChildEntityId" '
        'ORDER BY ea."Id"'
    )
    return cur.fetchall()


def _attribute_associations(cur, schema):
    cur.execute(
        f'SELECT x."Id", a."Name", a."Array", x."Name", x."Array" FROM "{schema}"."EntityAttributeAssociation" x '
        f'JOIN "{schema}"."Attributes" a ON a."Id" = x."AttributeId" ORDER BY x."Id"'
    )
    return cur.fetchall()


class TestV19AssociationNameCatchUp:
    def test_entity_association_name_and_array_follow_the_python_rule(self, apply_migration, pg_conn, nulled_tenant):
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            rows = _entity_associations(cur, nulled_tenant)
        assert len(rows) > 100
        mismatches = [
            row
            for row in rows
            if (row[5], row[6]) != (entity_association_name(row[1], row[2], row[3]), association_array(row[4]))
        ]
        assert mismatches == []

    def test_attribute_association_name_and_array_follow_the_python_rule(self, apply_migration, pg_conn, nulled_tenant):
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            rows = _attribute_associations(cur, nulled_tenant)
        assert len(rows) > 100
        mismatches = [row for row in rows if (row[3], row[4]) != (row[1], association_array(row[2]))]
        assert mismatches == []

    def test_a_name_that_is_not_null_is_left_alone(self, apply_migration, pg_conn, nulled_tenant):
        # A Name set some other way (a model import, #1388's collision fixes), with an Array that disagrees
        # with the child's: V1.9 must keep both.
        with pg_conn.cursor() as cur:
            cur.execute(
                f'UPDATE "{nulled_tenant}"."EntityAssociation" SET "Name" = %s, "Array" = true '
                f'WHERE "Id" = (SELECT min("Id") FROM "{nulled_tenant}"."EntityAssociation") RETURNING "Id"',
                ("V19ProbeName",),
            )
            ea_id = cur.fetchone()[0]
            cur.execute(
                f'UPDATE "{nulled_tenant}"."EntityAttributeAssociation" SET "Name" = %s, "Array" = true '
                f'WHERE "Id" = (SELECT min("Id") FROM "{nulled_tenant}"."EntityAttributeAssociation") RETURNING "Id"',
                ("V19ProbeName",),
            )
            xa_id = cur.fetchone()[0]
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            cur.execute(f'SELECT "Name", "Array" FROM "{nulled_tenant}"."EntityAssociation" WHERE "Id" = %s', (ea_id,))
            assert cur.fetchone() == ("V19ProbeName", True)
            cur.execute(
                f'SELECT "Name", "Array" FROM "{nulled_tenant}"."EntityAttributeAssociation" WHERE "Id" = %s', (xa_id,)
            )
            assert cur.fetchone() == ("V19ProbeName", True)

    def test_replay_changes_nothing(self, apply_migration, pg_conn, nulled_tenant):
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            before = (_entity_associations(cur, nulled_tenant), _attribute_associations(cur, nulled_tenant))
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            after = (_entity_associations(cur, nulled_tenant), _attribute_associations(cur, nulled_tenant))
        assert after == before

    def test_no_schema_keeps_a_null_name(self, apply_migration, pg_conn, nulled_tenant):
        apply_migration(V1_9)
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname"
            )
            schemas = [row[0] for row in cur.fetchall()]
            assert "public" in schemas and nulled_tenant in schemas
            nulls = {}
            for schema in schemas:
                for table in ("EntityAssociation", "EntityAttributeAssociation"):
                    cur.execute(f'SELECT count(*) FROM "{schema}"."{table}" WHERE "Name" IS NULL OR "Array" IS NULL')
                    count = cur.fetchone()[0]
                    if count:
                        nulls[(schema, table)] = count
        assert nulls == {}
