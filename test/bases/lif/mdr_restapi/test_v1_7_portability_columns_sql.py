"""Postgres-backed tests for the V1.7 portability-columns migration (issue #1386).

V1.7 adds element flags, association Name/Array and model lineage columns to public and every
tenant_* schema, and backfills them per the portable-format spec's §11 "Migration defaults". The
values must reproduce what the schema generator emits today, so the oracle here is independent of
the migration: the generator's own key rules for Name, and the inclusion rows for the flags.

backup.sql (loaded by conftest's postgres_server) already contains V1.7's result, so each test
clones a tenant with data, drops the new columns there, and re-runs V1.7 to backfill it from scratch.
"""

import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest
from lif.mdr_services.schema_generation_service import embedded_property_key

_V1_7 = (
    Path(__file__).parent.parent.parent.parent.parent
    / "sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.7__portability_columns.sql"
)

NEW_COLUMNS = {
    "Entities": ["LevelOfAccess", "Queryable", "Modifiable"],
    "Attributes": ["LevelOfAccess", "Queryable", "Modifiable"],
    "EntityAssociation": ["Name", "Array"],
    "EntityAttributeAssociation": ["Name", "Array"],
    "DataModels": ["CopiedFromName", "CopiedFromVersion", "CopiedFromContributorOrganization"],
}

# Relationship x Placement combinations the seed lacks (it has no has*/relevant* relationships,
# and no NULL placement with a relationship set).
SYNTHETIC_ASSOCIATIONS = [
    ("hasV17ProbeRef", "Reference"),
    ("hasV17ProbeEmb", "Embedded"),
    ("hasV17ProbeNone", None),
    ("relevantV17ProbeRef", "Reference"),
    ("relevantV17ProbeNone", None),
    ("v17ProbeNone", None),
    ("", None),
]


def ref_key(relationship, child_name):
    """add_ref's key for a Reference association (schema_generation_service.py, add_ref)."""
    if relationship is None or relationship.startswith(("has", "relevant")):
        return "Ref" + child_name
    return relationship + "Ref" + child_name


def expected_name(relationship, placement, child_name):
    if placement == "Reference":
        return ref_key(relationship, child_name)
    return embedded_property_key(relationship, child_name)


def apply_v1_7(postgres_server):
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
            str(_V1_7),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to apply V1.7: {result.stderr}")


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


@pytest.fixture
def bare_tenant(postgres_server, pg_conn):
    """A data-carrying tenant clone with V1.7's columns dropped, plus the synthetic associations.

    This is the state of a tenant that existed before V1.7 was applied.
    """
    schema = f"tenant_t{uuid.uuid4().hex[:12]}"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT public.clone_lif_schema(%s)", (schema,))
        for table, columns in NEW_COLUMNS.items():
            drops = ", ".join(f'DROP COLUMN "{c}"' for c in columns)
            cur.execute(f'ALTER TABLE "{schema}"."{table}" {drops}')
        # A parent with no associations yet, so the (parent, child, Relationship) unique index can't collide.
        cur.execute(
            f'SELECT "Id" FROM "{schema}"."Entities" e WHERE NOT "Deleted" AND NOT EXISTS '
            f'(SELECT 1 FROM "{schema}"."EntityAssociation" ea WHERE ea."ParentEntityId" = e."Id") ORDER BY "Id" LIMIT 2'
        )
        parent_id, child_id = (row[0] for row in cur.fetchall())
        for relationship, placement in SYNTHETIC_ASSOCIATIONS:
            cur.execute(
                f'INSERT INTO "{schema}"."EntityAssociation" ("ParentEntityId", "ChildEntityId", "Relationship", "Placement") '
                "VALUES (%s, %s, %s, %s)",
                (parent_id, child_id, relationship, placement),
            )
    yield schema
    with pg_conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _new_column_values(cur, schema):
    values = {}
    for table, columns in NEW_COLUMNS.items():
        cols = ", ".join(f'"{c}"' for c in columns)
        cur.execute(f'SELECT "Id", {cols} FROM "{schema}"."{table}" ORDER BY "Id"')
        values[table] = cur.fetchall()
    return values


