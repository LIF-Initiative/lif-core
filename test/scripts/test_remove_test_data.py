"""Tests for the removal of the MDR's test data before #1388's conversion.

The removal writes to every schema of a live MDR, so the tests check what it must leave alone as
closely as what it removes: a pinned Id that holds another row, a mapping or group that keeps live
work, models 1, 17 and 18, and everything on a dry run. Each test gets a fresh copy of backup.sql
from a template database. They need a local PostgreSQL (`initdb` and `psql`) and skip without one.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
from itertools import count
from urllib.parse import urlparse

import asyncpg
import pytest
import testing.postgresql

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


removal = _load("remove_test_data")

_COPIES = count()

# Rule -> the table it soft-deletes from.
_TABLES = {
    "transformations": "Transformations",
    "groups": "TransformationsGroup",
    "value_mappings": "ValueSetValueMapping",
    "mapped_value_sets": "ExtMappedValueSet",
    "inclusions": "ExtInclusionsFromBaseDM",
    "entity_associations": "EntityAssociation",
    "attribute_associations": "EntityAttributeAssociation",
    "constraints": "Constraints",
    "model_constraints": "DataModelConstraints",
    "values": "ValueSetValues",
    "value_sets": "ValueSets",
    "attributes": "Attributes",
    "entities": "Entities",
    "model_25": "DataModels",
}


@pytest.fixture(scope="module")
def seed_server():
    """A local PostgreSQL with backup.sql loaded into a template database named seed."""
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        url = urlparse(postgresql.url())
        env = {**os.environ, "PGPASSWORD": url.password or ""}
        base = ["-h", url.hostname, "-p", str(url.port), "-U", url.username]
        subprocess.run(["psql", *base, "-d", url.path.lstrip("/"), "-c", "CREATE DATABASE seed"], env=env, check=True)
        result = subprocess.run(
            ["psql", *base, "-d", "seed", "-f", str(_ROOT / "projects/lif_mdr_database/backup.sql")],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to load backup.sql: {result.stderr}")
        yield url


@pytest.fixture
async def seed_conn(seed_server):
    """A connection to a fresh copy of the seed."""
    name = f"seed_copy_{next(_COPIES)}"
    password = f":{seed_server.password}" if seed_server.password else ""
    root = f"postgresql://{seed_server.username}{password}@{seed_server.hostname}:{seed_server.port}"
    admin = await asyncpg.connect(f"{root}/postgres")
    try:
        await admin.execute(f"CREATE DATABASE {name} TEMPLATE seed")
    finally:
        await admin.close()
    conn = await asyncpg.connect(f"{root}/{name}")
    try:
        yield conn
    finally:
        await conn.close()


async def _live(conn, schema="public"):
    """Live row Ids per table."""
    return {
        table: {r["Id"] for r in await conn.fetch(f'SELECT "Id" FROM "{schema}"."{table}" WHERE "Deleted" = false')}
        for table in _TABLES.values()
    }


async def _deleted(conn, table, ids):
    rows = await conn.fetch(f'SELECT "Id" FROM "{table}" WHERE "Id" = ANY($1::int[]) AND "Deleted"', ids)
    return sorted(r["Id"] for r in rows)


def _ids(results, rule, schema="public"):
    return sorted(row["Id"] for row in results[schema][rule])


async def test_a_dry_run_changes_nothing(seed_conn):
    before = await _live(seed_conn)

    results = await removal.cleanup(seed_conn, apply=False)

    assert results["public"]["entities"], "the seed's test entities should be found"
    assert await _live(seed_conn) == before


async def test_it_reports_every_row_it_removes_and_nothing_else(seed_conn):
    """Each table loses exactly the rows its rule printed, in public and tenant_lif_team."""
    schemas = ("public", "tenant_lif_team")
    before = {schema: await _live(seed_conn, schema) for schema in schemas}

    results = await removal.cleanup(seed_conn, apply=True)

    for schema in schemas:
        after = await _live(seed_conn, schema)
        for rule, table in _TABLES.items():
            assert before[schema][table] - after[table] == set(_ids(results, rule, schema)), (schema, rule)
            assert after[table] <= before[schema][table], (schema, rule)


async def test_it_removes_the_seed_test_rows_and_model_25(seed_conn):
    owned = {
        table: [r["Id"] for r in await seed_conn.fetch(f'SELECT "Id" FROM "{table}" WHERE "DataModelId" = 25')]
        for table in ("Entities", "Attributes", "ValueSets", "ValueSetValues")
    }
    assert all(owned.values()), owned

    results = await removal.cleanup(seed_conn, apply=True)

    pinned_entities = [i for i, *_ in removal.SEED_ENTITIES]
    pinned_attributes = [i for i, *_ in removal.SEED_ATTRIBUTES]
    assert await _deleted(seed_conn, "Entities", pinned_entities + owned["Entities"]) == sorted(
        pinned_entities + owned["Entities"]
    )
    assert await _deleted(seed_conn, "Attributes", pinned_attributes + owned["Attributes"]) == sorted(
        pinned_attributes + owned["Attributes"]
    )
    assert await _deleted(seed_conn, "ValueSets", owned["ValueSets"]) == sorted(owned["ValueSets"])
    assert await _deleted(seed_conn, "ValueSetValues", owned["ValueSetValues"]) == sorted(owned["ValueSetValues"])
    assert [tuple(r.values()) for r in results["public"]["model_25"]] == [(25, "Test2UpdatedSourceModel")]
    # Group 22 is model 25's last live group (#1388).
    assert 22 in _ids(results, "groups")
    # Model 18's inclusions of model 25's 1839 and 1851, and 17's associations to its test entity.
    assert {169, 185} <= set(_ids(results, "inclusions"))
    assert 158 in _ids(results, "entity_associations")
    assert 1795 in _ids(results, "attribute_associations")
    # Model 25's value mappings to model 17's values.
    assert {2347, 2348} <= set(_ids(results, "value_mappings"))


async def test_it_leaves_the_real_models_and_1826(seed_conn):
    await removal.cleanup(seed_conn, apply=True)

    assert await _deleted(seed_conn, "DataModels", [1, 17, 18]) == []
    # stateUPrivateTestAttr is left to the conversion (decided on #1388).
    assert await _deleted(seed_conn, "Attributes", [1826]) == []


async def test_a_pin_matches_only_with_its_model_and_unique_name(seed_conn):
    """Demo holds other rows at the dev-only Ids: 380 there is UniconTestIgnore.Base.BeachEnt1."""
    await seed_conn.execute(
        'INSERT INTO "Entities" ("Id", "DataModelId", "Name", "UniqueName", "Deleted") OVERRIDING SYSTEM VALUE VALUES'
        " (380, 1, 'BeachEnt1', 'UniconTestIgnore.Base.BeachEnt1', false),"
        " (381, 18, 'partner.beach.ent_a', 'partner.beach.ent_a', false),"
        " (382, 17, 'partner.beach.ent_b', 'partner.beach.ent_b', false),"
        " (386, 1, 'TammieTestEntity', 'TammieTestEntity', false)"
    )

    results = await removal.cleanup(seed_conn, apply=True)

    assert 381 in _ids(results, "entities")
    # Wrong name, wrong model, and a row nobody pinned.
    assert await _deleted(seed_conn, "Entities", [380, 382, 386]) == []


async def _add_mappings(conn):
    """Group 9001 (1 -> 17): 9101 maps test attribute 1833, 9102 has test entity 342 on its path,
    9103 touches no test row. Group 9002: only 9104, which maps test attribute 1832 under an old
    dotted-name path."""
    await conn.execute(
        'INSERT INTO "TransformationsGroup" ("Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "Name", "Deleted")'
        " OVERRIDING SYSTEM VALUE VALUES (9001, 1, 17, '91.0', 'kept', false), (9002, 1, 17, '92.0', 'emptied', false)"
    )
    await conn.execute(
        'INSERT INTO "Transformations" ("Id", "TransformationGroupId", "Name", "Deleted") OVERRIDING SYSTEM VALUE'
        " VALUES (9101, 9001, 'a', false), (9102, 9001, 'b', false), (9103, 9001, 'c', false), (9104, 9002, 'd', false)"
    )
    await conn.execute(
        'INSERT INTO "TransformationAttributes" ("Id", "TransformationId", "AttributeId", "EntityIdPath", "AttributeType", "Deleted")'
        " OVERRIDING SYSTEM VALUE VALUES"
        " (9201, 9101, 93, '12,-93', 'Source', false), (9202, 9101, 1833, '4,342,-1833', 'Target', false),"
        " (9203, 9102, 93, '12,-93', 'Source', false), (9204, 9102, 54, '4,342,-54', 'Target', false),"
        " (9205, 9103, 93, '12,-93', 'Source', false), (9206, 9103, 54, '4,3,-54', 'Target', false),"
        # A dotted-name path, as old rows hold: only the AttributeId names the test row.
        " (9207, 9104, 1832, 'LIF.testNewLIFAttribute', 'Source', false)"
    )


async def test_it_removes_the_mappings_through_a_test_row_and_the_groups_they_empty(seed_conn):
    await _add_mappings(seed_conn)

    results = await removal.cleanup(seed_conn, apply=True)

    mine = [tuple(r.values()) for r in results["public"]["transformations"] if r["Id"] >= 9101]
    assert mine == [(9101, 9001, [9201, 9202]), (9102, 9001, [9203, 9204]), (9104, 9002, [9207])]
    assert await _deleted(seed_conn, "Transformations", [9103]) == []
    assert await _deleted(seed_conn, "TransformationAttributes", [9205, 9206]) == []
    assert await _deleted(seed_conn, "TransformationsGroup", [9001, 9002]) == [9002]


async def test_a_second_run_changes_nothing(seed_conn):
    await _add_mappings(seed_conn)
    await removal.cleanup(seed_conn, apply=True)

    again = await removal.cleanup(seed_conn, apply=True)

    assert {schema: {rule: rows for rule, rows in rules.items() if rows} for schema, rules in again.items()} == {
        schema: {} for schema in again
    }


async def test_model_25_goes_only_while_it_is_still_the_test_model(seed_conn):
    await seed_conn.execute('UPDATE "DataModels" SET "Name" = \'Someone else\'\'s model\' WHERE "Id" = 25')

    results = await removal.cleanup(seed_conn, apply=True)

    assert results["public"]["model_25"] == []
    assert await _deleted(seed_conn, "Attributes", [1834, 1836]) == []
    assert await _deleted(seed_conn, "ValueSets", [343]) == []


async def test_a_group_that_was_already_empty_is_kept(seed_conn):
    """Dev's group 31 (17 -> 26): live, no live mappings, and an old deleted one through a test row."""
    await seed_conn.execute(
        'INSERT INTO "TransformationsGroup" ("Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "Name", "Deleted")'
        " OVERRIDING SYSTEM VALUE VALUES (9003, 1, 17, '93.0', 'already empty', false)"
    )
    await seed_conn.execute(
        'INSERT INTO "Transformations" ("Id", "TransformationGroupId", "Name", "Deleted") OVERRIDING SYSTEM VALUE'
        " VALUES (9105, 9003, 'old', true)"
    )
    await seed_conn.execute(
        'INSERT INTO "TransformationAttributes" ("Id", "TransformationId", "AttributeId", "EntityIdPath", "AttributeType", "Deleted")'
        " OVERRIDING SYSTEM VALUE VALUES (9208, 9105, 1833, '4,342,-1833', 'Target', true)"
    )

    await removal.cleanup(seed_conn, apply=True)

    assert await _deleted(seed_conn, "TransformationsGroup", [9003]) == []


async def test_an_association_from_a_test_entity_to_a_real_attribute_goes(seed_conn):
    await seed_conn.execute(
        'INSERT INTO "EntityAttributeAssociation" ("Id", "EntityId", "AttributeId", "Deleted") OVERRIDING SYSTEM VALUE'
        " VALUES (9301, 342, 54, false)"
    )

    results = await removal.cleanup(seed_conn, apply=True)

    assert 9301 in _ids(results, "attribute_associations")
    assert await _deleted(seed_conn, "Attributes", [54]) == []
