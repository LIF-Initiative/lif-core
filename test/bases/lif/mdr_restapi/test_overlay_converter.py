"""The overlay conversion on the seed (#1388).

The seed still holds the test data #1444 and #1479 remove before the conversion runs, so each test runs
both cleanups first, then converts models 17 and 18 in one transaction, as the runner does. The
conversion checks itself (every touched model, all 16 flag combinations, against the rewritten
baseline); these tests pin what it did.
"""

import importlib.util
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from fastapi.encoders import jsonable_encoder

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


@pytest.mark.xfail(
    strict=True,
    reason="own elements keep their Ids, so `required` order changes; decision open on #1388 (the order question)",
)
async def test_the_seed_converts_and_passes_every_check(session):
    try:
        report = await convert_overlays(session, [17, 18])
    except ConversionFailed as e:
        pytest.fail("\n\n".join(e.reasons))

    assert sorted(report.compared) == [1, 16, 17, 18]
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
