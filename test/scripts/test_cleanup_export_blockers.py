"""Tests for the #1393 cleanup of the data that keeps models and mapping groups from exporting.

The cleanup writes to every schema of a live MDR, so the tests check what it must leave alone as
closely as what it changes: overlays, attributes a mapping still uses, and everything on a dry run.
The end-to-end test runs the real converters before and after, through measure_export_blockers.py.
Each test gets a fresh copy of backup.sql from a template database. They need a local PostgreSQL
(`initdb` and `psql`) and skip without one, like the MDR tests.
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
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered first: @dataclass resolves its annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load("cleanup_export_blockers")
measure = _load("measure_export_blockers")

_COPIES = count()


def test_format_ids_folds_runs():
    assert cleanup.format_ids([7, 3, 1, 2, 9, 10]) == "1-3, 7, 9-10"


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
    """A connection to a fresh copy of the seed, and its URL."""
    name = f"seed_copy_{next(_COPIES)}"
    admin = await asyncpg.connect(_url(seed_server, "postgres"))
    try:
        await admin.execute(f"CREATE DATABASE {name} TEMPLATE seed")
    finally:
        await admin.close()
    url = _url(seed_server, name)
    conn = await asyncpg.connect(url)
    try:
        yield conn, url
    finally:
        await conn.close()


def _url(server, database):
    password = f":{server.password}" if server.password else ""
    return f"postgresql://{server.username}{password}@{server.hostname}:{server.port}/{database}"


async def _measure(url):
    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://", 1))
    try:
        return {result.schema: result for result in await measure.measure(engine)}
    finally:
        await engine.dispose()


async def _snapshot(conn):
    # Every column the cleanup can write, in public.
    return (
        await conn.fetch('SELECT "Id", "DataType", "Deleted" FROM "Attributes" ORDER BY "Id"'),
        await conn.fetch('SELECT "Id", "Name" FROM "TransformationsGroup" ORDER BY "Id"'),
        await conn.fetch('SELECT "Id", "ContributorOrganization" FROM "DataModels" ORDER BY "Id"'),
        await conn.fetch('SELECT "Id", "Deleted" FROM "Transformations" ORDER BY "Id"'),
    )


async def test_cleanup_clears_its_refusals_and_leaves_the_rest_to_1388(seed_conn):
    conn, url = seed_conn
    before = await _measure(url)
    results = await cleanup.cleanup(conn, apply=True)
    after = await _measure(url)

    assert list(results) == ["public", "tenant_lif_team"]
    public = results["public"]
    assert {rule: len(rows) for rule, rows in public.items()} == {
        "unassociated_skipped": 0,
        "unassociated": 76,
        # 921 measured, less the 70 the first rule deletes.
        "no_data_type": 851,
        "group_name": 0,
        "model_26_org": 1,
        "transformation_1189": 1,
        "value_3649_extension": 1,
    }
    assert (before["public"].models_exported, after["public"].models_exported) == (1, 12)
    assert (before["public"].groups_exported, after["public"].groups_exported) == (2, 3)
    # What's left is the seed's entity-typed attributes, #1388's associations and overlay groups,
    # and model 25's one attribute associated only through a row another model owns.
    assert {key: len(refused) for key, refused in after["public"].refusals.items()} == {
        "NOT_MIGRATED: the attribute has DataType entity; it becomes an association to the entity": 190,
        "NOT_MIGRATED: the association is declared with ExtendedByDataModelId": 62,
        "NOT_MIGRATED: the child … is in another model": 8,
        "NOT_MIGRATED: … is an overlay; convert it first (ADR data_model/0004)": 6,
        "NOT_MIGRATED: model N declared it between two models it does not own, so it belongs to no model": 2,
        "NOT_MIGRATED: the attribute is in no association; migration drops it": 1,
    }


@pytest.mark.parametrize(
    "make_overlay_by",
    [
        # Model 17 is an overlay both ways on the seed; each case leaves it one, so each test covers one.
        pytest.param('UPDATE "ExtInclusionsFromBaseDM" SET "Deleted" = true WHERE "ExtDataModelId" = 17', id="base"),
        pytest.param('UPDATE "DataModels" SET "BaseDataModelId" = NULL WHERE "Id" = 17', id="inclusion-rows"),
    ],
)
async def test_cleanup_leaves_overlays_alone(seed_conn, make_overlay_by):
    conn, url = seed_conn
    await conn.execute(make_overlay_by)
    overlay_rows = 'SELECT "Id", "DataType", "Deleted" FROM "Attributes" WHERE "DataModelId" IN (17, 18) ORDER BY "Id"'
    before = await conn.fetch(overlay_rows)
    # Model 17 has 14 live unassociated attributes, which the first rule would delete without the filter.
    assert (
        await conn.fetchval(
            'SELECT count(*) FROM "Attributes" a WHERE a."DataModelId" = 17 AND a."Deleted" = false AND NOT EXISTS ('
            ' SELECT 1 FROM "EntityAttributeAssociation" x WHERE x."AttributeId" = a."Id" AND x."Deleted" = false)'
        )
        == 14
    )

    await cleanup.cleanup(conn, apply=True)

    assert await conn.fetch(overlay_rows) == before


async def test_dry_run_changes_nothing_and_a_second_run_finds_nothing(seed_conn):
    conn, url = seed_conn
    before = await _snapshot(conn)
    dry = await cleanup.cleanup(conn, apply=False)
    assert await _snapshot(conn) == before
    assert len(dry["public"]["no_data_type"]) == 851

    await cleanup.cleanup(conn, apply=True)
    again = await cleanup.cleanup(conn, apply=True)
    assert all(not rows for schema in again.values() for rows in schema.values())


async def test_cleanup_names_a_blank_group_and_skips_a_mapped_attribute(seed_conn):
    conn, url = seed_conn
    # Blank-named groups (dev has 10; Name is NOT NULL, so blank is empty or whitespace), and an unassociated attribute a live mapping row uses.
    await conn.execute(
        'INSERT INTO "TransformationsGroup" ("Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "Name", "Deleted") OVERRIDING SYSTEM VALUE'
        " VALUES (9001, 11, 7, '1.0', '', false), (9002, 15, 1, '2.0', E'\\t ', false), (9003, 1, 11, '1.0', ' ', true)"
    )
    attribute = await conn.fetchval(
        'SELECT a."Id" FROM "Attributes" a WHERE a."DataModelId" = 15 AND a."Deleted" = false AND NOT EXISTS ('
        ' SELECT 1 FROM "EntityAttributeAssociation" x WHERE x."AttributeId" = a."Id" AND x."Deleted" = false)'
        ' ORDER BY a."Id" LIMIT 1'
    )
    await conn.execute(
        'INSERT INTO "Transformations" ("Id", "TransformationGroupId", "Name", "Deleted") OVERRIDING SYSTEM VALUE VALUES (9101, 9001, \'t\', false)'
    )
    await conn.execute(
        'INSERT INTO "TransformationAttributes" ("Id", "TransformationId", "AttributeId", "EntityId", "AttributeType", "Deleted") OVERRIDING SYSTEM VALUE'
        " VALUES (9201, 9101, $1, NULL, 'Source', false)",
        attribute,
    )

    results = await cleanup.cleanup(conn, apply=True)

    public = results["public"]
    assert [(row["Id"], row["old_name"], row["Name"]) for row in public["group_name"]] == [
        (9001, "", "Schema.org_ELM"),
        (9002, "\t ", "Open Badges v2_LIF"),
    ]
    assert [row["Id"] for row in public["unassociated_skipped"]] == [attribute]
    assert attribute not in [row["Id"] for row in public["unassociated"]]
    assert await conn.fetchval('SELECT "Deleted" FROM "Attributes" WHERE "Id" = $1', attribute) is False
    # A deleted group keeps its blank Name.
    assert await conn.fetchval('SELECT "Name" FROM "TransformationsGroup" WHERE "Id" = 9003') == " "


async def test_cleanup_keeps_1189_once_it_has_an_expression(seed_conn):
    # The rule is for the empty row the decision named; one someone has since filled in is kept.
    conn, url = seed_conn
    await conn.execute('UPDATE "Transformations" SET "Expression" = \'{ "a": b }\' WHERE "Id" = 1189')

    results = await cleanup.cleanup(conn, apply=True)

    assert results["public"]["transformation_1189"] == []
    assert await conn.fetchval('SELECT "Deleted" FROM "Transformations" WHERE "Id" = 1189') is False


async def test_cleanup_keeps_3649_extension_once_it_has_notes(seed_conn):
    # A flag someone has since explained is no longer the stray one the decision named.
    conn, url = seed_conn
    await conn.execute('UPDATE "ValueSetValues" SET "ExtensionNotes" = \'why\' WHERE "Id" = 3649')

    results = await cleanup.cleanup(conn, apply=True)

    assert results["public"]["value_3649_extension"] == []
    assert await conn.fetchval('SELECT "Extension" FROM "ValueSetValues" WHERE "Id" = 3649') is True
