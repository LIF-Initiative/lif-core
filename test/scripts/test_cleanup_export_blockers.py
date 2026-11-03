"""Tests for the #1393 cleanup of the data that keeps models and mapping groups from exporting.

The cleanup writes to every schema of a live MDR, so the tests check what it must leave alone as
closely as what it changes: overlays, attributes a mapping still uses, and everything on a dry run.
The end-to-end test runs the real converters before and after, through measure_export_blockers.py.
Each test gets a fresh copy of backup.sql from a template database. They need a local PostgreSQL
(`initdb` and `psql`) and skip without one, like the MDR tests.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
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
        await conn.fetch('SELECT "Id", "Deleted" FROM "TransformationAttributes" ORDER BY "Id"'),
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
        # 781 measured, less the 70 the first rule deletes.
        "no_data_type": 711,
        "group_name": 0,
        "model_26_org": 1,
        "transformation_1189": 1,
        "value_3649_extension": 1,
        # The seed has no copy of 1760; dev has one in every schema.
        "transformation_1761": 0,
    }
    assert (before["public"].models_exported, after["public"].models_exported) == (2, 12)
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
    assert len(dry["public"]["no_data_type"]) == 711

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


async def test_cleanup_skips_an_attribute_an_overlay_includes(seed_conn):
    # A base model's attribute in no association, which overlay 17 still includes; and one whose
    # inclusion row is deleted, which goes like any other.
    conn, url = seed_conn
    included, formerly = [
        row["Id"]
        for row in await conn.fetch(
            'SELECT a."Id" FROM "Attributes" a WHERE a."DataModelId" = 15 AND a."Deleted" = false AND NOT EXISTS ('
            ' SELECT 1 FROM "EntityAttributeAssociation" x WHERE x."AttributeId" = a."Id" AND x."Deleted" = false)'
            ' ORDER BY a."Id" LIMIT 2'
        )
    ]
    await conn.execute(
        'INSERT INTO "ExtInclusionsFromBaseDM" ("Id", "ExtDataModelId", "ElementType", "IncludedElementId", "Deleted")'
        " OVERRIDING SYSTEM VALUE VALUES (9401, 17, 'Attribute', $1, false), (9402, 17, 'Attribute', $2, true)",
        included,
        formerly,
    )

    results = await cleanup.cleanup(conn, apply=True)

    public = results["public"]
    assert [row["Id"] for row in public["unassociated_skipped"]] == [included]
    deleted = {row["Id"] for row in public["unassociated"]}
    assert included not in deleted and formerly in deleted
    assert await conn.fetchval('SELECT "Deleted" FROM "Attributes" WHERE "Id" = $1', included) is False


async def test_cleanup_names_a_group_blank_by_python_s_strip(seed_conn):
    # The exporter's blank check is str.strip(), which strips more than space, tab, CR and LF.
    conn, url = seed_conn
    names = {9011: "\xa0", 9012: "\f\v", 9013: "　 ", 9014: "\xa0x"}
    await conn.executemany(
        'INSERT INTO "TransformationsGroup" ("Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "Name", "Deleted")'
        # One version each: a pair of models has one live group per version.
        " OVERRIDING SYSTEM VALUE VALUES ($1, 11, 7, $2, $3, false)",
        [(group, f"{group}.0", name) for group, name in names.items()],
    )
    assert [group for group, name in names.items() if not name.strip()] == [9011, 9012, 9013]

    results = await cleanup.cleanup(conn, apply=True)

    # UPDATE ... RETURNING has no row order, so compare sorted.
    assert sorted((row["Id"], row["old_name"], row["Name"]) for row in results["public"]["group_name"]) == [
        (9011, "\xa0", "Schema.org_ELM"),
        (9012, "\f\v", "Schema.org_ELM"),
        (9013, "　 ", "Schema.org_ELM"),
    ]
    assert await conn.fetchval('SELECT "Name" FROM "TransformationsGroup" WHERE "Id" = 9014') == "\xa0x"


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


async def _add_1760_and_its_copy(conn):
    # What dev has in group 3 (CEDS to LIF): 1760, and 1761 copying it field for field, both mapping
    # source attribute 93 to target attribute 54. The seed has neither.
    for transformation, source_row, target_row in ((1760, 9301, 9302), (1761, 9303, 9304)):
        await conn.execute(
            'INSERT INTO "Transformations" ("Id", "TransformationGroupId", "Name", "Expression", "ExpressionLanguage", "Deleted")'
            " OVERRIDING SYSTEM VALUE VALUES ($1, 3, 'Person.AssessmentLearningExperience.type', $2, 'JSONata', false)",
            transformation,
            '{ "Person": Assessment. { "AssessmentLearningExperience": [{ "type": Assessment Identifier }] } }',
        )
        await conn.execute(
            'INSERT INTO "TransformationAttributes" ("Id", "TransformationId", "AttributeId", "EntityId", "EntityIdPath", "AttributeType", "Deleted")'
            " OVERRIDING SYSTEM VALUE VALUES ($1, $3, 93, NULL, '12,-93', 'Source', false), ($2, $3, 54, NULL, '4,3,-54', 'Target', false)",
            source_row,
            target_row,
            transformation,
        )


async def test_cleanup_deletes_the_copy_of_1760_and_group_3_exports(seed_conn):
    conn, url = seed_conn
    await _add_1760_and_its_copy(conn)

    results = await cleanup.cleanup(conn, apply=True)
    after = await _measure(url)

    assert [tuple(row.values()) for row in results["public"]["transformation_1761"]] == [(1761, 3, [9303, 9304], None)]
    deleted = 'SELECT "Id", "Deleted" FROM "{}" WHERE "Id" = ANY($1::int[]) ORDER BY "Id"'
    assert [tuple(r) for r in await conn.fetch(deleted.format("Transformations"), [1760, 1761])] == [
        (1760, False),
        (1761, True),
    ]
    assert [
        tuple(r) for r in await conn.fetch(deleted.format("TransformationAttributes"), [9301, 9302, 9303, 9304])
    ] == [(9301, False), (9302, False), (9303, True), (9304, True)]
    assert not any(key.startswith("MAPPING_TARGET_SHARED") for key in after["public"].refusals)
    assert after["public"].groups_exported == 3

    # Bringing the copy back is enough to refuse group 3 again, so this rule is what cleared it.
    await conn.execute('UPDATE "Transformations" SET "Deleted" = false WHERE "Id" = 1761')
    await conn.execute('UPDATE "TransformationAttributes" SET "Deleted" = false WHERE "Id" IN (9303, 9304)')
    restored = await _measure(url)
    assert [
        refused for key, refused in restored["public"].refusals.items() if key.startswith("MAPPING_TARGET_SHARED")
    ] == [[("group 3 (4 -> 1 v1.0)", "Mappings[Person,AssessmentLearningExperience,type]")]]
    assert restored["public"].groups_exported == 2


@pytest.mark.parametrize(
    "make_it_differ",
    [
        pytest.param('UPDATE "Transformations" SET "Expression" = \'{ "a": b }\' WHERE "Id" = 1761', id="expression"),
        pytest.param('UPDATE "Transformations" SET "Notes" = \'kept on purpose\' WHERE "Id" = 1761', id="notes"),
        pytest.param('UPDATE "Transformations" SET "Contributor" = \'someone\' WHERE "Id" = 1761', id="contributor"),
        pytest.param(
            'UPDATE "Transformations" SET "ActivationDate" = \'2024-01-01\' WHERE "Id" = 1761', id="activation-date"
        ),
        pytest.param(
            'UPDATE "TransformationAttributes" SET "EntityIdPath" = \'4,-54\' WHERE "Id" = 9304', id="row-path"
        ),
        pytest.param('UPDATE "TransformationAttributes" SET "AttributeId" = 92 WHERE "Id" = 9303', id="mapping-row"),
        pytest.param(
            'UPDATE "TransformationAttributes" SET "Deleted" = true WHERE "Id" = 9301', id="original-row-gone"
        ),
        pytest.param('UPDATE "Transformations" SET "Deleted" = true WHERE "Id" = 1760', id="original-gone"),
    ],
)
async def test_cleanup_keeps_1761_once_it_differs_from_1760(seed_conn, make_it_differ):
    # The rule is for the exact copy the decision named; one that now differs is a mapping someone meant.
    conn, url = seed_conn
    await _add_1760_and_its_copy(conn)
    await conn.execute(make_it_differ)

    results = await cleanup.cleanup(conn, apply=True)

    assert results["public"]["transformation_1761"] == []
    assert await conn.fetchval('SELECT "Deleted" FROM "Transformations" WHERE "Id" = 1761') is False
    assert (
        await conn.fetchval('SELECT count(*) FROM "TransformationAttributes" WHERE "Id" IN (9303, 9304) AND "Deleted"')
        == 0
    )


async def test_cleanup_deletes_1761_whose_target_row_has_its_own_metadata_and_prints_it(seed_conn):
    # Dev's 1761: its target row carries placeholder metadata 1760's doesn't. Its rows map the same
    # attributes at the same paths, so it is still the copy; the metadata it drops is printed.
    conn, url = seed_conn
    await _add_1760_and_its_copy(conn)
    await conn.execute(
        'UPDATE "TransformationAttributes" SET "Notes" = \'TAT Notes\', "Contributor" = \'TAT Contributor\','
        ' "ActivationDate" = \'2021-06-15T00:00:00Z\' WHERE "Id" = 9304'
    )

    results = await cleanup.cleanup(conn, apply=True)

    [row] = results["public"]["transformation_1761"]
    assert (row["Id"], row["MappingRowIds"]) == (1761, [9303, 9304])
    dropped = json.loads(row["DroppedRowMetadata"])
    # The date is the same instant, written in the server's time zone.
    assert datetime.fromisoformat(dropped["9304"].pop("ActivationDate")) == datetime(2021, 6, 15, tzinfo=timezone.utc)
    assert dropped == {"9304": {"Notes": "TAT Notes", "Contributor": "TAT Contributor"}}
    assert await conn.fetchval('SELECT "Deleted" FROM "Transformations" WHERE "Id" = 1761') is True


async def test_cleanup_leaves_a_null_data_type_that_points_at_an_entity(seed_conn):
    # Under §11 such an attribute becomes an association to the entity, so it isn't a string.
    conn, url = seed_conn
    row = await conn.fetchrow(
        'SELECT a."Id", a."DataModelId" FROM "Attributes" a WHERE a."DataModelId" NOT IN (17, 18) AND a."Deleted" = false'
        ' AND a."DataType" IS NULL AND EXISTS (SELECT 1 FROM "EntityAttributeAssociation" x'
        ' JOIN "Entities" e ON e."Id" = x."EntityId" AND e."Deleted" = false'
        ' WHERE x."AttributeId" = a."Id" AND x."Deleted" = false) ORDER BY a."Id" LIMIT 1'
    )
    assert row is not None
    entity = await conn.fetchval(
        'SELECT "Id" FROM "Entities" WHERE "DataModelId" = $1 AND "Deleted" = false ORDER BY "Id" LIMIT 1',
        row["DataModelId"],
    )
    await conn.execute('UPDATE "Attributes" SET "TargetEntityId" = $2 WHERE "Id" = $1', row["Id"], entity)

    results = await cleanup.cleanup(conn, apply=True)

    assert row["Id"] not in [r["Id"] for r in results["public"]["no_data_type"]]
    assert await conn.fetchval('SELECT "DataType" FROM "Attributes" WHERE "Id" = $1', row["Id"]) is None
    assert await conn.fetchval('SELECT "Deleted" FROM "Attributes" WHERE "Id" = $1', row["Id"]) is False


async def test_cleanup_leaves_blank_groups_on_overlays_deleted_or_unnamed_models(seed_conn):
    conn, url = seed_conn
    await conn.execute('UPDATE "DataModels" SET "Deleted" = true WHERE "Id" = 15')
    await conn.execute('UPDATE "DataModels" SET "Name" = E\'\\u00a0\' WHERE "Id" = 11')
    await conn.execute('UPDATE "DataModels" SET "Name" = E\'\\t\' WHERE "Id" = 7')
    await conn.execute(
        'INSERT INTO "TransformationsGroup" ("Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "Name", "Deleted") OVERRIDING SYSTEM VALUE'
        # From overlay 17, to overlay 18, from deleted model 15, from model 11 (Name only an NBSP), and
        # to model 7 (Name only a tab).
        " VALUES (9021, 17, 1, '9.0', '', false), (9025, 1, 18, '9.0', '', false), (9022, 15, 1, '9.0', '', false),"
        " (9023, 11, 1, '9.0', '', false), (9024, 1, 7, '9.0', '', false)"
    )

    results = await cleanup.cleanup(conn, apply=True)

    assert results["public"]["group_name"] == []
    names = await conn.fetch('SELECT "Name" FROM "TransformationsGroup" WHERE "Id" BETWEEN 9021 AND 9025')
    assert [row["Name"] for row in names] == [""] * 5


async def test_a_failed_rollback_keeps_the_error_that_caused_it():
    class Transaction:
        async def start(self):
            pass

        async def rollback(self):
            raise ConnectionError("connection dropped")

    class Connection:
        def transaction(self):
            return Transaction()

        async def fetch(self, sql):
            raise RuntimeError("a rule failed")

    with pytest.raises(RuntimeError, match="a rule failed"):
        await cleanup.cleanup(Connection(), apply=False)
