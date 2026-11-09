"""The overlay conversion on the seed (#1388).

The seed still holds the test data #1444 and #1479 remove before the conversion runs, so each test runs
both cleanups first, then converts models 17 and 18 in one transaction, as the runner does. The
conversion checks itself (every touched model, all 16 flag combinations, against the rewritten
baseline); these tests pin what it did.
"""

import importlib.util
import pathlib
import sys
from unittest import mock
from urllib.parse import urlparse

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fastapi.encoders import jsonable_encoder

from lif.mdr_services import overlay_converter
from lif.mdr_services.overlay_converter import (
    Changes,
    ConversionFailed,
    convert_model,
    convert_overlays,
    move_base_content,
)
from lif.mdr_services.schema_generation_service import generate_openapi_schema

_ROOT = pathlib.Path(__file__).resolve().parents[4]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
async def cleaned_seed(seed_postgres):
    """The seed after #1444's and #1479's cleanups, as the conversion finds dev."""
    conn = await asyncpg.connect(seed_postgres.url())
    try:
        await _load("cleanup_export_blockers").cleanup(conn, apply=True)
        await _load("remove_test_data").cleanup(conn, apply=True)
    finally:
        await conn.close()
    return seed_postgres


@pytest.fixture
async def session(cleaned_seed):
    url = urlparse(cleaned_seed.url())
    engine = create_async_engine(
        f"postgresql+asyncpg://{url.username}:{url.password or ''}@{url.hostname}:{url.port}{url.path}"
    )
    maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def test_the_seed_converts_and_passes_every_check(session):
    try:
        report = await convert_overlays(session, [17, 18])
    except ConversionFailed as e:
        pytest.fail("\n\n".join(e.reasons))

    assert sorted(report.compared) == [1, 16, 17, 18]
    models = {m.model_id: m for m in report.models}
    assert models[17].copied == {"entities": 24, "attributes": 115, "value_sets": 1, "values": 62,
                                 "entity_associations": 36, "attribute_associations": 187}  # fmt: skip
    assert models[18].copied == {"entities": 13, "attributes": 42, "value_sets": 1, "values": 62,
                                 "entity_associations": 14, "attribute_associations": 42}  # fmt: skip
    # 17's own elements its schema doesn't show (step 6): 337 and 338, 1826 (decided on #1388), and the
    # attributes nothing associates.
    assert models[17].soft_deleted["Entities"] == [337, 338]
    assert sorted(models[17].soft_deleted["Attributes"]) == [1810, 1811, 1812, 1816, 1817, 1820, 1821, 1822, 1823,
                                                             1824, 1826, 1827, 1863, 1878, 1879, 1882]  # fmt: skip
    assert {table: len(ids) for table, ids in models[17].soft_deleted.items()} == {
        "Entities": 2, "Attributes": 16, "EntityAssociation": 7, "EntityAttributeAssociation": 83,
        "ExtInclusionsFromBaseDM": 206,
    }  # fmt: skip
    assert {table: len(ids) for table, ids in models[18].soft_deleted.items()} == {
        "Entities": 0, "Attributes": 0, "EntityAssociation": 1, "EntityAttributeAssociation": 0,
        "ExtInclusionsFromBaseDM": 73,
    }  # fmt: skip
    # Group 25's rows on step 0's attributes, and group 26's row.
    assert sorted(models[17].updated_mapping_rows) == [2747, 2749, 2751, 2753, 2755]
    assert models[18].updated_mapping_rows == []
    left = await session.execute(
        text('SELECT count(*) FROM "ExtInclusionsFromBaseDM" WHERE "Deleted" = false AND "ExtDataModelId" IN (17, 18)')
    )
    assert left.scalar() == 0


async def _full_schema(session, data_model_id):
    session.expunge_all()
    schema = await generate_openapi_schema(
        session, data_model_id, include_attr_md=True, include_entity_md=True, public_only=False, full_export=True
    )
    session.expunge_all()
    return jsonable_encoder(schema)


async def test_step_0_moves_the_eight_contact_attributes_to_model_1(session):
    moved = await move_base_content(session, Changes(), [17, 18])

    assert moved == {a: 1 for a in (1288, 1307, 1309, 1310, 1311, 1313, 1340, 1658)}
    owners = await session.execute(text('SELECT DISTINCT "DataModelId" FROM "Attributes" WHERE "Id" = ANY(:ids)'),
                                   {"ids": list(moved)})  # fmt: skip
    assert [row[0] for row in owners] == [1]


async def test_step_0_refuses_an_attribute_whose_name_the_base_already_has(session):
    await session.execute(
        text(
            'INSERT INTO "Attributes" ("Name", "UniqueName", "DataModelId", "DataType", "Deleted") '
            "VALUES ('emailAddress', 'Common.Contact.Email.emailAddress', 1, 'string', false)"
        )
    )

    with pytest.raises(ConversionFailed, match="attribute 1288 .* already live in base model 1"):
        await move_base_content(session, Changes(), [17, 18])


async def test_step_0_refuses_an_attribute_with_another_association(session):
    await session.execute(
        text(
            'INSERT INTO "EntityAttributeAssociation" ("EntityId", "AttributeId", "ExtendedByDataModelId", "Deleted") '
            "VALUES (4, 1288, 17, false)"
        )
    )

    with pytest.raises(ConversionFailed, match="attribute 1288 .* 1 other live association"):
        await move_base_content(session, Changes(), [17, 18])


async def test_it_refuses_an_overlay_with_inclusion_rows_but_no_base(session):
    full = await _full_schema(session, 17)
    await session.execute(text('UPDATE "DataModels" SET "BaseDataModelId" = NULL WHERE "Id" = 17'))

    with pytest.raises(ConversionFailed, match="model 17: has inclusion rows but no BaseDataModelId"):
        await convert_model(session, Changes(), 17, full)