class TestV17Backfill:
    def test_entity_association_name_and_array_follow_the_generator(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute(
                f'SELECT ea."Relationship", ea."Placement", c."Name", c."Array", ea."Name", ea."Array" '
                f'FROM "{bare_tenant}"."EntityAssociation" ea JOIN "{bare_tenant}"."Entities" c ON c."Id" = ea."ChildEntityId"'
            )
            rows = cur.fetchall()
        assert len(rows) > len(SYNTHETIC_ASSOCIATIONS)
        for relationship, placement, child_name, child_array, name, array in rows:
            assert name == expected_name(relationship, placement, child_name), (relationship, placement, child_name)
            assert array is (child_array == "Yes")

    def test_attribute_association_name_is_the_attribute_name(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute(
                f'SELECT a."Name", a."Array", x."Name", x."Array" FROM "{bare_tenant}"."EntityAttributeAssociation" x '
                f'JOIN "{bare_tenant}"."Attributes" a ON a."Id" = x."AttributeId"'
            )
            rows = cur.fetchall()
        assert rows
        for attribute_name, attribute_array, name, array in rows:
            assert name == attribute_name
            assert array is (attribute_array == "Yes")

    def test_flags_come_from_the_models_own_inclusion_row_else_the_default(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            for table, element_type in (("Entities", "Entity"), ("Attributes", "Attribute")):
                cur.execute(
                    f'SELECT e."Id", e."LevelOfAccess", e."Queryable", e."Modifiable", '
                    f'i."LevelOfAccess", i."Queryable", i."Modifiable" FROM "{bare_tenant}"."{table}" e '
                    f'LEFT JOIN "{bare_tenant}"."ExtInclusionsFromBaseDM" i ON i."ElementType" = %s '
                    'AND NOT coalesce(i."Deleted", false) AND i."IncludedElementId" = e."Id" '
                    'AND i."ExtDataModelId" = e."DataModelId"',
                    (element_type,),
                )
                rows = cur.fetchall()
                with_inclusion = [r for r in rows if r[4] is not None]
                # The seed's own-element inclusion rows (models 17 and 18) must keep their flags;
                # they are what a WHERE ... IS NULL backfill would miss if the default came first.
                assert with_inclusion, table
                assert any(r[4:] != ("Public", False, False) for r in with_inclusion), table
                for _, *flags, inc_access, inc_queryable, inc_modifiable in rows:
                    expected = (inc_access, inc_queryable, inc_modifiable) if inc_access else ("Public", False, False)
                    assert tuple(flags) == expected, table

    def test_lineage_is_not_backfilled(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute(
                f'SELECT count(*) FROM "{bare_tenant}"."DataModels" WHERE "CopiedFromName" IS NOT NULL '
                'OR "CopiedFromVersion" IS NOT NULL OR "CopiedFromContributorOrganization" IS NOT NULL'
            )
            assert cur.fetchone()[0] == 0


class TestV17Defaults:
    def test_new_elements_get_the_flag_defaults_and_associations_get_no_name(
        self, postgres_server, pg_conn, bare_tenant
    ):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute(f'SELECT "Id" FROM "{bare_tenant}"."DataModels" ORDER BY "Id" LIMIT 1')
            data_model_id = cur.fetchone()[0]
            cur.execute(
                f'INSERT INTO "{bare_tenant}"."Entities" ("Name", "UniqueName", "DataModelId") '
                'VALUES (%s, %s, %s) RETURNING "Id", "LevelOfAccess", "Queryable", "Modifiable"',
                ("V17Probe", "V17Probe", data_model_id),
            )
            entity_id, *flags = cur.fetchone()
            assert tuple(flags) == ("Public", False, False)
            # Name and Array have no default: NULL marks a row a later backfill still has to fill.
            cur.execute(
                f'INSERT INTO "{bare_tenant}"."EntityAssociation" ("ParentEntityId", "ChildEntityId") '
                'VALUES (%s, %s) RETURNING "Name", "Array"',
                (entity_id, entity_id),
            )
            assert cur.fetchone() == (None, None)


class TestV17Replay:
    def test_replay_changes_nothing(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            first = {schema: _new_column_values(cur, schema) for schema in ("public", bare_tenant)}
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            second = {schema: _new_column_values(cur, schema) for schema in ("public", bare_tenant)}
        assert first == second

    def test_every_tenant_schema_has_every_new_column(self, postgres_server, pg_conn, bare_tenant):
        apply_v1_7(postgres_server)
        with pg_conn.cursor() as cur:
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_'")
            schemas = [row[0] for row in cur.fetchall()]
            assert bare_tenant in schemas
            for schema in schemas:
                for table, columns in NEW_COLUMNS.items():
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
                        (schema, table),
                    )
                    present = {row[0] for row in cur.fetchall()}
                    assert set(columns) <= present, (schema, table)