async def test_it_refuses_a_mapping_row_through_a_row_the_schema_hides(session):
    """Entity 337 and attribute 1820 are 17's own but not included; step 6 drops them, so a live path
    through them can't be re-pointed (plan v4: plan change 2)."""
    full = await _full_schema(session, 17)
    row_id = (
        await session.execute(
            text(
                'INSERT INTO "TransformationAttributes" ("TransformationId", "AttributeId", "EntityId", "EntityIdPath", '
                '"AttributeType", "Deleted") SELECT t."Id", 1820, 337, \'4,337,-1820\', \'Target\', false '
                'FROM "Transformations" t WHERE t."TransformationGroupId" = 25 AND t."Deleted" = false '
                'ORDER BY t."Id" LIMIT 1 RETURNING "Id"'
            )
        )
    ).scalar()
    await move_base_content(session, Changes(), [17, 18])

    with pytest.raises(ConversionFailed, match=f"mapping row {row_id} \\(group 25.*'4,337,-1820'"):
        await convert_model(session, Changes(), 17, full)


async def test_it_refuses_when_another_model_still_uses_a_row_it_soft_deletes(session):
    """bjagg's probe on #1489: a live association from a model-2 entity to attribute 1820, which 17 owns
    and hides. Model 2 isn't compared, so without this check 1820 is soft-deleted and the run passes."""
    association_id = (
        await session.execute(
            text(
                'INSERT INTO "EntityAttributeAssociation" ("EntityId", "AttributeId", "Deleted") '
                'SELECT "Id", 1820, false FROM "Entities" WHERE "DataModelId" = 2 AND "Deleted" = false '
                'ORDER BY "Id" LIMIT 1 RETURNING "Id"'
            )
        )
    ).scalar()

    with pytest.raises(ConversionFailed) as failed:
        await convert_overlays(session, [17, 18])

    assert (
        f"EntityAttributeAssociation {association_id} (model 2) uses attribute 1820, which the conversion changes"
        in failed.value.reasons
    )


async def test_it_refuses_a_mapping_row_on_another_side_through_a_row_it_soft_deletes(session):
    """Step 8 re-points only the overlay's side; a row on another side through 1820 would be left dangling."""
    row_id = (
        await session.execute(
            text(
                'INSERT INTO "TransformationAttributes" ("TransformationId", "AttributeId", "EntityId", "EntityIdPath", '
                '"AttributeType", "Deleted") SELECT t."Id", 1820, 4, \'4,-1820\', \'Source\', false '
                'FROM "Transformations" t JOIN "TransformationsGroup" g ON g."Id" = t."TransformationGroupId" '
                'WHERE g."Id" = 25 AND t."Deleted" = false ORDER BY t."Id" LIMIT 1 RETURNING "Id"'
            )
        )
    ).scalar()

    with pytest.raises(ConversionFailed) as failed:
        await convert_overlays(session, [17, 18])

    assert any(
        reason.startswith(f"mapping row {row_id} (group 25) goes through '4,-1820'") for reason in failed.value.reasons
    )


async def test_step_0_refuses_two_candidates_with_one_unique_name(session):
    """All 8 candidates are 17's on the seed. Give 18 a ninth with 1288's UniqueName: both would move to
    model 1, which already shows both, so the comparison alone wouldn't catch it."""
    copy_id = (
        await session.execute(
            text(
                'INSERT INTO "Attributes" ("Name", "UniqueName", "DataModelId", "DataType", "Deleted") '
                'SELECT "Name", "UniqueName", 18, "DataType", false FROM "Attributes" WHERE "Id" = 1288 RETURNING "Id"'
            )
        )
    ).scalar()
    await session.execute(
        text(
            'INSERT INTO "EntityAttributeAssociation" ("EntityId", "AttributeId", "Deleted") '
            'SELECT "EntityId", :copy, false FROM "EntityAttributeAssociation" '
            'WHERE "AttributeId" = 1288 AND "Deleted" = false AND "ExtendedByDataModelId" IS NULL'
        ),
        {"copy": copy_id},
    )
    await session.execute(
        text(
            'INSERT INTO "ExtInclusionsFromBaseDM" ("ExtDataModelId", "ElementType", "IncludedElementId", '
            '"LevelOfAccess", "Queryable", "Modifiable", "Deleted") '
            'SELECT 18, "ElementType", :copy, "LevelOfAccess", "Queryable", "Modifiable", false '
            'FROM "ExtInclusionsFromBaseDM" WHERE "ExtDataModelId" = 17 AND "ElementType"::text = \'Attribute\' '
            'AND "IncludedElementId" = 1288 AND "Deleted" = false LIMIT 1'
        ),
        {"copy": copy_id},
    )

    with pytest.raises(ConversionFailed, match=f"attribute {copy_id} .* attribute 1288 \\(model 17\\) would also move"):
        await move_base_content(session, Changes(), [17, 18])


@pytest.mark.parametrize(
    ("constant", "column"), [("ATTRIBUTE_COLUMNS", "Description"), ("ENTITY_ASSOCIATION_COLUMNS", "Relationship")]
)
async def test_the_self_check_fails_a_conversion_that_loses_a_copied_column(session, constant, column):
    """The comparison is the main safety net: break the copies and it must refuse."""
    kept = tuple(c for c in getattr(overlay_converter, constant) if c != column)

    with mock.patch.object(overlay_converter, constant, kept), pytest.raises(ConversionFailed) as failed:
        await convert_overlays(session, [17, 18])

    assert any("differs from the rewritten baseline" in reason for reason in failed.value.reasons)
